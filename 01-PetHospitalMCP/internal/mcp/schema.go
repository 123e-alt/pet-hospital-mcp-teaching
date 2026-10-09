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

// ErrResult 把业务错误转成 MCP 文本错误结果（不让 SDK 当协议错误）。
// 对 store.ErrNotFound / store.ErrDuplicate 给出更友好的提示。
func ErrResult(err error) *mcp.CallToolResult {
	if err == nil {
		return mcp.NewToolResultText("ok")
	}
	switch {
	case errors.Is(err, store.ErrNotFound):
		return mcp.NewToolResultError("记录不存在: " + err.Error())
	case errors.Is(err, store.ErrDuplicate):
		return mcp.NewToolResultError("档案已存在: " + err.Error())
	}
	return mcp.NewToolResultError(err.Error())
}

// ---------------------------------------------------------------------------
// handler 类型别名
// ---------------------------------------------------------------------------

// Handler 是单个 MCP tool 的处理函数签名（与 mcp.ToolHandlerFunc 一致）。
type Handler = func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error)
