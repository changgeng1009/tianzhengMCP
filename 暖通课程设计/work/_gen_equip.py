import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()

# ====== Sheet 1: FHE Heat Exchangers ======
ws1 = wb.active
ws1.title = '全热交换器FHE'
headers1 = ['型号', '电源(V)', '功率(W)', '风量(m3/h)', '静压(Pa)', '重量(kg)']
for c, h in enumerate(headers1, 1):
    ws1.cell(row=1, column=c, value=h).font = Font(bold=True)
data1 = [
    ['FHE-15WB', 220, 60, 150, 60, 18],
    ['FHE-20WB', 220, 68, 200, 60, 18],
    ['FHE-25W', 220, 105, 250, 85, 31],
    ['FHE-35W', 220, 140, 350, 90, 36],
    ['FHE-40W', 220, 150, 400, 95, 39],
    ['FHE-50W', 220, 220, 500, 100, 48.5],
    ['FHE-60W', 220, 230, 600, 110, 49.5],
    ['FHE-80W', 220, 350, 800, 150, 71.5],
    ['FHE-100W', 220, 480, 1000, 150, 85],
]
for r, row in enumerate(data1, 2):
    for c, v in enumerate(row, 1):
        ws1.cell(row=r, column=c, value=v)

# ====== Sheet 2: FHE Ceiling series ======
ws2 = wb.create_sheet('全热交换器吊顶式')
headers2 = ['型号', '风量(m3/h)', '静压(Pa)', '功率(kW)', '电压(V)', '噪音(dB)', '重量(kg)']
for c, h in enumerate(headers2, 1):
    ws2.cell(row=1, column=c, value=h).font = Font(bold=True)
data2 = [
    ['FHE-150WB2', 1500, 180, '0.50 (0.25x2)', 220, 48, 85],
    ['FHE-200WB2', 2000, 200, '0.60 (0.30x2)', 220, 50, 90],
    ['FHE-250WB2', 2500, 220, '0.75 (0.375x2)', 220, 52, 105],
    ['FHE-300WB2', 3000, 250, '0.90 (0.45x2)', 220, 56, 110],
    ['FHE-400WB2', 4000, 300, '1.60 (0.80x2)', 380, 62, 148],
    ['FHE-500WB2', 5000, 300, '2.00 (1.00x2)', 380, 64, 188],
    ['FHE-6000WB2', 6000, 320, '3.00 (1.50x2)', 380, 64, 200],
]
for r, row in enumerate(data2, 2):
    for c, v in enumerate(row, 1):
        ws2.cell(row=r, column=c, value=v)

# ====== Sheet 3: Missing FCU data template ======
ws3 = wb.create_sheet('待提取-FCU机组参数')
hdr_warn = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')
headers3 = ['型号', '制冷量(kW)', '风量(m3/h)', '水量(kg/h)', '水压降(kPa)', '机外静压(Pa)', '数据来源']
for c, h in enumerate(headers3, 1):
    cell = ws3.cell(row=1, column=c, value=h)
    cell.font = Font(bold=True)
    cell.fill = hdr_warn
ws3.cell(row=2, column=1, value='待从PDF前16页或ZK样本图片提取')
ws3.cell(row=2, column=7, value='PDF扫描件(未提取)')

# ====== Sheet 4: Missing AHU data template ======
ws4 = wb.create_sheet('待提取-全空气机组参数')
headers4 = ['型号', '制冷量(kW)', '风量(m3/h)', '水量(kg/h)', '水压降(kPa)', '数据来源']
for c, h in enumerate(headers4, 1):
    cell = ws4.cell(row=1, column=c, value=h)
    cell.font = Font(bold=True)
    cell.fill = hdr_warn
ws4.cell(row=2, column=1, value='待从ZK样本图片或PDF提取')
ws4.cell(row=2, column=6, value='ZK组合式空调机组样本图片(未提取)')

for ws in [ws1, ws2, ws3, ws4]:
    for i in range(1, 8):
        ws.column_dimensions[get_column_letter(i)].width = 18

wb.save(r'D:\CodexWork\天正\暖通课程设计\work\equipment_catalog_extracted.xlsx')
print('Done: equipment_catalog_extracted.xlsx')
