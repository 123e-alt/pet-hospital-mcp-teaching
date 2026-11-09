// Package mcp 把宠物医院的 store.Store 能力包装为 MCP (Model Context Protocol) 服务。
//
// 该子包基于 github.com/mark3labs/mcp-go 实现 SSE 传输，对外暴露 22 个 tool，
// 让 Claude Desktop / Cursor / Cline 等 LLM 客户端可以用自然语言操作宠物医院。
//
// 与 internal/api 包并立、共用同一个 *store.Store 实例（Store 自身用 sync.RWMutex
// 保证并发安全），可同进程双端口（REST 8080 + MCP SSE 8081）运行。
package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"

	"pethospital/internal/store"
)

// ---------------------------------------------------------------------------
// 请求参数读取
// ---------------------------------------------------------------------------

// arguments 返回 CallToolRequest 的参数 map。
// 兼容 mcp-go 不同小版本：优先用 GetArguments()，失败时直接读 Params.Arguments。
func arguments(req mcp.CallToolRequest) map[string]any {
	if req.Params.Arguments != nil {
		if m, ok := req.Params.Arguments.(map[string]any); ok {
			return m
		}
	}
	// GetArguments 是 *CallToolRequest 的方法，返回 map[string]any
	if g := req.GetArguments(); g != nil {
		return g
	}
	return map[string]any{}
}

// UnmarshalArgs 把请求参数整体反序列化到 v。
func UnmarshalArgs(req mcp.CallToolRequest, v any) error {
	args := arguments(req)
	if len(args) == 0 {
		// 允许零参调用（v 走默认零值）
		return nil
	}
	buf, err := json.Marshal(args)
	if err != nil {
		return fmt.Errorf("参数序列化失败: %w", err)
	}
	if err := json.Unmarshal(buf, v); err != nil {
		return fmt.Errorf("参数解析失败: %w", err)
	}
	return nil
}

// UnmarshalField 把指定字段（必须是 object）反序列化到 v。
// 若字段缺失或为 null，返回 nil（不修改 v 的零值）。
func UnmarshalField(req mcp.CallToolRequest, key string, v any) error {
	args := arguments(req)
	raw, ok := args[key]
	if !ok || raw == nil {
		return nil
	}
	buf, err := json.Marshal(raw)
	if err != nil {
		return fmt.Errorf("字段 %s 序列化失败: %w", key, err)
	}
	if err := json.Unmarshal(buf, v); err != nil {
		return fmt.Errorf("字段 %s 解析失败: %w", key, err)
	}
	return nil
}

// GetString / GetInt / GetFloat / GetBool 提供默认值的字段读取。
func GetString(req mcp.CallToolRequest, key, def string) string {
	if v, ok := arguments(req)[key].(string); ok {
		return v
	}
	return def
}

func GetInt(req mcp.CallToolRequest, key string, def int) int {
	switch v := arguments(req)[key].(type) {
	case float64:
		if v == float64(int64(v)) {
			return int(v)
		}
		return int(v)
	case int:
		return v
	case int64:
		return int(v)
	}
	return def
}

func GetFloat(req mcp.CallToolRequest, key string, def float64) float64 {
	switch v := arguments(req)[key].(type) {
	case float64:
		return v
	case int:
		return float64(v)
	case int64:
		return float64(v)
	}
	return def
}

func GetBool(req mcp.CallToolRequest, key string, def bool) bool {
	if v, ok := arguments(req)[key].(bool); ok {
		return v
	}
	return def
}

