# -*- coding: utf-8 -*-
"""生成《2027年元旦放假安排通知》PPT"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUT = r'C:\Users\qq\Desktop\LLM\04-agent\xAgent\2027年元旦放假安排通知.pptx'

# ===== 配色 =====
NAVY    = RGBColor(0x1B, 0x2A, 0x4A)
BLUE    = RGBColor(0x2E, 0x5C, 0x9E)
LIGHT   = RGBColor(0xE8, 0xEF, 0xF9)
ACCENT  = RGBColor(0xD9, 0x53, 0x1E)
GRAY    = RGBColor(0x59, 0x59, 0x59)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
BG      = RGBColor(0xF7, 0xF9, 0xFC)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height


def add_slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    return s


def txt(slide, text, x, y, w, h, size=18, bold=False, color=NAVY,
        align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font='微软雅黑',
        spacing=1.3):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    lines = text.split('\n')
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = font
    return tb


def rect(slide, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE, alpha=None):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    sp.fill.solid()
    sp.fill.fore_color.rgb = color
    sp.line.fill.background()
    sp.shadow.inherit = False
    if alpha is not None:
        sp.fill.fore_color.rgb = color
    return sp


def page_num(slide, n, total=9):
    txt(slide, f'{n:02d} / {total:02d}', Inches(12.0), Inches(6.95),
        Inches(1.0), Inches(0.3), size=11, color=GRAY, align=PP_ALIGN.RIGHT)


def header_bar(slide, title, sub=''):
    """内容页统一页头"""
    rect(slide, 0, 0, SW, Inches(1.15), NAVY)
    rect(slide, 0, Inches(1.15), SW, Inches(0.06), ACCENT)
    txt(slide, title, Inches(0.75), Inches(0.28), Inches(8.5), Inches(0.6),
        size=30, bold=True, color=WHITE)
    if sub:
        txt(slide, sub, Inches(0.78), Inches(0.78), Inches(8.5), Inches(0.3),
            size=12, color=RGBColor(0xAE, 0xBE, 0xD8))


# ============ 第1页 封面 ============
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
bg.shadow.inherit = False

# 装饰几何
rect(s, Inches(9.6), Inches(-1.2), Inches(5.5), Inches(5.5),
     RGBColor(0x25, 0x37, 0x5C), MSO_SHAPE.OVAL)
rect(s, Inches(11.2), Inches(4.4), Inches(3.2), Inches(3.2),
     RGBColor(0x2E, 0x5C, 0x9E), MSO_SHAPE.OVAL)
rect(s, Inches(0.9), Inches(2.42), Inches(1.5), Inches(0.08), ACCENT)

txt(s, '2027 元旦', Inches(0.9), Inches(1.35), Inches(7.5), Inches(0.9),
    size=54, bold=True, color=WHITE)
txt(s, '放 假 安 排 通 知', Inches(0.9), Inches(2.7), Inches(8.0), Inches(1.0),
    size=48, bold=True, color=RGBColor(0x9D, 0xB9, 0xE6))

txt(s, 'HOLIDAY ARRANGEMENT NOTICE', Inches(0.95), Inches(3.85), Inches(7.0),
    Inches(0.4), size=14, color=RGBColor(0x6E, 0x84, 0xA8))

rect(s, Inches(0.9), Inches(4.55), Inches(6.2), Inches(0.02),
     RGBColor(0x3D, 0x55, 0x82))

txt(s, '放假时间：2027年1月1日 — 1月3日（共3天）',
    Inches(0.9), Inches(4.95), Inches(8.0), Inches(0.45), size=20, color=WHITE)
txt(s, '发布单位：××市××区综合管理办公室    　发文日期：2026年12月15日',
    Inches(0.9), Inches(5.55), Inches(9.0), Inches(0.4), size=13,
    color=RGBColor(0xA8, 0xB8, 0xD0))

rect(s, 0, Inches(7.26), SW, Inches(0.24), ACCENT)

# ============ 第2页 目录 ============
s = add_slide()
header_bar(s, '目 录', 'CONTENTS')
items = [
    ('01', '放假时间安排', '具体放假日期与调休说明'),
    ('02', '假期值班安排', '值班表与应急联络方式'),
    ('03', '安全注意事项', '办公场所与出行安全提示'),
    ('04', '工作要求与提醒', '各部门需落实的事项'),
]
y = Inches(1.85)
for i, (num, t, d) in enumerate(items):
    row_y = y + Inches(i * 1.22)
    rect(s, Inches(1.15), row_y, Inches(0.95), Inches(0.95), LIGHT)
    txt(s, num, Inches(1.15), row_y + Inches(0.19), Inches(0.95), Inches(0.6),
        size=30, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
    txt(s, t, Inches(2.42), row_y + Inches(0.08), Inches(6.0), Inches(0.45),
        size=24, bold=True, color=NAVY)
    txt(s, d, Inches(2.45), row_y + Inches(0.56), Inches(6.5), Inches(0.35),
        size=13, color=GRAY)
    if i < 3:
        rect(s, Inches(2.42), row_y + Inches(1.05), Inches(10.0), Emu(9525),
             RGBColor(0xD9, 0xDF, 0xE8))
page_num(s, 2)

# ============ 第3页 放假时间 ============
s = add_slide()
header_bar(s, '01  放假时间安排', 'HOLIDAY SCHEDULE')

cards = [
    ('1月1日', '周五', '元旦\n法定假日', ACCENT),
    ('1月2日', '周六', '周末\n正常休息', BLUE),
    ('1月3日', '周日', '周末\n正常休息', BLUE),
]
x0 = Inches(1.0)
for i, (date, week, desc, c) in enumerate(cards):
    cx = x0 + Inches(i * 2.85)
    rect(s, cx, Inches(1.85), Inches(2.45), Inches(2.35), WHITE)
    rect(s, cx, Inches(1.85), Inches(2.45), Inches(0.13), c)
    txt(s, date, cx, Inches(2.2), Inches(2.45), Inches(0.55), size=30,
        bold=True, color=c, align=PP_ALIGN.CENTER)
    txt(s, week, cx, Inches(2.85), Inches(2.45), Inches(0.35), size=15,
        color=GRAY, align=PP_ALIGN.CENTER)
    txt(s, desc, cx, Inches(3.3), Inches(2.45), Inches(0.8), size=13,
        color=NAVY, align=PP_ALIGN.CENTER, spacing=1.4)

# 右侧要点
px = Inches(9.75)
rect(s, px, Inches(1.85), Inches(2.6), Inches(2.35), LIGHT)
txt(s, '共 3 天', px, Inches(2.05), Inches(2.6), Inches(0.6), size=34,
    bold=True, color=ACCENT, align=PP_ALIGN.CENTER)
txt(s, '2027.01.01 — 01.03', px, Inches(2.75), Inches(2.6), Inches(0.35),
    size=13, color=GRAY, align=PP_ALIGN.CENTER)
txt(s, '1月4日（周一）\n正常上班', px, Inches(3.2), Inches(2.6), Inches(0.75),
    size=14, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

# 下方说明条
rect(s, Inches(1.0), Inches(4.7), Inches(11.35), Inches(1.9), WHITE)
rect(s, Inches(1.0), Inches(4.7), Inches(0.08), Inches(1.9), ACCENT)
txt(s, '调休说明', Inches(1.35), Inches(4.92), Inches(3.0), Inches(0.4),
    size=17, bold=True, color=NAVY)
notes = [
    '本次元旦放假共3天（1月1日至1月3日），不涉及调休，1月4日（周一）正常上班。',
    '放假期间，各部门不得擅自安排集体活动，确因工作需要加班的，须提前报办公室审批。',
    '如需请假延长假期，请于2026年12月25日前通过OA系统提交请假申请。',
]
txt(s, '\n'.join('· ' + n for n in notes), Inches(1.38), Inches(5.35),
    Inches(10.7), Inches(1.15), size=13, color=RGBColor(0x40, 0x40, 0x40),
    spacing=1.55)
page_num(s, 3)

# ============ 第4页 值班安排 ============
s = add_slide()
header_bar(s, '02  假期值班安排', 'DUTY SCHEDULE')

rows = [
    ('日期', '带班领导', '值班员', '值班电话'),
    ('1月1日（周五）', '王志强  主任', '李晓梅  张宇航', '0571-88886666'),
    ('1月2日（周六）', '陈建国  副主任', '刘思远  赵一鸣', '0571-88886667'),
    ('1月3日（周日）', '周文慧  副书记', '孙浩然  吴嘉怡', '0571-88886668'),
]
tbl_shape = s.shapes.add_table(4, 4, Inches(1.0), Inches(1.9),
                               Inches(11.3), Inches(2.5))
tbl = tbl_shape.table
tbl.columns[0].width = Inches(2.9)
tbl.columns[1].width = Inches(2.6)
tbl.columns[2].width = Inches(3.3)
tbl.columns[3].width = Inches(2.5)

for r, row in enumerate(rows):
    tbl.rows[r].height = Inches(0.62)
    for c, val in enumerate(row):
        cell = tbl.cell(r, c)
        cell.text = ''
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.12)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = val
        run.font.name = '微软雅黑'
        run.font.size = Pt(13)
        if r == 0:
            run.font.bold = True
            run.font.color.rgb = WHITE
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY
        else:
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if r % 2 == 1 else LIGHT

# 值班要求
rect(s, Inches(1.0), Inches(4.75), Inches(5.45), Inches(1.85), WHITE)
rect(s, Inches(1.0), Inches(4.75), Inches(0.08), Inches(1.85), BLUE)
txt(s, '值班要求', Inches(1.3), Inches(4.95), Inches(3.0), Inches(0.35),
    size=16, bold=True, color=NAVY)
req = ['24小时在岗值守，保持通信畅通', '每2小时巡查一次办公区域', '如实填写值班记录并做好交接']
txt(s, '\n'.join('· ' + r for r in req), Inches(1.33), Inches(5.38),
    Inches(5.0), Inches(1.1), size=12.5, color=RGBColor(0x40, 0x40, 0x40),
    spacing=1.55)

# 应急联络
rect(s, Inches(6.85), Inches(4.75), Inches(5.5), Inches(1.85), WHITE)
rect(s, Inches(6.85), Inches(4.75), Inches(0.08), Inches(1.85), ACCENT)
txt(s, '应急联络', Inches(7.15), Inches(4.95), Inches(3.0), Inches(0.35),
    size=16, bold=True, color=NAVY)
emg = ['总值班室：0571-88886666', '安保值班室：0571-88886688', '火警 119 ／ 急救 120 ／ 报警 110']
txt(s, '\n'.join('· ' + e for e in emg), Inches(7.18), Inches(5.38),
    Inches(5.0), Inches(1.1), size=12.5, color=RGBColor(0x40, 0x40, 0x40),
    spacing=1.55)
page_num(s, 4)

# ============ 第5页 安全注意事项 ============
s = add_slide()
header_bar(s, '03  安全注意事项', 'SAFETY REMINDERS')

safety = [
    ('办公场所安全', '离开前关闭电脑、空调、饮水机等用电设备，切断非必要电源；检查门窗是否锁闭。', BLUE),
    ('消防与用电', '严禁在办公区域存放易燃易爆物品；不私拉乱接电线，不使用大功率电器。', ACCENT),
    ('涉密与财物', '涉密文件、印章、票据须入柜上锁；现金及贵重物品按财务规定存入保险柜。', BLUE),
    ('出行交通安全', '假期出行请遵守交通法规，避免疲劳驾驶；雨雪天气注意道路湿滑，减速慢行。', ACCENT),
    ('居家与防疫', '注意用火用气安全，外出前检查燃气阀门；保持室内通风，做好个人健康防护。', BLUE),
    ('网络与反诈', '不点击陌生链接，不向他人透露验证码；警惕"假期补贴""退改签"类诈骗。', ACCENT),
]
for i, (t, d, c) in enumerate(safety):
    col = i % 2
    row = i // 2
    bx = Inches(1.0) + Inches(col * 5.75)
    by = Inches(1.78) + Inches(row * 1.66)
    rect(s, bx, by, Inches(5.5), Inches(1.42), WHITE)
    rect(s, bx, by, Inches(0.07), Inches(1.42), c)
    txt(s, t, bx + Inches(0.32), by + Inches(0.16), Inches(4.9), Inches(0.35),
        size=16, bold=True, color=NAVY)
    txt(s, d, bx + Inches(0.32), by + Inches(0.58), Inches(4.95), Inches(0.75),
        size=12, color=RGBColor(0x4D, 0x4D, 0x4D), spacing=1.45)
page_num(s, 5)

# ============ 第6页 工作要求 ============
s = add_slide()
header_bar(s, '04  工作要求与提醒', 'WORK REQUIREMENTS')

steps = [
    ('01', '落实值班制度', '严格执行值班表，值班人员不得迟到、早退、脱岗；确需调整的，提前1个工作日报办公室备案。'),
    ('02', '保持信息畅通', '中层以上干部及值班人员手机24小时开机，确保突发情况能够第一时间响应。'),
    ('03', '强化应急处置', '遇有紧急情况和重大事项，按"先处置、后报告"原则启动预案，30分钟内上报分管领导。'),
    ('04', '做好收尾准备', '1月3日下班前完成安全检查；1月4日上班后1小时内反馈本部门到岗及运行情况。'),
]
for i, (num, t, d) in enumerate(steps):
    by = Inches(1.8) + Inches(i * 1.28)
    rect(s, Inches(1.0), by, Inches(0.72), Inches(0.72), NAVY)
    txt(s, num, Inches(1.0), by + Inches(0.13), Inches(0.72), Inches(0.45),
        size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    txt(s, t, Inches(1.95), by + Inches(0.02), Inches(3.3), Inches(0.4),
        size=19, bold=True, color=NAVY)
    txt(s, d, Inches(1.95), by + Inches(0.48), Inches(10.2), Inches(0.6),
        size=12.5, color=RGBColor(0x4D, 0x4D, 0x4D), spacing=1.4)
    if i < 3:
        rect(s, Inches(1.36), by + Inches(0.76), Inches(0.02), Inches(0.48),
             RGBColor(0xC5, 0xCE, 0xDC))
page_num(s, 6)

# ============ 第7页 假期服务保障 ============
s = add_slide()
header_bar(s, '假期服务保障与温馨提示', 'SERVICE & TIPS')

left = [
    ('食堂安排', '1月1日—1月3日食堂暂停供餐，1月4日恢复正常。'),
    ('班车运行', '假期期间班车停运，1月4日按原时刻表恢复运行。'),
    ('门禁管理', '启用节假日模式，进出需刷卡并登记来访信息。'),
]
right = [
    ('快递收发', '假期暂停收发，物业代收件请于1月4日后领取。'),
    ('空调供暖', '假期仅保留值班室供暖，其他区域关闭。'),
    ('保洁服务', '1月2日安排1次公共区域保洁，其余时间暂停。'),
]
for col, group in enumerate([left, right]):
    bx = Inches(1.0) + Inches(col * 5.75)
    for i, (t, d) in enumerate(group):
        by = Inches(1.85) + Inches(i * 1.65)
        rect(s, bx, by, Inches(5.5), Inches(1.4), WHITE)
        rect(s, bx, by, Inches(5.5), Inches(0.06), BLUE if col == 0 else ACCENT)
        txt(s, t, bx + Inches(0.3), by + Inches(0.28), Inches(4.9), Inches(0.35),
            size=16, bold=True, color=NAVY)
        txt(s, d, bx + Inches(0.3), by + Inches(0.72), Inches(4.95), Inches(0.55),
            size=12, color=RGBColor(0x4D, 0x4D, 0x4D), spacing=1.4)
page_num(s, 7)

# ============ 第8页 时间轴总览 ============
s = add_slide()
header_bar(s, '假期时间轴总览', 'TIMELINE OVERVIEW')

rect(s, Inches(1.2), Inches(3.55), Inches(10.9), Inches(0.05),
     RGBColor(0xC5, 0xCE, 0xDC))

tl = [
    ('12.15', '通知发布', 'OA系统同步发布', BLUE),
    ('12.25', '请假截止', '延长假期申请截止', BLUE),
    ('1.1', '假期开始', '元旦法定假日', ACCENT),
    ('1.3', '假期最后一天', '完成安全检查', ACCENT),
    ('1.4', '恢复正常上班', '09:00 前反馈到岗', BLUE),
]
for i, (date, t, d, c) in enumerate(tl):
    cx = Inches(1.5) + Inches(i * 2.35)
    rect(s, cx, Inches(3.37), Inches(0.42), Inches(0.42), c, MSO_SHAPE.OVAL)
    txt(s, date, cx - Inches(0.55), Inches(2.55), Inches(1.5), Inches(0.5),
        size=20, bold=True, color=c, align=PP_ALIGN.CENTER)
    txt(s, t, cx - Inches(0.85), Inches(3.95), Inches(2.1), Inches(0.4),
        size=15, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    txt(s, d, cx - Inches(0.95), Inches(4.42), Inches(2.3), Inches(0.7),
        size=11.5, color=GRAY, align=PP_ALIGN.CENTER, spacing=1.3)
page_num(s, 8)

# ============ 第9页 结尾 ============
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
bg.shadow.inherit = False

rect(s, Inches(-1.5), Inches(3.6), Inches(5.0), Inches(5.0),
     RGBColor(0x25, 0x37, 0x5C), MSO_SHAPE.OVAL)

txt(s, '感谢聆听', Inches(0), Inches(2.65), SW, Inches(1.2), size=54,
    bold=True, color=WHITE, align=PP_ALIGN.CENTER)
rect(s, Inches(6.17), Inches(3.95), Inches(1.0), Inches(0.05), ACCENT)
txt(s, '祝全体同事元旦快乐，假期平安愉快！', Inches(0), Inches(4.35), SW,
    Inches(0.5), size=20, color=RGBColor(0x9D, 0xB9, 0xE6), align=PP_ALIGN.CENTER)
txt(s, '××市××区综合管理办公室　　|　　2026年12月15日', Inches(0), Inches(5.35),
    SW, Inches(0.4), size=13, color=RGBColor(0x87, 0x9B, 0xB8),
    align=PP_ALIGN.CENTER)
rect(s, 0, Inches(7.26), SW, Inches(0.24), ACCENT)

prs.save(OUT)
print('已生成：', OUT)
print('幻灯片页数：', len(prs.slides))
