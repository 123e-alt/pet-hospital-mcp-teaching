# -*- coding: utf-8 -*-
"""生成《2026年10月工资表》Excel 工作簿"""
import random
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

random.seed(20261102)

OUT = r'C:\Users\qq\Desktop\LLM\04-agent\xAgent\2026年10月工资表.xlsx'

wb = Workbook()

# ===================== 样式 =====================
THIN = Side(style='thin', color='999999')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill('solid', fgColor='4472C4')
HEAD_FONT = Font(name='微软雅黑', size=10, bold=True, color='FFFFFF')
TITLE_FONT = Font(name='微软雅黑', size=16, bold=True)
SUB_FONT = Font(name='微软雅黑', size=10, color='595959')
BODY_FONT = Font(name='微软雅黑', size=10)
BOLD_FONT = Font(name='微软雅黑', size=10, bold=True)
MONEY_FMT = '#,##0.00'

# ===================== 数据 =====================
emp_data = [
    # 姓名, 部门, 岗位, 基本工资, 绩效工资, 岗位津贴, 加班费, 全勤奖
    ('王志强', '综合办公室', '主任',        12000, 6000, 2500, 0,    500),
    ('李晓梅', '综合办公室', '行政专员',     6800, 2800, 800,  320,  500),
    ('张宇航', '综合办公室', '文员',         5500, 2000, 600,  0,    500),
    ('陈建国', '财务部',     '财务经理',     11000, 5000, 2000, 0,    500),
    ('刘思远', '财务部',     '会计',         7600, 3200, 900,  0,    500),
    ('赵一鸣', '财务部',     '出纳',         6200, 2400, 700,  580,  500),
    ('周文慧', '人力资源部', '人力资源经理', 10500, 4800, 1800, 0,    500),
    ('孙浩然', '人力资源部', '招聘专员',     6400, 2600, 700,  260,  500),
    ('吴嘉怡', '人力资源部', '薪酬专员',     6900, 2700, 800,  0,    500),
    ('马云飞', '技术部',     '技术总监',     15000, 8000, 3000, 0,    500),
    ('郑晓东', '技术部',     '高级工程师',   12500, 6500, 2200, 1450, 500),
    ('何雨欣', '技术部',     '工程师',       9200, 4000, 1200, 0,    300),
    ('许志明', '技术部',     '开发工程师',   8800, 3800, 1100, 960,  500),
    ('林书瑶', '市场部',     '市场经理',     10800, 5200, 1900, 0,    500),
    ('黄子谦', '市场部',     '市场专员',     6300, 2500, 700,  640,  500),
    ('徐如月', '市场部',     '品牌策划',     7100, 2900, 900,  0,    500),
    ('高远航', '销售部',     '销售经理',     10000, 9000, 2000, 0,    500),
    ('谢伟霆', '销售部',     '客户经理',     7200, 7500, 1000, 380,  500),
    ('梅晓琳', '销售部',     '销售助理',     5800, 4200, 600,  0,    300),
    ('韩明轩', '客服部',     '客服主管',     8200, 3500, 1000, 0,    500),
    ('范雨桐', '客服部',     '客服专员',     5600, 2200, 600,  540,  500),
    ('潘书宁', '客服部',     '客服专员',     5600, 2100, 600,  0,    500),
    ('罗嘉恒', '质检部',     '质检员',       6100, 2400, 700,  300,  500),
    ('崔晨阳', '质检部',     '质检员',       5900, 2300, 650,  0,    300),
]

SS_RATE = 0.105      # 个人社保公积金（养老8%+医疗2%+失业0.5%）+公积金另计
HF_RATE = 0.12       # 个人公积金
TAX_THRESHOLD = 5000 # 个税起征点

HEADERS = ['序号', '姓名', '部门', '岗位', '基本工资', '绩效工资', '岗位津贴',
           '加班费', '全勤奖', '应发合计', '个人社保', '个人公积金', '个税',
           '其他扣款', '实发工资']


def calc_tax(taxable):
    """按月度综合所得税率表简算"""
    if taxable <= 0:
        return 0
    brackets = [
        (3000, 0.03, 0), (12000, 0.10, 210), (25000, 0.20, 1410),
        (35000, 0.25, 2660), (55000, 0.30, 4410), (80000, 0.35, 7160),
        (float('inf'), 0.45, 15160),
    ]
    for cap, rate, deduct in brackets:
        if taxable <= cap:
            return max(0, round(taxable * rate - deduct, 2))
    return 0