// GetStringSlice 把字段读取为 []string，兼容 JSON 数组里的 string 或 any。
func GetStringSlice(req mcp.CallToolRequest, key string) []string {
	raw, ok := arguments(req)[key].([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		if s, ok := item.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// 结果构造
// ---------------------------------------------------------------------------

// JSONResult 把任意可序列化数据包装成 TextContent + JSON 字符串的 MCP 结果。
// 这是 MCP tool 返回结构化数据给 LLM 的标准做法。
func JSONResult(data any) (*mcp.CallToolResult, error) {
	buf, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return mcp.NewToolResultError("结果序列化失败: " + err.Error()), nil
	}
	return mcp.NewToolResultText(string(buf)), nil
}

// TextResult 返回纯文本结果。
func TextResult(text string) (*mcp.CallToolResult, error) {
	return mcp.NewToolResultText(text), nil
}

// ---------------------------------------------------------------------------
// 结构化错误：所有 tool 失败统一返回 {"ok":false,"error":{"code","msg"}}
// ---------------------------------------------------------------------------

// 稳定的业务错误码，供客户端/模型按码处理。
const (
	ErrCodeValidation = "VALIDATION_FAILED" // 参数缺失、格式非法、枚举越界
	ErrCodeNotFound   = "NOT_FOUND"         // 记录不存在
	ErrCodeDuplicate  = "DUPLICATE"         // 档案/记录已存在
	ErrCodeInternal   = "INTERNAL_ERROR"    // 存储层或未知内部错误
	ErrCodeTimeout    = "TIMEOUT"           // 调用超时（见 WithCallGuard）
)

// errorJSON 构造结构化错误结果（NewToolResultError 文本即 JSON，便于模型解析）。
func errorJSON(code, msg string) *mcp.CallToolResult {
	buf, _ := json.Marshal(map[string]any{
		"ok":    false,
		"error": map[string]string{"code": code, "msg": msg},
	})
	return mcp.NewToolResultError(string(buf))
}

// ErrResult 把业务错误转成结构化 MCP 错误结果（不让 SDK 当协议错误）。
// 分类规则：store 哨兵错误 → NOT_FOUND/DUPLICATE；
// 含参数校验特征文案 → VALIDATION_FAILED；其余 → INTERNAL_ERROR。
func ErrResult(err error) *mcp.CallToolResult {
	if err == nil {
		return mcp.NewToolResultText("ok")
	}
	msg := err.Error()
	switch {
	case errors.Is(err, store.ErrNotFound):
		return errorJSON(ErrCodeNotFound, "记录不存在: "+msg)
	case errors.Is(err, store.ErrDuplicate):
		return errorJSON(ErrCodeDuplicate, "档案已存在: "+msg)
	case isValidationMsg(msg):
		return errorJSON(ErrCodeValidation, msg)
	}
	return errorJSON(ErrCodeInternal, msg)
}

// isValidationMsg 识别 handlers 中的参数校验错误文案。
func isValidationMsg(msg string) bool {
	for _, kw := range []string{"参数解析失败", "不能为空", "必填", "无效", "格式", "至少", "超出", "非法"} {
		if strings.Contains(msg, kw) {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// 调用护栏：统一超时 + 调用日志（标准库 log，带时间戳）
// ---------------------------------------------------------------------------

// callLog 是 MCP tool 的调用日志器（替代 fmt.Print，满足工程日志要求）。
var callLog = log.New(os.Stderr, "", log.LstdFlags)

// WithCallGuard 包装 handler：调用超时（超时返回 TIMEOUT 结构化错误）+
// 每次调用输出一条带耗时的日志（tool/result/duration）。
func WithCallGuard(h Handler, timeout time.Duration) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		ctx, cancel := context.WithTimeout(ctx, timeout)
		defer cancel()
		start := time.Now()
		res, err := h(ctx, req)
		dur := time.Since(start).Milliseconds()
		switch {
		case errors.Is(ctx.Err(), context.DeadlineExceeded):
			callLog.Printf("tool=%s result=timeout dur=%dms", req.Params.Name, dur)
			return errorJSON(ErrCodeTimeout,
				fmt.Sprintf("调用超时（超过 %s），请缩小查询范围后重试", timeout)), nil
		case err != nil:
			callLog.Printf("tool=%s result=panic_error dur=%dms err=%q", req.Params.Name, dur, err)
		case res != nil && res.IsError:
			callLog.Printf("tool=%s result=biz_error dur=%dms", req.Params.Name, dur)
		default:
			callLog.Printf("tool=%s result=ok dur=%dms", req.Params.Name, dur)
		}
		return res, err
	}
}

// ---------------------------------------------------------------------------
// handler 类型别名
// ---------------------------------------------------------------------------

// Handler 是单个 MCP tool 的处理函数签名（与 mcp.ToolHandlerFunc 一致）。
type Handler = func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error)
