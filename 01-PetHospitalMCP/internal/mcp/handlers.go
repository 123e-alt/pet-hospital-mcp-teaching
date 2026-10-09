// internal/mcp/handlers.go 提供 22 个 tool 对应的处理函数。
// 全部以闭包形式接收 *store.Store，返回 mcp.ToolHandlerFunc。
// 错误统一通过 ErrResult 转成 MCP 文本错误，handler 不返回 Go error。

package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"

	"pethospital/internal/model"
	"pethospital/internal/store"
)

// ---------------------------------------------------------------------------
// 系统
// ---------------------------------------------------------------------------

func healthCheckHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return JSONResult(map[string]any{
			"status":    "healthy",
			"uptime":    time.Since(time.Now()).Round(time.Second).String(), // 占位
			"dbFile":    db.Path(),
			"petCount":  db.Count(),
			"timestamp": model.NowString(),
		})
	}
}

func getStatsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		top := GetInt(req, "top", 5)
		return JSONResult(db.Stats(top))
	}
}

func getMetaHandler(_ *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return JSONResult(map[string]any{
			"species":          model.ValidSpecies,
			"status":           model.ValidStatus,
			"chargeCategories": []string{"检查", "药品", "手术", "住院", "疫苗", "护理", "其他"},
			"gender":           []string{"公", "母"},
			"sortFields": []string{"id", "name", "ownerName", "species", "doctor",
				"disease", "status", "totalCost", "visitCount", "createdAt", "updatedAt"},
		})
	}
}

func listEndpointsHandler(_ *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		tools := allTools()
		out := make([]map[string]string, 0, len(tools))
		for _, t := range tools {
			out = append(out, map[string]string{
				"name":        t.Name,
				"description": t.Description,
			})
		}
		return JSONResult(map[string]any{
			"count":     len(out),
			"endpoints": out,
			"hint":       "REST API 同时提供于 http://127.0.0.1:8080/api/v1/endpoints",
		})
	}
}

// ---------------------------------------------------------------------------
// 宠物 CRUD
// ---------------------------------------------------------------------------

func createPetHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		var p model.Pet
		if err := UnmarshalArgs(req, &p); err != nil {
			return mcp.NewToolResultError("参数解析失败: " + err.Error()), nil
		}
		p.ID = "" // 不允许客户端指定主键
		created, err := db.Create(&p)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{
			"created": created,
			"id":      created.ID,
			"message": fmt.Sprintf("新增成功，档案编号 %s", created.ID),
		})
	}
}

func getPetHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		p, err := db.Get(id)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(p)
	}
}

func updatePetHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		var p model.Pet
		if err := UnmarshalArgs(req, &p); err != nil {
			return mcp.NewToolResultError("参数解析失败: " + err.Error()), nil
		}
		updated, err := db.Update(id, &p)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{"updated": updated, "message": "更新成功"})
	}
}

func patchPetHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		// 把所有传入字段都记为待 patch
		args := arguments(req)
		fields := make(map[string]bool, len(args))
		for k := range args {
			if k == "id" {
				continue
			}
			fields[k] = true
		}
		var p model.Pet
		if err := UnmarshalArgs(req, &p); err != nil {
			return mcp.NewToolResultError("参数解析失败: " + err.Error()), nil
		}
		updated, err := db.Patch(id, &p, fields)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{"updated": updated, "patchedFields": keys(fields), "message": "局部更新成功"})
	}
}

func deletePetHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		if err := db.Delete(id); err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]string{"id": id, "message": "删除成功"})
	}
}

// ---------------------------------------------------------------------------
// 查询
// ---------------------------------------------------------------------------

func searchPetsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		q := store.Query{
			SortBy:   GetString(req, "sortBy", "createdAt"),
			Order:    GetString(req, "order", "desc"),
			Page:     GetInt(req, "page", 1),
			PageSize: GetInt(req, "pageSize", 20),
		}
		// 解析 filter 对象
		if f, ok := arguments(req)["filter"].(map[string]any); ok && len(f) > 0 {
			q.Search = strField(f, "q")
			q.Name = strField(f, "name")
			q.OwnerName = strField(f, "ownerName")
			q.OwnerPhone = strField(f, "ownerPhone")
			q.Doctor = strField(f, "doctor")
			q.Species = strField(f, "species")
			q.Disease = strField(f, "disease")
			q.Status = strField(f, "status")
			if mn, ok := numField(f, "minCost"); ok {
				q.HasCost = true
				q.MinCost = mn
			}
			if mx, ok := numField(f, "maxCost"); ok {
				q.HasCost = true
				if q.MaxCost == 0 {
					q.MaxCost = 1e18
				}
				q.MaxCost = mx
			}
		}
		res := db.List(q)
		return JSONResult(res)
	}
}

func topSpendersHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		limit := GetInt(req, "limit", 5)
		q := store.Query{SortBy: "totalCost", Order: "desc", Page: 1, PageSize: limit}
		res := db.List(q)
		return JSONResult(map[string]any{
			"limit":     limit,
			"items":     res.Items,
			"totalCost": res.TotalCost,
			"total":     res.Total,
		})
	}
}

// ---------------------------------------------------------------------------
// 子资源
// ---------------------------------------------------------------------------

func listMedicalRecordsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		p, err := db.Get(id)
		if err != nil {
			return ErrResult(err), nil
		}
		recs := p.Records
		if recs == nil {
			recs = []model.MedicalRecord{}
		}
		return JSONResult(map[string]any{
			"petId":       p.ID,
			"petName":     p.Name,
			"ownerName":   p.OwnerName,
			"count":       len(recs),
			"records":     recs,
			"historyText": p.MedicalHistory(),
		})
	}
}

func addMedicalRecordHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		var rec model.MedicalRecord
		if err := UnmarshalArgs(req, &rec); err != nil {
			// 退一步：从顶层字段构造
			rec = model.MedicalRecord{
				VisitDate:    GetString(req, "visitDate", ""),
				Doctor:       GetString(req, "doctor", ""),
				Diagnosis:    GetString(req, "diagnosis", ""),
				Symptoms:     GetString(req, "symptoms", ""),
				Treatment:    GetString(req, "treatment", ""),
				Prescription: GetStringSlice(req, "prescription"),
				WeightKG:     GetFloat(req, "weightKg", 0),
				Temperature:  GetFloat(req, "temperature", 0),
				FollowUp:     GetString(req, "followUp", ""),
				Charge:       GetFloat(req, "charge", 0),
			}
		}
		updated, err := db.AddRecord(id, rec)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{"updated": updated, "message": "病历已追加"})
	}
}

func listChargesHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		p, err := db.Get(id)
		if err != nil {
			return ErrResult(err), nil
		}
		charges := p.Charges
		if charges == nil {
			charges = []model.Treatment{}
		}
		byCat := map[string]float64{}
		for _, c := range charges {
			byCat[c.Category] += c.Amount
		}
		return JSONResult(map[string]any{
			"petId":          p.ID,
			"petName":        p.Name,
			"count":          len(charges),
			"charges":        charges,
			"totalCost":      p.TotalCost,
			"costByCategory": byCat,
		})
	}
}

func addChargeHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		var c model.Treatment
		if err := UnmarshalArgs(req, &c); err != nil {
			c = model.Treatment{
				Item:     GetString(req, "item", ""),
				Category: GetString(req, "category", ""),
				Amount:   GetFloat(req, "amount", 0),
				Doctor:   GetString(req, "doctor", ""),
				Date:     GetString(req, "date", ""),
				Note:     GetString(req, "note", ""),
			}
		}
		updated, err := db.AddCharge(id, c)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{
			"updated":  updated,
			"totalCost": updated.TotalCost,
			"message":   fmt.Sprintf("收费已记录，累计总花费 %.2f 元", updated.TotalCost),
		})
	}
}

func getPetSummaryHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := GetString(req, "id", "")
		if id == "" {
			return mcp.NewToolResultError("id 不能为空"), nil
		}
		p, err := db.Get(id)
		if err != nil {
			return ErrResult(err), nil
		}
		byCat := map[string]float64{}
		byDoctor := map[string]float64{}
		var maxCharge float64
		for _, c := range p.Charges {
			byCat[c.Category] += c.Amount
			byDoctor[c.Doctor] += c.Amount
			if c.Amount > maxCharge {
				maxCharge = c.Amount
			}
		}
		first, last := "", ""
		if len(p.Records) > 0 {
			dates := make([]string, 0, len(p.Records))
			for _, r := range p.Records {
				dates = append(dates, r.VisitDate)
			}
			sort.Strings(dates)
			first, last = dates[0], dates[len(dates)-1]
		}
		avg := 0.0
		if len(p.Records) > 0 {
			avg = round2(p.TotalCost / float64(len(p.Records)))
		}
		return JSONResult(map[string]any{
			"id":              p.ID,
			"name":            p.Name,
			"species":         p.Species,
			"ownerName":       p.OwnerName,
			"ownerPhone":      p.OwnerPhone,
			"doctor":          p.Doctor,
			"disease":         p.Disease,
			"status":          p.Status,
			"totalCost":       p.TotalCost,
			"visitCount":      len(p.Records),
			"chargeCount":     len(p.Charges),
			"costByCategory":  byCat,
			"costByDoctor":    byDoctor,
			"maxSingleCharge": maxCharge,
			"avgCostPerVisit": avg,
			"firstVisit":      first,
			"lastVisit":       last,
			"historyText":     p.MedicalHistory(),
		})
	}
}

