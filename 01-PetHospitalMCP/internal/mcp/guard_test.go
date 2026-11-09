// internal/mcp/guard_test.go 验证结构化错误码与 WithCallGuard 超时/日志护栏。
package mcp

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/mark3labs/mcp-go/mcp"

	"pethospital/internal/store"
)

// resultText 取出 CallToolResult 的首段文本。
func resultText(t *testing.T, res *mcp.CallToolResult) string {
	t.Helper()
	if res == nil || len(res.Content) == 0 {
		t.Fatalf("空结果")
	}
	tc, ok := res.Content[0].(mcp.TextContent)
	if !ok {
		t.Fatalf("结果不是 TextContent: %T", res.Content[0])
	}
	return tc.Text
}

func TestErrResultCodes(t *testing.T) {
	cases := []struct {
		name string
		err  error
		code string
	}{
		{"not_found", store.ErrNotFound, ErrCodeNotFound},
		{"duplicate", store.ErrDuplicate, ErrCodeDuplicate},
		{"validation", errors.New("id 不能为空"), ErrCodeValidation},
		{"validation_parse", errors.New("参数解析失败: unexpected end"), ErrCodeValidation},
		{"internal", errors.New("disk io error"), ErrCodeInternal},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			res := ErrResult(c.err)
			if !res.IsError {
				t.Fatalf("应为错误结果")
			}
			text := resultText(t, res)
			if !strings.Contains(text, `"code":"`+c.code+`"`) {
				t.Fatalf("缺少错误码 %s，实际: %s", c.code, text)
			}
			if !strings.Contains(text, `"msg"`) {
				t.Fatalf("缺少可读信息: %s", text)
			}
		})
	}
}

func TestErrResultNil(t *testing.T) {
	res := ErrResult(nil)
	if res.IsError {
		t.Fatalf("nil 错误不应返回错误结果")
	}
}

func TestWithCallGuardTimeout(t *testing.T) {
	slow := Handler(func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		select {
		case <-time.After(200 * time.Millisecond):
			return mcp.NewToolResultText("done"), nil
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	})
	req := mcp.CallToolRequest{}
	req.Params.Name = "slow_tool"
	res, err := WithCallGuard(slow, 20*time.Millisecond)(context.Background(), req)
	if err != nil {
		t.Fatalf("超时应包装为结构化错误而非 Go error: %v", err)
	}
	if !res.IsError {
		t.Fatalf("超时结果应为错误")
	}
	if text := resultText(t, res); !strings.Contains(text, `"code":"`+ErrCodeTimeout+`"`) {
		t.Fatalf("缺少 TIMEOUT 错误码: %s", text)
	}
}

func TestWithCallGuardPassThrough(t *testing.T) {
	ok := Handler(func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return mcp.NewToolResultText("ok"), nil
	})
	req := mcp.CallToolRequest{}
	req.Params.Name = "fast_tool"
	res, err := WithCallGuard(ok, time.Second)(context.Background(), req)
	if err != nil || res.IsError {
		t.Fatalf("正常调用不应被拦截: err=%v isError=%v", err, res.IsError)
	}
}