# ===================== Sheet1 工资明细 =====================
ws = wb.active
ws.title = '工资明细表'

ws.merge_cells('A1:O1')
ws['A1'] = '2026年10月工资表'
ws['A1'].font = TITLE_FONT
ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
ws.row_dimensions[1].height = 30

ws.merge_cells('A2:O2')
ws['A2'] = '编制单位：××市××区综合管理办公室　　　　工资所属期：2026-10-01 至 2026-10-31　　　　币种：人民币（元）'
ws['A2'].font = SUB_FONT
ws['A2'].alignment = Alignment(horizontal='left', vertical='center')
ws.row_dimensions[2].height = 20

HEAD_ROW = 3
for col, h in enumerate(HEADERS, start=1):
    c = ws.cell(row=HEAD_ROW, column=col, value=h)
    c.font = HEAD_FONT
    c.fill = HEAD_FILL
    c.border = BORDER
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
ws.row_dimensions[HEAD_ROW].height = 28

total = dict.fromkeys(
    ['basic', 'perf', 'allow', 'ot', 'full', 'gross', 'ss', 'hf', 'tax', 'other', 'net'], 0)

row = HEAD_ROW + 1
for idx, (name, dept, post, basic, perf, allow, ot, full) in enumerate(emp_data, start=1):
    gross = basic + perf + allow + ot + full
    ss = round(basic * SS_RATE, 2)
    hf = round(basic * HF_RATE, 2)
    taxable = gross - ss - hf - TAX_THRESHOLD
    tax = calc_tax(taxable)
    other = random.choice([0, 0, 0, 0, 50, 120, 200])   # 迟到扣款等
    net = round(gross - ss - hf - tax - other, 2)

    values = [idx, name, dept, post, basic, perf, allow, ot, full,
              gross, ss, hf, tax, other, net]
    for col, v in enumerate(values, start=1):
        c = ws.cell(row=row, column=col, value=v)
        c.font = BODY_FONT
        c.border = BORDER
        if col >= 5:
            c.number_format = MONEY_FMT
            c.alignment = Alignment(horizontal='right', vertical='center')
        else:
            c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[row].height = 20

    for k, v in zip(total,
                    [basic, perf, allow, ot, full, gross, ss, hf, tax, other, net]):
        total[k] += v
    row += 1

# 合计行
c = ws.cell(row=row, column=1, value='合计')
ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
c.font = BOLD_FONT
c.alignment = Alignment(horizontal='center', vertical='center')
c.border = BORDER
for col in range(2, 5):
    ws.cell(row=row, column=col).border = BORDER

sum_values = [None] * 4 + [total['basic'], total['perf'], total['allow'], total['ot'],
                           total['full'], total['gross'], total['ss'], total['hf'],
                           total['tax'], total['other'], total['net']]
for col in range(1, 16):
    c = ws.cell(row=row, column=col)
    if sum_values[col - 1] is not None:
        c.value = round(sum_values[col - 1], 2)
        c.number_format = MONEY_FMT
        c.alignment = Alignment(horizontal='right', vertical='center')
    c.font = BOLD_FONT
    c.border = BORDER
    c.fill = PatternFill('solid', fgColor='DCE6F1')
ws.row_dimensions[row].height = 22

TOTAL_ROW = row

# 说明
row += 2
notes = [
    '说明：',
    '1. 应发合计 = 基本工资 + 绩效工资 + 岗位津贴 + 加班费 + 全勤奖。',
    '2. 个人社保按基本工资的10.5%计提（养老8%、医疗2%、失业0.5%）；个人公积金按基本工资的12%计提。',
    '3. 个税按月度综合所得预扣率表计算，起征点5,000元/月，应纳税所得额 = 应发合计 − 个人社保 − 个人公积金 − 5,000。',
    '4. 实发工资 = 应发合计 − 个人社保 − 个人公积金 − 个税 − 其他扣款。',
    '5. 其他扣款含迟到早退、请假等扣减；本表数据为示例填充，实际发放以财务核定为准。',
]
for n in notes:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=15)
    c = ws.cell(row=row, column=1, value=n)
    c.font = Font(name='微软雅黑', size=9, color='595959') if n != '说明：' else BOLD_FONT
    c.alignment = Alignment(horizontal='left', vertical='center')
    row += 1

