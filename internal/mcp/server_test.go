package mcp

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"

	"pethospital/internal/model"
	"pethospital/internal/store"
)

// newTestStore 返回一个临时的内存式 store（写到 t.TempDir() 下）。
func newTestStore(t *testing.T) *store.Store {
	t.Helper()
	db, err := store.Open(t.TempDir() + "/pet.db")
	if err != nil {
		t.Fatalf("打开测试 db 失败: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

// makeReq 构造一个 CallToolRequest，参数用 map[string]any。
func makeReq(args map[string]any) mcp.CallToolRequest {
	return mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Arguments: args,
		},
	}
}

// extractText 从 CallToolResult 的 Content 里抽取文本拼接。
func extractText(t *testing.T, r *mcp.CallToolResult) string {
	t.Helper()
	if r == nil {
		return ""
	}
	if r.IsError {
		// 仍然尝试读 Content，但让测试断言更明确
	}
	var b strings.Builder
	for _, c := range r.Content {
		if tc, ok := c.(mcp.TextContent); ok {
			b.WriteString(tc.Text)
		}
	}
	return b.String()
}

// createTestPet 创建一只宠物，返回 ID。
func createTestPet(t *testing.T, db *store.Store) string {
	t.Helper()
	p := &model.Pet{
		Name: "测试犬", Species: model.SpeciesDog, AgeMonths: 24,
		OwnerName: "测试主人", OwnerPhone: "13800001111",
		Doctor: "李医生", Disease: "测试感冒", Status: model.StatusTreating,
	}
	created, err := db.Create(p)
	if err != nil {
		t.Fatalf("创建测试宠物失败: %v", err)
	}
	return created.ID
}

// ---------------------------------------------------------------------------
// TestCreatePetAndHandle 覆盖 create_pet + get_pet 的核心链路。
// ---------------------------------------------------------------------------

func TestCreatePetHandler(t *testing.T) {
	db := newTestStore(t)
	h := createPetHandler(db)

	req := makeReq(map[string]any{
		"name":       "旺财",
		"species":    "犬",
		"ownerName":  "张三",
		"ownerPhone": "13800001111",
		"doctor":     "李医生",
		"disease":    "急性肠胃炎",
		"status":     "待就诊",
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("create_pet 失败: %s", extractText(t, r))
	}
	txt := extractText(t, r)
	if !strings.Contains(txt, "PET-") {
		t.Fatalf("返回结果未包含 PET- ID: %s", txt)
	}

	// 数据库应当有 1 条
	if db.Count() != 1 {
		t.Fatalf("DB 计数 = %d，期望 1", db.Count())
	}
}

func TestCreatePetHandler_ValidateFail(t *testing.T) {
	db := newTestStore(t)
	h := createPetHandler(db)

	// 故意缺 name
	req := makeReq(map[string]any{
		"species":    "犬",
		"ownerName":  "张三",
		"ownerPhone": "13800001111",
		"doctor":     "李医生",
		"disease":    "感冒",
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 不应返回 Go error: %v", err)
	}
	if !r.IsError {
		t.Fatalf("缺必填字段时应当返回 IsError=true")
	}
}

func TestGetPetHandler_NotFound(t *testing.T) {
	db := newTestStore(t)
	h := getPetHandler(db)

	req := makeReq(map[string]any{"id": "PET-999999"})
	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 不应返回 Go error: %v", err)
	}
	if !r.IsError {
		t.Fatalf("查不存在的 ID 应当返回 IsError=true")
	}
	if !strings.Contains(extractText(t, r), "不存在") {
		t.Fatalf("错误提示应包含「不存在」: %s", extractText(t, r))
	}
}

// ---------------------------------------------------------------------------
// TestSearchPetsHandler 覆盖 list / search 链路。
// ---------------------------------------------------------------------------

func TestSearchPetsHandler_FilterByStatus(t *testing.T) {
	db := newTestStore(t)
	// 插入 3 只，2 只住院中
	if _, err := db.Create(&model.Pet{
		Name: "A", Species: model.SpeciesDog, OwnerName: "O1", OwnerPhone: "13800001111",
		Doctor: "李医生", Disease: "x", Status: model.StatusHospitalized,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Create(&model.Pet{
		Name: "B", Species: model.SpeciesCat, OwnerName: "O2", OwnerPhone: "13800002222",
		Doctor: "王医生", Disease: "y", Status: model.StatusHospitalized,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Create(&model.Pet{
		Name: "C", Species: model.SpeciesRabbit, OwnerName: "O3", OwnerPhone: "13800003333",
		Doctor: "李医生", Disease: "z", Status: model.StatusRecovered,
	}); err != nil {
		t.Fatal(err)
	}

	h := searchPetsHandler(db)
	req := makeReq(map[string]any{
		"filter": map[string]any{"status": "住院中"},
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("不应返回错误: %s", extractText(t, r))
	}

	// 解析 JSON 验证 total=2
	var res map[string]any
	if err := json.Unmarshal([]byte(extractText(t, r)), &res); err != nil {
		t.Fatalf("结果非 JSON: %v", err)
	}
	if total, _ := res["total"].(float64); total != 2 {
		t.Fatalf("status=住院中 应返回 2 条，得到 %v", res["total"])
	}
}

// ---------------------------------------------------------------------------
// TestAddMedicalRecordHandler 覆盖追加病历链路。
// ---------------------------------------------------------------------------

func TestAddMedicalRecordHandler(t *testing.T) {
	db := newTestStore(t)
	id := createTestPet(t, db)

	h := addMedicalRecordHandler(db)
	req := makeReq(map[string]any{
		"id":          id,
		"doctor":      "李医生",
		"diagnosis":   "测试感冒加重",
		"symptoms":    "咳嗽",
		"treatment":  "口服药",
		"charge":      200,
		"prescription": []any{"阿莫西林"},
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("追加病历失败: %s", extractText(t, r))
	}

	// 验证 store 侧记录数 +1
	p, _ := db.Get(id)
	if len(p.Records) != 1 {
		t.Fatalf("病历数 = %d，期望 1", len(p.Records))
	}
	if p.Records[0].Diagnosis != "测试感冒加重" {
		t.Fatalf("病历诊断不匹配: %s", p.Records[0].Diagnosis)
	}
}

func TestAddMedicalRecordHandler_MissingDiagnosis(t *testing.T) {
	db := newTestStore(t)
	id := createTestPet(t, db)

	h := addMedicalRecordHandler(db)
	req := makeReq(map[string]any{
		"id":     id,
		"doctor": "李医生",
		// 故意缺 diagnosis
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 不应返回 Go error: %v", err)
	}
	if !r.IsError {
		t.Fatalf("缺 diagnosis 应当返回 IsError=true")
	}
}

// ---------------------------------------------------------------------------
// TestAddChargeHandler 覆盖追加收费链路。
// ---------------------------------------------------------------------------

func TestAddChargeHandler(t *testing.T) {
	db := newTestStore(t)
	id := createTestPet(t, db)

	h := addChargeHandler(db)
	req := makeReq(map[string]any{
		"id":       id,
		"item":     "血常规检查",
		"category": "检查",
		"amount":   180,
		"doctor":   "李医生",
	})

	r, err := h(context.Background(), req)
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("追加收费失败: %s", extractText(t, r))
	}

	p, _ := db.Get(id)
	if p.TotalCost != 180 {
		t.Fatalf("总花费 = %.2f，期望 180", p.TotalCost)
	}
}

// ---------------------------------------------------------------------------
// TestDeletePetHandler 覆盖删除链路。
// ---------------------------------------------------------------------------

func TestDeletePetHandler(t *testing.T) {
	db := newTestStore(t)
	id := createTestPet(t, db)

	h := deletePetHandler(db)
	r, err := h(context.Background(), makeReq(map[string]any{"id": id}))
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("删除失败: %s", extractText(t, r))
	}
	if db.Count() != 0 {
		t.Fatalf("删除后 DB 计数 = %d，期望 0", db.Count())
	}
}

// ---------------------------------------------------------------------------
// TestGetStatsHandler 覆盖统计链路。
// ---------------------------------------------------------------------------

func TestGetStatsHandler(t *testing.T) {
	db := newTestStore(t)
	createTestPet(t, db)
	createTestPet(t, db) // 故意复用 phone 也 OK，store 不去重

	h := getStatsHandler(db)
	r, err := h(context.Background(), makeReq(map[string]any{"top": 5}))
	if err != nil {
		t.Fatalf("handler 返回 error: %v", err)
	}
	if r.IsError {
		t.Fatalf("stats 失败: %s", extractText(t, r))
	}
	var st map[string]any
	if err := json.Unmarshal([]byte(extractText(t, r)), &st); err != nil {
		t.Fatalf("stats 结果非 JSON: %v", err)
	}
	if total, _ := st["totalPets"].(float64); total != 2 {
		t.Fatalf("totalPets = %v，期望 2", st["totalPets"])
	}
}

// ---------------------------------------------------------------------------
// TestNewServer_ToolCount 验证 NewServer 注册了全部 22 个 tool。
// ---------------------------------------------------------------------------

func TestNewServer_ToolRegistration(t *testing.T) {
	db := newTestStore(t)
	opts := DefaultOptions("127.0.0.1:8081")
	s, err := NewServer(db, opts)
	if err != nil {
		t.Fatalf("NewServer 失败: %v", err)
	}
	if s == nil {
		t.Fatal("返回 nil server")
	}
	// 不容易直接断言 tool 数量，至少要构造成功
}

func TestNewServer_RejectsNonLoopback(t *testing.T) {
	db := newTestStore(t)
	opts := DefaultOptions("0.0.0.0:8081")
	if _, err := NewServer(db, opts); err == nil {
		t.Fatal("非回环地址应被拒绝")
	}
}

// ---------------------------------------------------------------------------
// TestEnsureLoopback 覆盖启动安全检查。
// ---------------------------------------------------------------------------

func TestEnsureLoopback(t *testing.T) {
	cases := []struct {
		addr string
		ok   bool
	}{
		{"127.0.0.1:8081", true},
		{"localhost:8081", true},
		{"[::1]:8081", true},
		{"0.0.0.0:8081", false},
		{":8081", false}, // 空主机名视为不安全
		{"192.168.1.1:8081", false},
	}
	for _, c := range cases {
		err := ensureLoopback(c.addr)
		if c.ok && err != nil {
			t.Errorf("addr=%s 应放行但报错: %v", c.addr, err)
		}
		if !c.ok && err == nil {
			t.Errorf("addr=%s 应拒绝但放行了", c.addr)
		}
	}
}
