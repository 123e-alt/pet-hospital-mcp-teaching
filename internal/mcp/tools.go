// internal/mcp/tools.go 定义全部 22 个 MCP tool 的参数 schema。
// tool name 统一 snake_case；必填字段加 mcp.Required()，枚举字段加 mcp.Enum(...)。

package mcp

import (
	"github.com/mark3labs/mcp-go/mcp"

	"pethospital/internal/model"
)

// 工具名常量，便于在 handlers.go 中按名注册与测试时引用。
const (
	ToolHealthCheck         = "health_check"
	ToolGetStats            = "get_stats"
	ToolGetMeta             = "get_meta"
	ToolListEndpoints       = "list_endpoints"
	ToolCreatePet           = "create_pet"
	ToolGetPet              = "get_pet"
	ToolUpdatePet           = "update_pet"
	ToolPatchPet            = "patch_pet"
	ToolDeletePet           = "delete_pet"
	ToolSearchPets          = "search_pets"
	ToolTopSpenders         = "top_spenders"
	ToolListMedicalRecords  = "list_medical_records"
	ToolAddMedicalRecord    = "add_medical_record"
	ToolListCharges         = "list_charges"
	ToolAddCharge           = "add_charge"
	ToolGetPetSummary       = "get_pet_summary"
	ToolBatchCreatePets     = "batch_create_pets"
	ToolBatchDeletePets     = "batch_delete_pets"
	ToolExportPets          = "export_pets"
	ToolCompactDB           = "compact_db"
	ToolSeedDemoData        = "seed_demo_data"
)

// petFields 向一个 tool 追加宠物档案的全部可写字段。
// 用于 create_pet / update_pet。
func petFields(t mcp.Tool, _ bool) {} // 占位（保留接口对称性），实际 tool 定义在 allTools() 里直接构造。