# 签字栏
row += 1
signs = ['制表人：__________', '审核人：__________', '部门负责人：__________', '财务负责人：__________']
ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=8)
ws.merge_cells(start_row=row, start_column=9, end_row=row, end_column=12)
ws.merge_cells(start_row=row, start_column=13, end_row=row, end_column=15)
for i, s in enumerate(signs):
    col = [1, 5, 9, 13][i]
    c = ws.cell(row=row, column=col, value=s)
    c.font = BODY_FONT
    c.alignment = Alignment(horizontal='center', vertical='center')

# 列宽
widths = [6, 10, 14, 14, 12, 12, 11, 10, 10, 13, 11, 12, 10, 11, 13]
for i, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(i)].width = w

ws.freeze_panes = 'E4'
ws.auto_filter.ref = f'A{HEAD_ROW}:O{TOTAL_ROW - 1}'

# ===================== Sheet2 部门汇总 =====================
ws2 = wb.create_sheet('部门汇总')

ws2.merge_cells('A1:F1')
ws2['A1'] = '2026年10月工资部门汇总表'
ws2['A1'].font = TITLE_FONT
ws2['A1'].alignment = Alignment(horizontal='center', vertical='center')
ws2.row_dimensions[1].height = 28

h2 = ['部门', '人数', '应发合计', '代扣合计', '实发合计', '人均实发']
for col, h in enumerate(h2, start=1):
    c = ws2.cell(row=3, column=col, value=h)
    c.font = HEAD_FONT
    c.fill = HEAD_FILL
    c.border = BORDER
    c.alignment = Alignment(horizontal='center', vertical='center')
ws2.row_dimensions[3].height = 26

# 汇总
dept_stat = {}
for row_i in range(HEAD_ROW + 1, TOTAL_ROW):
    dept = ws.cell(row=row_i, column=3).value
    gross = ws.cell(row=row_i, column=10).value
    ss = ws.cell(row=row_i, column=11).value
    hf = ws.cell(row=row_i, column=12).value
    tax = ws.cell(row=row_i, column=13).value
    other = ws.cell(row=row_i, column=14).value
    net = ws.cell(row=row_i, column=15).value
    d = dept_stat.setdefault(dept, [0, 0, 0, 0])
    d[0] += 1
    d[1] += gross
    d[2] += ss + hf + tax + other
    d[3] += net

r2 = 4
for dept, (cnt, gross, deduct, net) in sorted(dept_stat.items(),
                                              key=lambda x: -x[1][3]):
    vals = [dept, cnt, round(gross, 2), round(deduct, 2), round(net, 2),
            round(net / cnt, 2)]
    for col, v in enumerate(vals, start=1):
        c = ws2.cell(row=r2, column=col, value=v)
        c.font = BODY_FONT
        c.border = BORDER
        if col >= 3:
            c.number_format = MONEY_FMT
            c.alignment = Alignment(horizontal='right', vertical='center')
        else:
            c.alignment = Alignment(horizontal='center', vertical='center')
    ws2.row_dimensions[r2].height = 20
    r2 += 1

# 合计
ws2.cell(row=r2, column=1, value='合计')
ws2.cell(row=r2, column=2, value=f'=SUM(B4:B{r2 - 1})')
ws2.cell(row=r2, column=3, value=f'=SUM(C4:C{r2 - 1})')
ws2.cell(row=r2, column=4, value=f'=SUM(D4:D{r2 - 1})')
ws2.cell(row=r2, column=5, value=f'=SUM(E4:E{r2 - 1})')
ws2.cell(row=r2, column=6, value=f'=E{r2}/B{r2}')
for col in range(1, 7):
    c = ws2.cell(row=r2, column=col)
    c.font = BOLD_FONT
    c.border = BORDER
    c.fill = PatternFill('solid', fgColor='DCE6F1')
    if col >= 3:
        c.number_format = MONEY_FMT
        c.alignment = Alignment(horizontal='right', vertical='center')
    else:
        c.alignment = Alignment(horizontal='center', vertical='center')
ws2.row_dimensions[r2].height = 22

for i, w in enumerate([16, 10, 16, 16, 16, 14], start=1):
    ws2.column_dimensions[get_column_letter(i)].width = w
ws2.freeze_panes = 'A4'

wb.save(OUT)
print('已生成：', OUT)
print(f'员工数：{len(emp_data)}  部门数：{len(dept_stat)}')
print(f'应发合计：{total["gross"]:,.2f}  实发合计：{total["net"]:,.2f}')
