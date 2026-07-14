# -*- coding: utf-8 -*-
from pathlib import Path
from datetime import datetime
import csv, io, re
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

base = Path.cwd()
work = base / 'work'
work.mkdir(exist_ok=True)
source_root = base / 'REDACTED_CLASS 课程设计资料'
pdf_rel = 'REDACTED_CLASS 课程设计资料/选型-末端系列 (1).pdf'
zk_rel = 'REDACTED_CLASS 课程设计资料/workzk_ahu_data.md'

def style_ws(ws):
    fill = PatternFill('solid', fgColor='1F4E78')
    font = Font(color='FFFFFF', bold=True)
    border = Border(bottom=Side(style='thin', color='9EADCC'))
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        max_len = 8
        for cell in col:
            text = '' if cell.value is None else str(cell.value)
            max_len = max(max_len, min(len(text), 56))
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        ws.column_dimensions[letter].width = min(max_len + 2, 42)

def write_book(path, rows, sheet_name, title):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, '') for h in headers])
    style_ws(ws)
    notes = wb.create_sheet('说明')
    notes.append(['项目', '内容'])
    notes.append(['标题', title])
    notes.append(['生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    notes.append(['来源限制', '仅本地课程资料；未使用网上数据；未读取/修改DWG；未修改现有Excel。'])
    notes.append(['置信度', '高=页面清晰且字段完整；中=字段清晰但仍需确认用途/型号对应；需复核=样本未给出或不清晰。'])
    style_ws(notes)
    notes.column_dimensions['A'].width = 18
    notes.column_dimensions['B'].width = 90
    wb.save(path)

# FCU：PDF第3页基础参数，第5页尺寸。水管/冷凝水管径见第3页底部说明。
fcu_dims = {
    'FC-34':'A740 B510 C480 D492；出风口480*120；回风口492*180；吊装孔510*210',
    'FC-51':'A840 B610 C580 D592；出风口580*120；回风口592*180；吊装孔610*210',
    'FC-68':'A940 B710 C680 D692；出风口680*120；回风口692*180；吊装孔710*210',
    'FC-85':'A1040 B810 C780 D792；出风口780*120；回风口792*180；吊装孔810*210',
    'FC-102':'A1140 B910 C880 D892；出风口880*120；回风口892*180；吊装孔910*210',
    'FC-136':'A1540 B1310 C1280 D1292；出风口1280*120；回风口1292*180；吊装孔1310*210',
    'FC-170':'A1640 B1410 C1380 D1392；出风口1380*120；回风口1392*180；吊装孔1410*210',
    'FC-204':'A1740 B1550 C1520 D1532；出风口1520*120；回风口1532*180；吊装孔1550*210',
    'FC-238':'A1840 B1670 C1640 D1652；出风口1640*120；回风口1652*180；吊装孔1670*210',
}
fcu_raw = [
    ('2排管','FC-34',340,268,201,1.72,3.24,296,7,'30Pa输入44W/输出12W',36),
    ('2排管','FC-51',510,403,302,2.52,4.24,433,15,'30Pa输入59W/输出20W',38),
    ('2排管','FC-68',680,537,403,3.36,6.07,578,28,'30Pa输入72W/输出25W',39),
    ('2排管','FC-85',850,671,503,4.20,8.05,722,8,'30Pa输入85W/输出30W',42),
    ('2排管','FC-102',1020,805,604,4.90,10.27,843,14,'30Pa输入104W/输出40W',44),
    ('2排管','FC-136',1360,1074,805,6.60,11.11,1135,19,'30Pa输入147W/输出25*2W',47),
    ('2排管','FC-170',1700,1342,1007,7.82,13.62,1345,28,'30Pa输入170W/输出30*2W',48),
    ('2排管','FC-204',2040,1611,1208,9.51,15.78,1636,44,'30Pa输入212W/输出40*2W',50),
    ('2排管','FC-238',2380,1879,1409,11.09,19.24,1908,71,'30Pa输入253W/输出50*2W',52),
    ('3排管','FC-34',340,255,190,2.04,3.23,351,7,'30Pa输入44W/输出12W',36),
    ('3排管','FC-51',510,383,287,2.97,4.23,511,15,'30Pa输入59W/输出20W',38),
    ('3排管','FC-68',680,510,383,3.97,6.00,683,28,'30Pa输入72W/输出25W',39),
    ('3排管','FC-85',850,638,478,4.84,8.00,832,8,'30Pa输入85W/输出30W',42),
    ('3排管','FC-102',1020,765,574,5.70,9.98,980,14,'30Pa输入104W/输出40W',44),
    ('3排管','FC-136',1360,1020,765,7.75,11.76,1333,19,'30Pa输入147W/输出25*2W',47),
    ('3排管','FC-170',1700,1275,956,9.27,13.50,1595,28,'30Pa输入170W/输出30*2W',48),
    ('3排管','FC-204',2040,1530,1148,11.12,15.70,1913,44,'30Pa输入212W/输出40*2W',50),
    ('3排管','FC-238',2380,1785,1340,12.97,19.15,2231,71,'30Pa输入253W/输出50*2W',52),
]
fcu_rows = []
for coil, model, hi, mid, low, cool, heat, water, res, power, noise in fcu_raw:
    fcu_rows.append({
        '设备类型':'风机盘管-暗藏式', '型号':model, '盘管配置':coil,
        '风量 m³/h':hi, '中档风量 m³/h':mid, '低档风量 m³/h':low,
        '制冷量 kW':cool, '制热量 kW':heat,
        '水流量 m³/h 或 L/s':f'{water} kg/h', '水阻 kPa':res,
        '电机功率 W 或 kW':power, '噪声 dB(A)':noise, '机外余压 Pa':'12/30/50Pa可选；本行按30Pa记录',
        '进出水管径 DN':'DN20 内螺纹', '凝结水管径 DN':'DN20 外螺纹',
        '外形尺寸':fcu_dims[model], '重量':'样本页未清晰列出，需人工复核', '安装方式':'卧式暗藏/吊顶暗装',
        '数据来源文件':pdf_rel, '来源页码或图片编号':'PDF第3页、第5页', '置信度':'高',
        '备注':'未混入变工况修正表；如采用3+1排管，需另查第3页组合盘管行并人工确认。'
    })

# 新风/空气处理机组：KD来自PDF第12页；KW/KL来自第10页；FHE来自第17页；ZK来自本地Markdown数据包。
fresh_rows = []
kd_raw = [
    ('四排管','KD-2D',2000,'219/97','0.32/0.25',25,28,4.4,10,101,'DN40','DN25'),
    ('四排管','KD-3D',3000,'245/155','0.55/0.45',40,43,6.89,20,154,'DN50','DN25'),
    ('四排管','KD-4D',4000,'255/148','0.8/0.8',54,56,9.3,25,182,'DN50','DN32'),
    ('四排管','KD-5D',5000,'186/110','1.1/0.8',69,71,11.9,40,216,'DN50','DN32'),
    ('四排管','KD-6D',6000,'310/216','1.5/1.1',85,86,14.6,49,259,'DN50','DN32'),
    ('六排管','KD-2D',2000,'189/67','0.32/0.25',35,33,5.9,25,112,'DN50','DN25'),
    ('六排管','KD-3D',3000,'215/125','0.55/0.45',52,49,8.9,40,171,'DN50','DN25'),
    ('六排管','KD-4D',4000,'225/118','0.8/0.8',69,67,11.9,48,202,'DN65','DN32'),
    ('六排管','KD-5D',5000,'256/80','1.1/0.8',86,83,14.8,30,241,'DN65','DN32'),
    ('六排管','KD-6D',6000,'280/186','1.5/1.1',104,100,17.8,40,288,'DN65','DN32'),
]
noise = {'KD-2D':'56','KD-3D':'58','KD-4D':'59','KD-5D':'60','KD-6D':'61'}
for coil, model, air, press, motor, cool, heat, flow, res, weight, dn, cdn in kd_raw:
    fresh_rows.append({
        '设备类型':'吊挂式空气处理机组/新风工况', '型号':model, '额定风量 m³/h':air,
        '制冷量 kW':cool, '制热量 kW':heat, '机外余压 Pa':f'I类/II类 {press}',
        '电机功率 kW':f'I类/II类 {motor}', '水流量 m³/h 或 t/h':f'{flow} m³/h', '水阻 kPa':res,
        '噪声 dB(A)':noise.get(model, '需人工复核'), '进出水管径 DN':dn, '凝结水管径 DN':cdn,
        '外形尺寸':'见PDF第12页对应型号尺寸图表', '重量':weight, '过滤段或功能段配置':'新风工况；图示含过滤/盘管/风机段',
        '数据来源文件':pdf_rel, '来源页码或图片编号':'PDF第12页', '置信度':'高',
        '备注':f'{coil}；旧Excel如使用XF命名，需确认XF与KD对应关系。'
    })
for model, air, press, dim in [
    ('KW-5P',5000,400,'A900 B650 C790 D1200 E1250 H790 L*R400*350 L1*R1700*300'),
    ('KW-6P',6000,420,'A1000 B750 C790 D1200 E1350 H790 L*R450*400 L1*R800*300'),
    ('KW-8P',8000,450,'A1200 B800 C790 D1300 E1400 H790 L*R650*500 L1*R1000*400'),
    ('KW-10P',10000,450,'A1300 B900 C790 D1400 E1500 H900 L*R700*400 L1*R1100*400'),
    ('KW-12.5P',12500,480,'A1500 B1000 C790 D1400 E1600 H900 L*R800*500 L1*R1250*400'),
    ('KW-15P',15000,500,'A1800 B1000 C790 D1400 E1600 H1000 L*R1000*500 L1*R1700*400'),
    ('KL-20P',20000,520,'A1200 B1200 C1600 D2000 E1800 H1600 H1 1000 L*R1200*800 L1*R1900*800'),
    ('KL-25P',25000,550,'A1500 B1200 C1600 D2800 E1800 H1600 H1 1000 L*R1200*800 L1*R1900*800'),
    ('KL-30P',30000,550,'A1800 B1300 C1600 D2800 E1900 H1600 H1 1000 L*R1200*900 L1*R2300*900'),
]:
    fresh_rows.append({
        '设备类型':'新风空气处理机组', '型号':model, '额定风量 m³/h':air,
        '制冷量 kW':'需人工复核', '制热量 kW':'需人工复核', '机外余压 Pa':press,
        '电机功率 kW':'需人工复核', '水流量 m³/h 或 t/h':'需人工复核', '水阻 kPa':'需人工复核',
        '噪声 dB(A)':'需人工复核', '进出水管径 DN':'需人工复核', '凝结水管径 DN':'需人工复核',
        '外形尺寸':dim, '重量':'需人工复核', '过滤段或功能段配置':'可选上层空气过滤段；见PDF第10页说明',
        '数据来源文件':pdf_rel, '来源页码或图片编号':'PDF第10页', '置信度':'中',
        '备注':'第10页清晰给出风量、静压、尺寸；冷量/水量等未在该页完整确认。'
    })
for model, air, press, power, weight, dim, noise_val in [
    ('FHE-150WB2',1500,180,'0.25*2 kW',85,'1504x1306x909；进/出风口230*210',48),
    ('FHE-200WB2',2000,200,'0.30*2 kW',90,'1504x1376x1009；进/出风口230*260',50),
    ('FHE-250WB2',2500,220,'0.375*2 kW',105,'1570x1406x1009；进/出风口300*260',52),
    ('FHE-300WB2',3000,250,'0.45*2 kW',110,'1570x1406x1049；进/出风口330*300',56),
    ('FHE-400WB2',4000,300,'0.8*2 kW',148,'1842x1742x1049；进/出风口360*310',62),
]:
    fresh_rows.append({
        '设备类型':'全热交换器', '型号':model, '额定风量 m³/h':air,
        '制冷量 kW':'不适用', '制热量 kW':'不适用', '机外余压 Pa':press,
        '电机功率 kW':power, '水流量 m³/h 或 t/h':'不适用', '水阻 kPa':'不适用', '噪声 dB(A)':noise_val,
        '进出水管径 DN':'不适用', '凝结水管径 DN':'不适用', '外形尺寸':dim, '重量':weight,
        '过滤段或功能段配置':'全热交换，吊顶式', '数据来源文件':pdf_rel, '来源页码或图片编号':'PDF第17页',
        '置信度':'高', '备注':'用于新风换气，不等同于冷/热水新风处理机组。'
    })
# ZK parse from Markdown CSV blocks.
zk_path = source_root / zk_rel
zk_text = zk_path.read_text(encoding='utf-8', errors='ignore') if zk_path.exists() else ''
blocks = re.findall(r'```csv\s*(.*?)```', zk_text, flags=re.S)
zk_perf, zk_water, zk_size = {}, {}, {}
for block in blocks:
    clean = block.replace('\\_', '_')
    rdr = csv.DictReader(io.StringIO(clean.strip()))
    rows = list(rdr); heads = rdr.fieldnames or []
    if 'cooling_4row_kw' in heads:
        zk_perf = {r['model']: r for r in rows}
    elif 'cw_flow_4row_th' in heads:
        zk_water = {r['model']: r for r in rows}
    elif 'section_BxH' in heads:
        zk_size = {r['model']: r for r in rows}
for model, r in zk_perf.items():
    if model not in ['ZK-15','ZK-20','ZK-25','ZK-30','ZK-40']:
        continue
    w = zk_water.get(model, {}); s = zk_size.get(model, {})
    for key, label in [('4row','四排管'), ('6row','六排管'), ('8row','八排管')]:
        fresh_rows.append({
            '设备类型':'组合式空气处理机组', '型号':model, '额定风量 m³/h':r.get('airflow_m3h'),
            '制冷量 kW':r.get(f'cooling_{key}_kw'), '制热量 kW':'需人工复核', '机外余压 Pa':r.get('fan_pressure_pa'),
            '电机功率 kW':r.get('motor_kw'), '水流量 m³/h 或 t/h':w.get(f'cw_flow_{key}_th','') + ' t/h',
            '水阻 kPa':w.get(f'cw_resistance_{key}_kpa',''), '噪声 dB(A)':r.get('noise_dba'),
            '进出水管径 DN':w.get('cw_pipe_mm',''), '凝结水管径 DN':w.get('condensate_pipe_mm',''),
            '外形尺寸':'截面 '+s.get('section_BxH','')+'；水平出口 '+s.get('horizontal_outlet_ExD',''),
            '重量':'需人工复核', '过滤段或功能段配置':'组合段按设计选择；阻力表见数据包',
            '数据来源文件':zk_rel, '来源页码或图片编号':'本地Markdown CSV', '置信度':'高',
            '备注':label+'；型号后缀如 W6S-ZH 需按结构、排数、左右式补全。'
        })

write_book(work / 'fcu_catalog_extracted.xlsx', fcu_rows, 'FCU样本', 'FCU风机盘管样本参数提取')
write_book(work / 'fresh_air_unit_catalog_extracted.xlsx', fresh_rows, '新风空气机组', '新风机组/空气处理机组样本参数提取')

files = []
for p in sorted(source_root.rglob('*')):
    if not p.is_file():
        continue
    status = '跳过图纸/锁文件' if p.suffix.lower() in ['.dwg','.bak','.dwl','.dwl2'] else '纳入只读检索'
    role = '设备样本PDF' if p.suffix.lower()=='.pdf' else '课程指导/规则文档' if p.suffix.lower()=='.docx' else '课程计算表参考' if p.suffix.lower()=='.xlsx' else '设备样本图片' if p.suffix.lower() in ['.jpg','.jpeg','.png'] else '结构化设备数据' if p.suffix.lower()=='.md' else '非目标资料'
    files.append((p.relative_to(source_root).as_posix(), p.suffix, p.stat().st_size, status, role))
inv = ['# 设备资料目录盘点','',f'- 扫描目录：`{source_root}`','- 本阶段未读取、未修改 DWG；DWG/BAK/DWL/DWL2 已排除。','- 数据来源限定为本地课程资料，未使用网上数据。','','## 文件清单','','| 文件 | 类型 | 大小(Byte) | 处理状态 | 说明 |','|---|---:|---:|---|---|']
for row in files:
    inv.append('| ' + ' | '.join(str(x).replace('|','/') for x in row) + ' |')
inv += ['','## 找到的设备样本文件','','- `选型-末端系列 (1).pdf`：FCU、KD/KW/KL 新风/空气处理机组、FHE 全热交换器。','- `workzk_ahu_data.md`：ZK 组合式空气处理机组结构化参数。','- `选型-组合全空气机组选型图片/003.jpg` 至 `013.jpg`：ZK 图片样本来源。','- `REDACTED_CLASS班-课程设计指导2025级 .docx`：风口、风管、水系统与选型规则。','- `新风量及新风负荷计算问题.docx`：新风量和新风负荷补充规则。','','## 提取结果','','- FCU 参数足够用于初步选型：已提取 FC-34~FC-238 的风量、冷量、热量、水流量、水阻、30Pa功率、噪声、DN20管径和尺寸。','- 新风机组参数可用于 KD 系列初步选型；KW/KL 只提取到风量、静压、尺寸，其他字段需复核。','- ZK 参数足够用于 ZK-20/ZK-25 等中餐厅全空气机组初步校核。']
(work / 'equipment_data_inventory.md').write_text('\n'.join(inv), encoding='utf-8')

rules = '''# 风口、风管、水系统规则提取

## 数据来源

- `REDACTED_CLASS班-课程设计指导2025级 .docx`
- `新风量及新风负荷计算问题.docx`

## 已提取规则

| 类别 | 规则/公式 | 备注 |
|---|---|---|
| 新风量人员法 | Q人员 = 人数 × 人均新风量 | 中餐厅可按 S×0.8 人/m² × 30 m³/(h·人) 估算；普通餐厅可按 25 m³/(h·人)。 |
| 新风量换气次数法 | Q换气 = n × S × H | 中餐厅推荐 n=3~6 次/h；必须乘层高/净高。 |
| 全空气新风校核 | Q设计 ≥ 空调总送风量 × 10% | 10% 是下限校核，不是直接替代人员法/换气次数法。 |
| 新风负荷 | Q = L × 1.2 × Δh / 3600 | 南宁室内外焓差示例约 28.8。 |
| 新风机选型余量 | 总新风量 × 1.1 后查样本 | 指导书示例为 12×150×1.1=1980 m³/h。 |
| 风机盘管选型 | 按房间冷负荷 + 房间布局选择 | 采用风管+散流器时应选高静压型，机外静压 ≥30Pa。 |
| 出风口风速 | 2~3 m/s | 中餐厅可取较高值；包厢/安静场所取低值。 |
| 餐厅风口风速 | 中餐厅 3.5~4.5 m/s；包厢/西餐厅 2.5~3.5 m/s | 需结合噪声要求。 |
| 回风口风速 | 不大于 4 m/s；安静场所 1.5~2.5 m/s | 用于回风口尺寸估算。 |
| 防雨百叶风速 | 4~6 m/s | 用于室外新风入口。 |
| 风管/风口公式 | L = F × V；F = A × B；F = L / V / 3600 | L 为 m³/h，V 为 m/s，F 为 m²。 |
| 静压箱面积 | 截面积 ≥1.5 倍入口风管截面积 | 常规静压箱内风速 1.5~2.5m/s。 |
| 风机出口直管 | 风机出口至消声静压箱直管段宜 1.0~1.5m | 1.5~3m 需附阻力计算。 |
| 新风机吸入口直管 | 机组进风法兰前宜 ≥1.5 倍风管长边，最低不小于 1 倍长边 | 外墙百叶后宜留 ≥0.5m 直管。 |
| 风管软接 | 风机出风口与硬质风管之间设 150~250mm 保温柔性软接 | 减震与施工要求。 |
| 走廊净高 | 走廊疏散走道内静压箱、风管底部净高 ≥2.2m | 需图纸布置后校核。 |
| 冷凝水坡度 | 一般不小于 0.8% | 无压排水管。 |
| 水管流速 | 水泵压出口 2.4~3.6；吸入口 1.2~2.1；主干管 1.2~4.5；一般管路 1.5~3.0；向上管道 1.0~3.0 m/s | 指导书表格推荐值。 |
| 水管公式 | L = F × V；D = sqrt(4F/π) | 文档示例存在单位书写疑点，需按工程单位复核。 |

## 待图纸布置后复核

- 实际风管路线、分支管段长度、弯头/三通数量、局部阻力。
- 实际水管路线、同程/异程方案、最不利环路。
- 走廊、吊顶、梁底净高对风管/静压箱的影响。
- 设备平台、管井、风井、新风入口与排风口间距。
'''
(work / 'air_water_design_rules_extracted.md').write_text(rules, encoding='utf-8')

uncertain = '''# 设备参数提取不确定项

## 需要人工复核

1. FCU 重量：PDF 第3-5页未清晰列出 FC-34~FC-238 重量。
2. FCU 3+1排管：水流量/水阻为制冷盘管和加热盘管组合值，本轮未写入主表，实际采用时需人工确认。
3. 新风机组型号命名：旧 Excel 可能使用 `XF-3000`，本地样本清晰型号为 `KD-3D`、`KD-3x2D` 等，二者对应关系需确认。
4. KW/KL 系列：PDF 第10页清晰给出风量、静压、尺寸，但制冷量、制热量、水流量、水阻、噪声、管径未完整确认。
5. FHE 全热交换器：可用于新风换气，但不是冷/热水新风处理机组，是否填入 Excel “新风机组”字段需确认。
6. ZK 组合式机组：风量、冷量、风压、电机功率、水流量、水阻、管径足够；重量、功能段组合、左右式、户外/低温/壁板后缀仍需确认。
7. 客房 FCU 选型仍需结合房间布局、风口数量、是否高静压、噪声要求确认。
8. 4F 客房数量、同型面积、层高、外窗/西晒风险仍属于图纸/人工确认项。

## 可以部分解除的 Excel 待确认项

- FCU 样本参数“无本地依据”可以部分解除：FC 系列风量、冷量、热量、水流量、水阻、30Pa功率、噪声、DN20管径、暗装尺寸已有本地样本依据。
- ZK 中餐厅空气处理机组参数“需样本核实”可以部分解除：ZK-20/ZK-25 等参数已有 `workzk_ahu_data.md` 本地数据依据。
- 新风机组参数可在用户确认采用 KD 系列后部分解除，例如 KD-3D/KD-3x2D 可作为 3000 m³/h 附近新风机组候选。

## 仍需保留“待图纸布置后复核”

- 风管尺寸最终值、风口数量、风口位置、静压箱尺寸。
- 水系统管径、管路长度、局部阻力、最不利环路。
- 新风入口、防雨百叶、机房/管井/风井、设备平台布置。
'''
(work / 'equipment_extract_uncertain_items.md').write_text(uncertain, encoding='utf-8')

# Verify
for p in [work/'fcu_catalog_extracted.xlsx', work/'fresh_air_unit_catalog_extracted.xlsx']:
    wb = load_workbook(p, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    print(p.name, ws.max_row, ws.max_column, [ws.cell(1,c).value for c in range(1, min(ws.max_column, 6)+1)])
    wb.close()
for p in [work/'equipment_data_inventory.md', work/'air_water_design_rules_extracted.md', work/'equipment_extract_uncertain_items.md']:
    print(p.name, p.stat().st_size, p.read_text(encoding='utf-8')[:30])