// allTools 返回全部 22 个 tool 定义，供 server 注册。
// handler 由 server.go 在注册时关联。
func allTools() []mcp.Tool {
	return []mcp.Tool{
		// ---------------- 系统 ----------------
		mcp.NewTool(ToolHealthCheck,
			mcp.WithDescription("宠物医院健康检查。返回服务运行状态、运行时长、数据库文件路径、当前档案数量。"),
		),
		mcp.NewTool(ToolGetStats,
			mcp.WithDescription("返回医院经营统计：宠物总数、病历数、收费笔数、总收入、客单价、最高单笔、" +
				"按种类/状态/医生分组的统计、医生收入排行、消费排行榜。"),
			mcp.WithNumber("top", mcp.Description("消费排行榜返回的前 N 名，默认 5")),
		),
		mcp.NewTool(ToolGetMeta,
			mcp.WithDescription("返回枚举字典：宠物种类、就诊状态、收费分类、可排序字段、性别及全部字段说明。"),
		),
		mcp.NewTool(ToolListEndpoints,
			mcp.WithDescription("返回本服务对外暴露的全部 REST 接口清单（含 method/path/desc）。"),
		),

		// ---------------- 宠物 CRUD ----------------
		mcp.NewTool(ToolCreatePet,
			mcp.WithDescription("新增一只宠物档案。ID 由服务端自增生成（PET-000001 形式）。"),
			mcp.WithString("name", mcp.Required(), mcp.Description("宠物姓名")),
			mcp.WithString("species", mcp.Description("种类"), mcp.Enum(model.ValidSpecies...)),
			mcp.WithString("breed", mcp.Description("品种")),
			mcp.WithString("gender", mcp.Description("性别：公/母"), mcp.Enum("公", "母")),
			mcp.WithNumber("ageMonths", mcp.Description("月龄")),
			mcp.WithString("color", mcp.Description("毛色")),
			mcp.WithString("chipNo", mcp.Description("芯片号")),
			mcp.WithString("ownerName", mcp.Required(), mcp.Description("主人姓名")),
			mcp.WithString("ownerPhone", mcp.Required(), mcp.Description("主人电话，如 13800001111")),
			mcp.WithString("ownerAddr", mcp.Description("主人住址")),
			mcp.WithString("doctor", mcp.Required(), mcp.Description("主治医生姓名")),
			mcp.WithString("disease", mcp.Required(), mcp.Description("疾病/主要诊断")),
			mcp.WithString("status", mcp.Description("就诊状态"), mcp.Enum(model.ValidStatus...)),
			mcp.WithString("allergy", mcp.Description("过敏史")),
			mcp.WithString("note", mcp.Description("备注")),
		),
		mcp.NewTool(ToolGetPet,
			mcp.WithDescription("按 ID 查询单个宠物档案，含病历与消费明细。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID，如 PET-000001")),
		),
		mcp.NewTool(ToolUpdatePet,
			mcp.WithDescription("全量更新宠物档案（PUT 语义）。未传字段会被置空。ID 由路径参数指定，不可改。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
			mcp.WithString("name", mcp.Required()),
			mcp.WithString("species", mcp.Enum(model.ValidSpecies...)),
			mcp.WithString("breed"),
			mcp.WithString("gender", mcp.Enum("公", "母")),
			mcp.WithNumber("ageMonths"),
			mcp.WithString("color"),
			mcp.WithString("chipNo"),
			mcp.WithString("ownerName", mcp.Required()),
			mcp.WithString("ownerPhone", mcp.Required()),
			mcp.WithString("ownerAddr"),
			mcp.WithString("doctor", mcp.Required()),
			mcp.WithString("disease", mcp.Required()),
			mcp.WithString("status", mcp.Enum(model.ValidStatus...)),
			mcp.WithString("allergy"),
			mcp.WithString("note"),
		),
		mcp.NewTool(ToolPatchPet,
			mcp.WithDescription("局部更新宠物档案（PATCH 语义）。只传需要修改的字段，未传字段保持不变。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
			mcp.WithString("name"),
			mcp.WithString("species", mcp.Enum(model.ValidSpecies...)),
			mcp.WithString("breed"),
			mcp.WithString("gender", mcp.Enum("公", "母")),
			mcp.WithNumber("ageMonths"),
			mcp.WithString("color"),
			mcp.WithString("chipNo"),
			mcp.WithString("ownerName"),
			mcp.WithString("ownerPhone"),
			mcp.WithString("ownerAddr"),
			mcp.WithString("doctor"),
			mcp.WithString("disease"),
			mcp.WithString("status", mcp.Enum(model.ValidStatus...)),
			mcp.WithString("allergy"),
			mcp.WithString("note"),
		),
		mcp.NewTool(ToolDeletePet,
			mcp.WithDescription("按 ID 删除宠物档案（连同病历与消费明细）。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
		),

		// ---------------- 查询 ----------------
		mcp.NewTool(ToolSearchPets,
			mcp.WithDescription("条件查询宠物列表，支持分页/排序/多维过滤。"+
				"filter 对象内字段全部可选，组合为 AND 关系；q 为全文检索，跨多个字段。"),
			mcp.WithObject("filter",
				mcp.Description("过滤条件对象"),
				mcp.Properties(map[string]any{
					"q":          map[string]any{"type": "string", "description": "全文检索关键词，空格分词 AND"},
					"name":       map[string]any{"type": "string", "description": "宠物姓名模糊匹配"},
					"ownerName":  map[string]any{"type": "string", "description": "主人姓名模糊"},
					"ownerPhone": map[string]any{"type": "string", "description": "电话模糊"},
					"doctor":     map[string]any{"type": "string", "description": "医生姓名模糊"},
					"species":    map[string]any{"type": "string", "description": "种类精确", "enum": model.ValidSpecies},
					"disease":    map[string]any{"type": "string", "description": "疾病模糊"},
					"status":     map[string]any{"type": "string", "description": "状态精确", "enum": model.ValidStatus},
					"minCost":    map[string]any{"type": "number", "description": "最低总花费"},
					"maxCost":    map[string]any{"type": "number", "description": "最高总花费"},
				}),
			),
			mcp.WithString("sortBy", mcp.Description("排序字段"),
				mcp.Enum("id", "name", "ownerName", "species", "doctor",
					"disease", "status", "totalCost", "visitCount", "createdAt", "updatedAt")),
			mcp.WithString("order", mcp.Description("排序方向"), mcp.Enum("asc", "desc")),
			mcp.WithNumber("page", mcp.Description("页码，从 1 开始，默认 1")),
			mcp.WithNumber("pageSize", mcp.Description("每页条数，默认 20，最大 500")),
		),
		mcp.NewTool(ToolTopSpenders,
			mcp.WithDescription("消费排行榜，按在医院总花费降序返回前 N 名宠物。"),
			mcp.WithNumber("limit", mcp.Description("返回前 N 名，默认 5")),
		),

		// ---------------- 子资源 ----------------
		mcp.NewTool(ToolListMedicalRecords,
			mcp.WithDescription("查询指定宠物的全部历史病历。返回病历数组与拼接后的病历摘要文本。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
		),
		mcp.NewTool(ToolAddMedicalRecord,
			mcp.WithDescription("为指定宠物追加一条历史病历。visitDate 缺省取今天。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
			mcp.WithString("visitDate", mcp.Description("就诊日期 YYYY-MM-DD，默认今天")),
			mcp.WithString("doctor", mcp.Required(), mcp.Description("接诊医生")),
			mcp.WithString("diagnosis", mcp.Required(), mcp.Description("诊断结论")),
			mcp.WithString("symptoms", mcp.Description("主诉/症状")),
			mcp.WithString("treatment", mcp.Description("处置方案")),
			mcp.WithArray("prescription", mcp.Description("处方列表"),
				mcp.Items(map[string]any{"type": "string"})),
			mcp.WithNumber("weightKg", mcp.Description("就诊时体重 kg")),
			mcp.WithNumber("temperature", mcp.Description("体温 ℃")),
			mcp.WithString("followUp", mcp.Description("复诊建议")),
			mcp.WithNumber("charge", mcp.Description("本次费用，元")),
		),
		mcp.NewTool(ToolListCharges,
			mcp.WithDescription("查询指定宠物的全部消费明细。返回消费数组、累计总花费及按分类汇总。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
		),
		mcp.NewTool(ToolAddCharge,
			mcp.WithDescription("为指定宠物追加一笔收费，自动累加到宠物总花费。date 缺省取今天。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
			mcp.WithString("item", mcp.Required(), mcp.Description("收费项目，如「血常规检查」")),
			mcp.WithString("category", mcp.Required(), mcp.Description("收费分类"),
				mcp.Enum("检查", "药品", "手术", "住院", "疫苗", "护理", "其他")),
			mcp.WithNumber("amount", mcp.Required(), mcp.Description("金额（元）")),
			mcp.WithString("doctor", mcp.Description("经手医生")),
			mcp.WithString("date", mcp.Description("收费日期 YYYY-MM-DD，默认今天")),
			mcp.WithString("note", mcp.Description("备注")),
		),
		mcp.NewTool(ToolGetPetSummary,
			mcp.WithDescription("返回单只宠物的费用与就诊汇总：总花费、就诊次数、消费笔数、按分类/医生分组的花费、"+
				"最高单笔、平均每次就诊花费、首次与最近一次就诊日期、病历摘要文本。"),
			mcp.WithString("id", mcp.Required(), mcp.Description("宠物档案 ID")),
		),

		// ---------------- 批量 / 导出 ----------------
		mcp.NewTool(ToolBatchCreatePets,
			mcp.WithDescription("批量新增宠物档案。每条 item 至少包含 name/ownerName/ownerPhone/doctor/disease。"),
			mcp.WithArray("items", mcp.Required(), mcp.Description("宠物档案数组"),
				mcp.Items(map[string]any{
					"type": "object",
					"properties": map[string]any{
						"name":       map[string]any{"type": "string"},
						"species":    map[string]any{"type": "string"},
						"ownerName":  map[string]any{"type": "string"},
						"ownerPhone": map[string]any{"type": "string"},
						"doctor":     map[string]any{"type": "string"},
						"disease":    map[string]any{"type": "string"},
					},
				})),
		),
		mcp.NewTool(ToolBatchDeletePets,
			mcp.WithDescription("批量删除宠物档案，返回实际删除的 ID 列表与未找到的数量。"),
			mcp.WithArray("ids", mcp.Required(), mcp.Description("待删除的 ID 数组"),
				mcp.Items(map[string]any{"type": "string"})),
		),
		mcp.NewTool(ToolExportPets,
			mcp.WithDescription("导出全部宠物档案。format=csv 返回 CSV 文本（首行为表头），"+
				"format=json 返回 JSON 数组。"),
			mcp.WithString("format", mcp.Description("导出格式"), mcp.Enum("json", "csv")),
		),

		// ---------------- 管理 ----------------
		mcp.NewTool(ToolCompactDB,
			mcp.WithDescription("手动压实数据库文件，清理日志中的删除/更新垃圾，返回压实前后文件大小。"),
		),
		mcp.NewTool(ToolSeedDemoData,
			mcp.WithDescription("写入演示数据。force=true 时强制覆盖；count 可指定额外生成的随机档案数（0-50000，或 all=1000）。"),
			mcp.WithBoolean("force", mcp.Description("数据库非空时是否强制写入演示数据")),
			mcp.WithString("count", mcp.Description("额外随机档案数（0-50000 整数或 all），默认 0 只写 8 条手工精选")),
		),
	}
}