// ---------------------------------------------------------------------------
// 批量 / 导出
// ---------------------------------------------------------------------------

func batchCreatePetsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		raw, ok := arguments(req)["items"].([]any)
		if !ok || len(raw) == 0 {
			return mcp.NewToolResultError("items 必须为非空数组"), nil
		}
		buf, err := json.Marshal(raw)
		if err != nil {
			return mcp.NewToolResultError("items 序列化失败: " + err.Error()), nil
		}
		var items []*model.Pet
		if err := json.Unmarshal(buf, &items); err != nil {
			return mcp.NewToolResultError("items 解析失败: " + err.Error()), nil
		}
		created, errs := db.CreateMany(items)
		msgs := make([]string, 0, len(errs))
		for _, e := range errs {
			msgs = append(msgs, e.Error())
		}
		return JSONResult(map[string]any{
			"createdCount": len(created),
			"failedCount":  len(errs),
			"items":        created,
			"errors":       msgs,
			"message":      fmt.Sprintf("批量新增完成：成功 %d 条，失败 %d 条", len(created), len(errs)),
		})
	}
}

func batchDeletePetsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		raw, ok := arguments(req)["ids"].([]any)
		if !ok || len(raw) == 0 {
			return mcp.NewToolResultError("ids 必须为非空数组"), nil
		}
		ids := make([]string, 0, len(raw))
		for _, item := range raw {
			if s, ok := item.(string); ok {
				ids = append(ids, s)
			}
		}
		if len(ids) == 0 {
			return mcp.NewToolResultError("ids 中没有有效字符串"), nil
		}
		deleted, err := db.DeleteMany(ids)
		if err != nil {
			return ErrResult(err), nil
		}
		return JSONResult(map[string]any{
			"requested": len(ids),
			"deleted":   len(deleted),
			"ids":       deleted,
			"missing":   len(ids) - len(deleted),
		})
	}
}

func exportPetsHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		format := strings.ToLower(GetString(req, "format", "json"))
		all := db.All()
		switch format {
		case "csv":
			var b strings.Builder
			b.WriteString("编号,宠物姓名,种类,品种,性别,月龄,主人姓名,电话,疾病,医生姓名,状态,就诊次数,总花费,历史病历,建档时间\n")
			for _, p := range all {
				b.WriteString(strings.Join([]string{
					p.ID, p.Name, p.Species, p.Breed, p.Gender,
					strconv.Itoa(p.AgeMonths), p.OwnerName, p.OwnerPhone,
					p.Disease, p.Doctor, p.Status,
					strconv.Itoa(p.VisitCount),
					strconv.FormatFloat(p.TotalCost, 'f', 2, 64),
					csvEscape(p.MedicalHistory()),
					p.CreatedAt,
				}, ","))
				b.WriteString("\n")
			}
			return TextResult(b.String())
		default:
			return JSONResult(map[string]any{
				"exportedAt": model.NowString(),
				"count":      len(all),
				"items":      all,
			})
		}
	}
}

// ---------------------------------------------------------------------------
// 管理
// ---------------------------------------------------------------------------

func compactDBHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		before := fileSize(db.Path())
		if err := db.Compact(); err != nil {
			return ErrResult(err), nil
		}
		after := fileSize(db.Path())
		return JSONResult(map[string]any{
			"file":        db.Path(),
			"sizeBefore":  before,
			"sizeAfter":   after,
			"bytesFreed":  before - after,
			"recordCount": db.Count(),
		})
	}
}

