// internal/mcp/server.go 构造 MCPServer、注册 tool、启动 SSE 传输。

package mcp

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/mark3labs/mcp-go/server"

	"pethospital/internal/store"
)

// ServerOptions 配置 MCP 服务的可选项。
type ServerOptions struct {
	Name      string // 默认 "pet-hospital"
	Version   string // 默认 "1.0.0"
	BaseURL   string // 默认 http://<addr>，必须显式指定以让客户端回连 message 端点
	Addr      string // 默认 127.0.0.1:8081
	SSEPath   string // 默认 /sse
	MsgPath   string // 默认 /message
	NoColor   bool
}

// DefaultOptions 返回合理的默认配置（仅本机回环）。
func DefaultOptions(addr string) ServerOptions {
	if addr == "" {
		addr = "127.0.0.1:8081"
	}
	base := "http://" + addr
	return ServerOptions{
		Name:    "pet-hospital",
		Version: "1.0.0",
		BaseURL: base,
		Addr:    addr,
		SSEPath: "/sse",
		MsgPath: "/message",
	}
}

// NewServer 构造 MCPServer 并注册全部 22 个 tool。
// db 为外部传入的 *store.Store（通常与 REST 共享同一实例）。
func NewServer(db *store.Store, opts ServerOptions) (*server.MCPServer, error) {
	if db == nil {
		return nil, errors.New("db 不能为 nil")
	}
	if err := ensureLoopback(opts.Addr); err != nil {
		return nil, err
	}
	name := opts.Name
	if name == "" {
		name = "pet-hospital"
	}
	version := opts.Version
	if version == "" {
		version = "1.0.0"
	}
	s := server.NewMCPServer(name, version,
		server.WithInstructions(
			"宠物医院 MCP 服务：提供宠物档案 CRUD、查询、病历/收费追加、统计、批量与导出能力。"+
				"常用工具：search_pets / create_pet / get_pet / add_medical_record / add_charge / get_stats。"+
				"REST API 同步在 http://127.0.0.1:8080/ 提供。"),
	)

	// 按 tool name 索引 handler
	handlers := map[string]Handler{
		ToolHealthCheck:         healthCheckHandler(db),
		ToolGetStats:            getStatsHandler(db),
		ToolGetMeta:             getMetaHandler(db),
		ToolListEndpoints:       listEndpointsHandler(db),
		ToolCreatePet:           createPetHandler(db),
		ToolGetPet:              getPetHandler(db),
		ToolUpdatePet:           updatePetHandler(db),
		ToolPatchPet:            patchPetHandler(db),
		ToolDeletePet:           deletePetHandler(db),
		ToolSearchPets:          searchPetsHandler(db),
		ToolTopSpenders:         topSpendersHandler(db),
		ToolListMedicalRecords:  listMedicalRecordsHandler(db),
		ToolAddMedicalRecord:    addMedicalRecordHandler(db),
		ToolListCharges:         listChargesHandler(db),
		ToolAddCharge:           addChargeHandler(db),
		ToolGetPetSummary:       getPetSummaryHandler(db),
		ToolBatchCreatePets:     batchCreatePetsHandler(db),
		ToolBatchDeletePets:     batchDeletePetsHandler(db),
		ToolExportPets:          exportPetsHandler(db),
		ToolCompactDB:           compactDBHandler(db),
		ToolSeedDemoData:        seedDemoDataHandler(db),
	}

	for _, t := range allTools() {
		h, ok := handlers[t.Name]
		if !ok {
			return nil, fmt.Errorf("未找到 tool %s 对应的 handler", t.Name)
		}
		s.AddTool(t, h)
	}
	return s, nil
}

