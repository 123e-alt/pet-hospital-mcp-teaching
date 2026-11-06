# -*- coding: utf-8 -*-
"""生成《关于2026年11月值班安排的通知》Word 文档"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

doc = Document()

# ---------- 全局样式 ----------
style = doc.styles['Normal']
style.font.name = 'Times New Roman'
style.font.size = Pt(12)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')

# 页边距
for section in doc.sections:
    section.top_margin = Cm(3.7)
    section.bottom_margin = Cm(3.5)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.6)


def set_font(run, name='仿宋', size=12, bold=False, color=None):
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
    if color:
        run.font.color.rgb = color


# ---------- 标题 ----------
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('关于2026年11月值班安排的通知')
set_font(r, '方正小标宋简体', 22, bold=True)
p.paragraph_format.space_after = Pt(6)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('行办发〔2026〕18号')
set_font(r, '仿宋', 12)
p.paragraph_format.space_after = Pt(18)

# ---------- 主送单位 ----------
p = doc.add_paragraph()
r = p.add_run('各部门、各科室：')
set_font(r, '仿宋', 14)
p.paragraph_format.first_line_indent = Pt(28)
p.paragraph_format.space_after = Pt(6)

# ---------- 正文 ----------
body_texts = [
    '为进一步加强单位日常管理，保障各项工作有序运转，及时妥善处置各类突发情况，'
    '根据《值班工作管理办法（试行）》有关要求，结合本月工作实际情况，现将2026年11月'
    '值班安排及有关事项通知如下。',
    '一、值班时间',
    '工作日值班时间为18:00至次日8:30；双休日及法定节假日实行24小时值班，'
    '白天班为8:30至18:00，夜间班为18:00至次日8:30。值班人员须提前10分钟到岗，'
    '做好值班记录与交接班工作。',
    '二、值班地点',
    '综合办公楼一楼值班室（值班电话：0571-88886666；传真：0571-88886667）。'
    '值班期间须保持通信畅通，值班电话响铃三次内接听。',
    '三、值班人员安排',
    '本月值班共分4个班组，每组设带班领导1名、值班员2名，具体安排如下：',
]

for t in body_texts:
    p = doc.add_paragraph()
    r = p.add_run(t)
    set_font(r, '仿宋', 14)
    p.paragraph_format.first_line_indent = Pt(28)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(4)

# ---------- 表格 ----------
table = doc.add_table(rows=1, cols=5)
table.style = 'Table Grid'
table.alignment = WD_TABLE_ALIGNMENT.CENTER

headers = ['班组', '值班时间', '带班领导', '值班员', '联系电话']
rows_data = [
    ['第一组', '11月1日—11月8日', '王志强（主任）', '李晓梅、张宇航', '1380571001 / 1380571002'],
    ['第二组', '11月9日—11月16日', '陈建国（副主任）', '刘思远、赵一鸣', '1380571003 / 1380571004'],
    ['第三组', '11月17日—11月24日', '周文慧（副书记）', '孙浩然、吴嘉怡', '1380571005 / 1380571006'],
    ['第四组', '11月25日—11月30日', '马云飞（副主任）', '郑晓东、何雨欣', '1380571007 / 1380571008'],
]

hdr = table.rows[0].cells
for i, h in enumerate(headers):
    hdr[i].text = ''
    para = hdr[i].paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(para.add_run(h), '黑体', 12, bold=True)

for row in rows_data:
    cells = table.add_row().cells
    for i, val in enumerate(row):
        cells[i].text = ''
        para = cells[i].paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(para.add_run(val), '仿宋', 11)

# 表格后空一行
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(4)

# ---------- 后续正文 ----------
tail_texts = [
    '四、工作要求',
    '（一）严格落实值班制度。值班人员须按时到岗，不得迟到、早退、擅自脱岗，'
    '确需调整值班安排的，应提前一个工作日向办公室报备并办理调换手续。',
    '（二）认真做好值班记录。对来电来访、文件收发、突发事件等情况须如实登记，'
    '做到记录完整、准确、可追溯，重要情况第一时间向带班领导报告。',
    '（三）规范处置突发事件。遇有紧急情况和重大事项，按照"先处置、后报告"原则，'
    '及时启动应急预案，并在30分钟内报办公室及分管领导，不得迟报、漏报、瞒报。',
    '（四）做好安全防范工作。离岗前检查办公区域水电、门窗及消防设施，'
    '妥善保管涉密文件和贵重物品，确保单位安全稳定。',
    '（五）办公室将对值班情况进行不定期抽查，抽查结果纳入年度考核。'
    '对违反值班纪律的，视情节予以通报批评并追究相关责任。',
    '特此通知。',
]

for t in tail_texts:
    p = doc.add_paragraph()
    r = p.add_run(t)
    set_font(r, '仿宋', 14)
    p.paragraph_format.first_line_indent = Pt(28)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(4)

# ---------- 附件 ----------
p = doc.add_paragraph()
r = p.add_run('附件：1. 2026年11月值班人员名单')
set_font(r, '仿宋', 14)
p.paragraph_format.first_line_indent = Pt(28)

p = doc.add_paragraph()
r = p.add_run('　　　2. 值班工作交接单（样表）')
set_font(r, '仿宋', 14)
p.paragraph_format.first_line_indent = Pt(28)
p.paragraph_format.space_after = Pt(24)

# ---------- 落款 ----------
for text in ['××市××区综合管理办公室', '2026年11月2日']:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run(text + '　　　')
    set_font(r, '仿宋', 14)

# ---------- 页脚 ----------
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('—— 抄送：区委办公室、区政府办公室 ——')
set_font(r, '仿宋', 10, color=RGBColor(0x66, 0x66, 0x66))

out = r'C:\Users\qq\Desktop\LLM\04-agent\xAgent\关于2026年11月值班安排的通知.docx'
doc.save(out)
print('已生成：', out)