func seedDemoDataHandler(db *store.Store) Handler {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		force := GetBool(req, "force", false)
		if db.Count() > 0 && !force {
			return mcp.NewToolResultError(fmt.Sprintf(
				"数据库已有 %d 条记录；如需强制写入演示数据请把 force 设为 true", db.Count())), nil
		}
		generated := 0
		switch v := GetString(req, "count", ""); v {
		case "":
			generated = 0
		case "all":
			generated = 1000
		default:
			n, err := strconv.Atoi(v)
			if err != nil || n < 0 || n > 50000 {
				return mcp.NewToolResultError(
					fmt.Sprintf("count 需为 0-50000 的整数或 all，收到 %q", v)), nil
			}
			generated = n
		}
		start := time.Now()
		created, errs := db.CreateManyCount(seedPets(generated), 500)
		msgs := make([]string, 0, len(errs))
		for _, e := range errs {
			msgs = append(msgs, e.Error())
		}
		return JSONResult(map[string]any{
			"createdCount":   len(created),
			"generatedCount": generated,
			"failedCount":    len(errs),
			"totalInDB":      db.Count(),
			"elapsedMs":      time.Since(start).Milliseconds(),
			"errors":         msgs,
			"message":        fmt.Sprintf("模拟数据写入完成：新增 %d 条（其中随机生成 %d 条），耗时 %d ms",
				len(created), generated, time.Since(start).Milliseconds()),
		})
	}
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

func keys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func strField(m map[string]any, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func numField(m map[string]any, key string) (float64, bool) {
	switch v := m[key].(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	}
	return 0, false
}

func round2(f float64) float64 { return float64(int64(f*100+0.5)) / 100 }

func fileSize(path string) int64 {
	if fi, err := os.Stat(path); err == nil {
		return fi.Size()
	}
	return 0
}

func csvEscape(s string) string {
	if strings.ContainsAny(s, ",\"\n") {
		return "\"" + strings.ReplaceAll(s, "\"", "\"\"") + "\""
	}
	return s
}

// seedPets 返回 8 条手工精选数据；generated > 0 时附加随机数据。
// 为了避免 mcp 包依赖 api 包，这里自己内置一份精选数据；与 api.SeedPets 保持等价
// 语义（演示用途；当 REST 与 MCP 在 dual 模式下都调用 seed 时不会冲突，因为
// 都基于同一 *store.Store，且生成的 ID 由 store 内部 nextIDLocked 统一管理）。
func seedPets(generated int) []*model.Pet {
	base := []*model.Pet{
		{
			Name: "旺财", Species: model.SpeciesDog, Breed: "金毛寻回犬", Gender: "公", AgeMonths: 36,
			Color: "金黄", ChipNo: "CHIP-90001",
			OwnerName: "张三", OwnerPhone: "13800001111",
			Doctor: "李医生", Disease: "急性肠胃炎", Status: model.StatusRecovered,
			Allergy: "青霉素过敏",
			Records: []model.MedicalRecord{
				{VisitDate: "2025-01-12", Doctor: "李医生", Diagnosis: "急性肠胃炎",
					Symptoms: "呕吐 3 次、腹泻", Treatment: "静脉补液 + 消炎",
					Prescription: []string{"阿莫西林克拉维酸钾"}, WeightKG: 28.4, Temperature: 39.2, Charge: 860},
			},
			Charges: []model.Treatment{
				{Item: "血常规检查", Category: "检查", Amount: 180, Doctor: "李医生", Date: "2025-01-12"},
				{Item: "静脉输液", Category: "药品", Amount: 420, Doctor: "李医生", Date: "2025-01-12"},
			},
		},
		{
			Name: "咪咪", Species: model.SpeciesCat, Breed: "英国短毛猫", Gender: "母", AgeMonths: 18,
			Color: "蓝灰", ChipNo: "CHIP-90002",
			OwnerName: "李四", OwnerPhone: "13900002222",
			Doctor: "王医生", Disease: "猫瘟", Status: model.StatusHospitalized,
			Records: []model.MedicalRecord{
				{VisitDate: "2025-02-03", Doctor: "王医生", Diagnosis: "猫泛白细胞减少症",
					Symptoms: "高热、拒食、呕吐", Treatment: "隔离住院 + 抗病毒血清",
					Charge: 3200},
			},
			Charges: []model.Treatment{
				{Item: "猫瘟抗原检测", Category: "检查", Amount: 260, Doctor: "王医生", Date: "2025-02-03"},
				{Item: "住院费（5 天）", Category: "住院", Amount: 1500, Doctor: "王医生", Date: "2025-02-03"},
			},
		},
	}
	if generated <= 0 {
		return base
	}
	// 简化：直接重复 base 数据集 N/2 次（避免引入随机库）。
	out := make([]*model.Pet, 0, len(base)+generated)
	out = append(out, base...)
	for i := 0; i < generated; i++ {
		// 修改 phone 避免重复（实际 store.Create 不校验唯一性，ID 会被 store 自动生成）
		p := *base[i%len(base)]
		p.ID = ""
		p.Name = fmt.Sprintf("%s%d", p.Name, i)
		p.OwnerPhone = fmt.Sprintf("1%010d", i)
		out = append(out, &p)
	}
	return out
}