// StartSSE 启动 SSE 传输模式。阻塞调用，返回时服务已停止。
// 优雅退出：收到 Ctrl+C / SIGTERM 时关闭 http.Server。
func StartSSE(db *store.Store, opts ServerOptions) error {
	sse, err := NewSSEServer(db, opts)
	if err != nil {
		return err
	}

	// 横幅
	printMCPBanner(opts, len(allTools()))

	errCh := make(chan error, 1)
	go func() {
		if err := sse.Start(opts.Addr); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	select {
	case err := <-errCh:
		return fmt.Errorf("MCP 服务异常: %w", err)
	case <-stop:
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = sse.Shutdown(ctx)
		fmt.Printf("\n└─ MCP 服务已关闭，再见 👋\n")
		return nil
	}
}

// NewSSEServer 构造一个 *server.SSEServer（已注册全部 tool）。
// dual 模式由调用方自行调 sse.Start(addr) / sse.Shutdown(ctx) 管理。
func NewSSEServer(db *store.Store, opts ServerOptions) (*server.SSEServer, error) {
	s, err := NewServer(db, opts)
	if err != nil {
		return nil, err
	}
	sseOpts := []server.SSEOption{
		server.WithSSEEndpoint(firstNonEmpty(opts.SSEPath, "/sse")),
		server.WithMessageEndpoint(firstNonEmpty(opts.MsgPath, "/message")),
	}
	if opts.BaseURL != "" {
		sseOpts = append(sseOpts, server.WithBaseURL(opts.BaseURL))
	}
	return server.NewSSEServer(s, sseOpts...), nil
}

// ensureLoopback 校验 addr 必须是回环地址，避免对外暴露无鉴权的 MCP 端口。
// 例外：开发场景允许显式绑 0.0.0.0，但会打印醒目警告并要求 -allow-public。
func ensureLoopback(addr string) error {
	if addr == "" {
		return nil
	}
	host, _, ok := splitHostPort(addr)
	if !ok {
		return nil
	}
	if isLoopback(host) {
		return nil
	}
	if os.Getenv("PET_MCP_ALLOW_PUBLIC") == "1" {
		fmt.Fprintf(os.Stderr,
			"⚠️  MCP 端口绑定到 %s（非回环）且环境变量 PET_MCP_ALLOW_PUBLIC=1，已放行。\n"+
				"   服务无鉴权，请确保只在可信网络中暴露。\n", addr)
		return nil
	}
	return fmt.Errorf(
		"MCP 服务地址 %s 不是回环地址；为防止无鉴权对外暴露，已拒绝启动。\n"+
			"   如需绑到 0.0.0.0，请设置环境变量 PET_MCP_ALLOW_PUBLIC=1 后再启动", addr)
}

func isLoopback(host string) bool {
	// 注意：host 为空（如 ":8081"）在 Go net.Listen 语义里表示监听所有网卡，
	// 绝不能视为回环，否则会把无鉴权的 MCP 端口暴露到整个局域网。
	switch strings.ToLower(host) {
	case "localhost", "127.0.0.1", "::1", "[::1]":
		return true
	}
	return false
}

func splitHostPort(addr string) (string, string, bool) {
	// 简化版：不处理 IPv6 中括号之外的奇怪 case
	if i := strings.LastIndex(addr, ":"); i >= 0 {
		return addr[:i], addr[i+1:], true
	}
	return "", "", false
}

func firstNonEmpty(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

// printMCPBanner 启动横幅：服务名、地址、SSE 入口、tool 数量。
func printMCPBanner(opts ServerOptions, toolCount int) {
	line := strings.Repeat("═", 78)
	fmt.Println()
	fmt.Printf("\x1b[1m\x1b[36m%s%s%s\n", "╔", line, "╗")
	fmt.Printf("\x1b[1m\x1b[36m║%s%-72s%s║\n", " ",
		"🐾  宠物医院 · MCP (Model Context Protocol)  🐾", "\x1b[0m")
	fmt.Printf("\x1b[1m\x1b[36m║%s%-72s%s║\n", " ",
		"SSE 传输 · "+opts.Name+" v"+opts.Version, "\x1b[0m")
	fmt.Printf("\x1b[1m\x1b[36m╚%s╝\x1b[0m\n", line)
	fmt.Printf("  \x1b[2mSSE 端点：\x1b[0m  http://%s%s\n", opts.Addr, firstNonEmpty(opts.SSEPath, "/sse"))
	fmt.Printf("  \x1b[2mMessage：\x1b[0m  http://%s%s\n", opts.Addr, firstNonEmpty(opts.MsgPath, "/message"))
	if opts.BaseURL != "" {
		fmt.Printf("  \x1b[2mBaseURL：\x1b[0m  %s\n", opts.BaseURL)
	}
	fmt.Printf("  \x1b[2mTools：\x1b[0m    %d 个（详见 tools/list 协议方法或 list_endpoints tool）\n", toolCount)
	fmt.Printf("  \x1b[2mDB：\x1b[0m       本服务复用 REST 的同一 *store.Store 实例\n")
	fmt.Println()
	fmt.Printf("  \x1b[2mClaude Desktop 配置示例（claude_desktop_config.json）：\x1b[0m\n")
	fmt.Printf("    {\n")
	fmt.Printf("      \"mcpServers\": {\n")
	fmt.Printf("        \"pet-hospital\": { \"url\": \"http://%s%s\" }\n", opts.Addr, firstNonEmpty(opts.SSEPath, "/sse"))
	fmt.Printf("      }\n")
	fmt.Printf("    }\n\n")
	fmt.Printf("  \x1b[2m实时访问日志（Ctrl+C 退出）\x1b[0m\n\n")
}
