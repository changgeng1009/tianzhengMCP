# -*- coding: utf-8 -*-
from pathlib import Path
from shutil import copy2
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import math, json, re

base=Path.cwd()
src_calc=base/'output'/'暖通课程设计计算表-GPT重填版.xlsx'
out_calc=base/'output'/'暖通课程设计计算表-GPT重填版-模板内容补丁.xlsx'
src_equip=base/'output'/'暖通设备选型汇总表-GPT重填版.xlsx'
out_equip=base/'output'/'暖通设备选型汇总表-GPT重填版-模板内容补丁.xlsx'
copy2(src_calc, out_calc)

wb=load_workbook(out_calc, data_only=False)

# ---- 房间冷负荷计算 ----
ws=wb['房间冷负荷计算']
# local sample based selections
# FC-204 2pipe: 9.51 kW, 2040 m3/h, 1636 kg/h, 44 kPa
# FC-136 2pipe: 6.60 kW, 1360 m3/h, 1135 kg/h, 19 kPa
# FC-85 2pipe: 4.20 kW, 850 m3/h, 722 kg/h, 8 kPa
updates = {
    13: ['2F-HB01 豪华包厢A', 19.99, 330, None, None, 'FC-204', 1, 9.51, 2040, 1636, 44],
    14: ['2F-HB02 豪华包厢B', 21.65, 330, None, None, 'FC-204', 1, 9.51, 2040, 1636, 44],
    15: ['2F-BX01~BX06 普通包厢', 18.13, 330, None, None, 'FC-136', 6, 6.60, 1360, 1135, 19],
    17: ['4F-KF 标准客房（26.54㎡/间×16）', 424.64, 120, None, None, 'FC-85', 16, 4.20, 850, 722, 8],
    21: ['2F-CT01 中餐厅左', 286.68, 430, None, None, 'ZK-20W6S', 1, 145, 20000, 24.93, 35.86],
    22: ['2F-CT02 中餐厅右', 432.01, 430, None, None, 'ZK-25W8S', 1, 221.08, 25000, 38.02, 43.87],
}
for r, vals in updates.items():
    for c, v in enumerate(vals, start=1):
        if c in (4,5):
            continue  # keep template formulas D/E
        ws.cell(r,c).value=v
# Update formulas if absent, keep existing formula pattern
for r in [13,14,15,17,21,22]:
    ws.cell(r,4).value=f'=B{r}*C{r}/1000'
    ws.cell(r,5).value=f'=D{r}*1.1'
# Clear stale prefill reserve text in key non-used rows only within existing template rows
for r in [18,19,23]:
    for c in [1,2,3,6,7,8,9,10,11]:
        ws.cell(r,c).value = None if c!=1 else '预留'

# ---- 新风量 ----
ws=wb['新风量']
# method 1 people entries
nf_people = {
    13: ('2F-CT01 中餐厅左', 220, 25),
    14: ('2F-CT02 中餐厅右', 332, 25),
    15: ('2F-HB01 豪华包厢A', 10, 25),
    16: ('2F-HB02 豪华包厢B', 11, 25),
    17: ('2F-BX01~BX06 普通包厢', 60, 25),
    18: ('4F-KF 标准客房（16间）', 32, 30),
}
for r,(name,people,per) in nf_people.items():
    ws.cell(r,2).value=name; ws.cell(r,3).value=people; ws.cell(r,4).value=per
    ws.cell(r,5).value=f'=C{r}*D{r}'
    ws.cell(r,6).value=f'=E{r}*1.2*28.8/3600'
ws['E21']='=SUM(E13:E20)'
# method 2 table / detailed rows
nf_detail = {
    26: ('2F-CT01 中餐厅左', 286.68, 220, None, 25),
    27: ('2F-CT02 中餐厅右', 432.01, 332, None, 25),
    28: ('2F-HB01 豪华包厢A', 19.99, 10, 0.5, 25),
    29: ('2F-HB02 豪华包厢B', 21.65, 11, 0.5, 25),
    30: ('2F-BX01~BX06 普通包厢', 108.78, 60, None, 25),
    31: ('4F-KF 标准客房（26.54㎡/间×16）', 424.64, 32, None, 30),
}
for r,(name,area,people,density,per) in nf_detail.items():
    ws.cell(r,2).value=name; ws.cell(r,3).value=area; ws.cell(r,4).value=people
    ws.cell(r,5).value=density if density is not None else f'=D{r}/C{r}'
    ws.cell(r,6).value=per
    ws.cell(r,7).value=f'=D{r}*F{r}'
    ws.cell(r,8).value=f'=G{r}*1.2*28.8/3600'
# summary rows if existing
# skip merged summary cells B35:J35
# Keep formulas elsewhere intact

# ---- 风-全空气 ----
ws=wb['风-全空气']
ws['N2']='2F-CT01 中餐厅左'; ws['O2']=286.68; ws['P2']=4.2; ws['R2']=12; ws['T2']=1.1
ws['N3']='2F-CT02 中餐厅右'; ws['O3']=432.01; ws['P3']=4.2; ws['R3']=12; ws['T3']=1.1
for r in [2,3]:
    ws.cell(r,17).value=f'=O{r}*P{r}'
    ws.cell(r,19).value=f'=Q{r}*R{r}'
    ws.cell(r,21).value=f'=S{r}*T{r}'
ws['C20']='=SUM(U2:U3)'
ws['C21']=24
ws['C22']='=C20/C21'
ws['A51']='2F中餐厅全空气风管段编号'
ws['A54']='支管-中餐厅左'; ws['B54']=12; ws['C54']='=B54*C22'; ws['D54']=630; ws['F54']=320
ws['A55']='支管-中餐厅右'; ws['B55']=12; ws['C55']='=B55*C22'; ws['D55']=800; ws['F55']=320
ws['A58']='主管-中餐厅左'; ws['B58']=12; ws['C58']='=B58*C22'; ws['D58']=800; ws['F58']=320
ws['A59']='主管-中餐厅右'; ws['B59']=12; ws['C59']='=B59*C22'; ws['D59']=800; ws['F59']=320

# ---- 风-FCU+新风 ----
ws=wb['风-FCU+新风']
# wind outlet rows. B total FCU air volume; C total outlet count; D single outlet air volume.
wind_rows = {
    18: ('2F-HB01 豪华包厢A', '=房间冷负荷计算!I13*房间冷负荷计算!G13', 2, 400,400, 320,630, 250,250),
    19: ('2F-HB02 豪华包厢B', '=房间冷负荷计算!I14*房间冷负荷计算!G14', 2, 400,400, 320,630, 250,250),
    20: ('2F-BX01~BX06 普通包厢', '=房间冷负荷计算!I15*房间冷负荷计算!G15', 6, 400,400, 320,630, 250,250),
    22: ('4F-KF 标准客房（16间）', '=房间冷负荷计算!I17*房间冷负荷计算!G17', 16, 320,320, 320,500, 150,150),
}
for r,(name,b_formula,count,ea,eb,ha,hb,ka,kb) in wind_rows.items():
    ws.cell(r,1).value=name; ws.cell(r,2).value=b_formula; ws.cell(r,3).value=count; ws.cell(r,4).value=f'=B{r}/C{r}'
    ws.cell(r,5).value=ea; ws.cell(r,6).value='*'; ws.cell(r,7).value=eb
    ws.cell(r,8).value=ha; ws.cell(r,9).value='*'; ws.cell(r,10).value=hb
    ws.cell(r,11).value=ka; ws.cell(r,12).value='*'; ws.cell(r,13).value=kb
# existing new-air duct table
# 2F package new air: HB250, HB275, BX1500 -> about 2025, choose branch 200x120 where applicable, main 500x320
ws['A30']='二层包厢新风管路'
for r,seg,flow,size in [(32,'豪华包厢A支管',250,(200,120)),(33,'豪华包厢B支管',275,(200,120)),(34,'普通包厢支管合计',1500,(500,200)),(36,'二层包厢主管',2025,(500,320))]:
    ws.cell(r,1).value=seg; ws.cell(r,2).value=flow; ws.cell(r,5).value=size[0]; ws.cell(r,6).value='*'; ws.cell(r,7).value=size[1]
# 4F rooms new air 960, branch per room 60, corridor branch groups
ws['A39']='四层客房新风管路'
for r,seg,flow,size in [(41,'客房单间支管',60,(160,120)),(42,'8间客房支管',480,(320,200)),(43,'8间客房支管',480,(320,200)),(45,'四层客房主管',960,(400,250))]:
    ws.cell(r,1).value=seg; ws.cell(r,2).value=flow; ws.cell(r,5).value=size[0]; ws.cell(r,6).value='*'; ws.cell(r,7).value=size[1]
# clear stale fifth floor block labels but keep template rows
for r in range(48,57):
    if ws.cell(r,1).value not in [None,'支管段','主管段']:
        ws.cell(r,1).value='预留'

# ---- 水系统 ----
ws=wb['水系统']
def fill_water_row(r, name, kgph, vel, dn, length='按平面布置估算'):
    ws.cell(r,2).value=name; ws.cell(r,3).value=length; ws.cell(r,4).value=kgph; ws.cell(r,5).value=vel
    ws.cell(r,6).value=f'=(4*D{r}/3.14/E{r}/3600/1000)^0.5*1000'
    ws.cell(r,7).value=dn; ws.cell(r,8).value=f'=4*D{r}/3.14/G{r}^2/3.6'
def fill_water_row_m3(r, name, m3h, vel, dn, length='按平面布置估算'):
    ws.cell(r,10).value=name; ws.cell(r,11).value=length; ws.cell(r,12).value=m3h; ws.cell(r,13).value=vel
    ws.cell(r,14).value=f'=(4*L{r}/3.14/M{r}/3600)^0.5*1000'
    ws.cell(r,15).value=dn; ws.cell(r,16).value=f'=4*L{r}/3.14/O{r}^2/3.6*1000'
ws['B23']='二层'; ws['J23']='二层'
for r,name,kg,vel,dn in [
    (24,'ZK-20W6S中餐厅左',24930,2.0,80),
    (25,'ZK-25W8S中餐厅右',38020,2.0,100),
    (26,'豪华包厢FCU合计',3272,1.5,32),
    (27,'普通包厢FCU合计',6810,1.5,40),
    (28,'二层包厢新风机KD-3D',8900,1.8,50),
]:
    fill_water_row(r,name,kg,vel,dn)
    fill_water_row_m3(r,name,round(kg/1000,2),vel,dn)
for r in [29,30,31]:
    ws.cell(r,2).value='预留'; ws.cell(r,10).value='预留'
ws['B35']='四层';
for r,name,kg,vel,dn in [
    (36,'标准客房FCU合计',11552,1.8,50),
    (37,'四层客房新风机KD-2D',5900,1.6,40),
]:
    fill_water_row(r,name,kg,vel,dn)
for r in [38,39,40,41,42,43]:
    ws.cell(r,2).value='预留'
# Keep tail rows as template reserve; remove old blocking wording in working rows
ws['B82']='预留（模板尾行）'

# ---- 设备汇总表 ----
ws=wb['设备汇总表']
summary_rows = {
    5: [1,'K-2F-CT01','组合式空气处理机','ZK-20W6S',145,20000,24.93,35.86,'台',1,'本地ZK数据包，6排管'],
    6: [2,'K-2F-CT02','组合式空气处理机','ZK-25W8S',221.08,25000,38.02,43.87,'台',1,'本地ZK数据包，8排管'],
    9: [3,'FCU-2F-HB','风机盘管','FC-204',9.51,2040,1636,44,'台',2,'豪华包厢A/B，本地末端样本'],
    10:[4,'FCU-2F-BX','风机盘管','FC-136',6.60,1360,1135,19,'台',6,'普通包厢，本地末端样本'],
    11:[5,'X-2F-BX','吊挂式空气处理机组','KD-3D',52,3000,8.9,40,'台',1,'二层包厢新风，六排管候选'],
    13:[6,'FCU-4F-KF','风机盘管','FC-85',4.20,850,722,8,'台',16,'标准客房16间，本地末端样本'],
    14:[7,'X-4F-KF','吊挂式空气处理机组','KD-2D',35,2000,5.9,25,'台',1,'四层客房新风，六排管候选'],
}
for r,vals in summary_rows.items():
    for c,v in enumerate(vals, start=2):
        ws.cell(r,c).value=v
ws['L20']='备注：本表仅按模板已有字段汇总设备；风管水管深化后续按图纸复核。'

wb.save(out_calc)
wb.close()

# ---- Independent equipment selection summary workbook ----
if src_equip.exists():
    copy2(src_equip, out_equip)
    ewb=load_workbook(out_equip)
    ews=ewb[ewb.sheetnames[0]]
else:
    ewb=Workbook(); ews=ewb.active; ews.title='设备选型汇总'
headers=['序号','设备编号','设备名称','型号','制冷量','风量','水流量','水阻','单位','数量','备注']
# clear and write within simple workbook
for row in ews.iter_rows():
    for cell in row:
        cell.value=None
for c,h in enumerate(headers, start=1): ews.cell(1,c).value=h
for idx, vals in enumerate(summary_rows.values(), start=2):
    # vals already starts 序号 at first and has 11 items
    for c,v in enumerate(vals, start=1): ews.cell(idx,c).value=v
# style
fill=PatternFill('solid', fgColor='1F4E78'); font=Font(color='FFFFFF', bold=True)
for cell in ews[1]:
    cell.fill=fill; cell.font=font; cell.alignment=Alignment(horizontal='center')
ews.freeze_panes='A2'; ews.auto_filter.ref=f'A1:K{1+len(summary_rows)}'
for col in range(1,12):
    letter=get_column_letter(col); ews.column_dimensions[letter].width=16 if col!=11 else 36
    for r in range(1,2+len(summary_rows)):
        ews.cell(r,col).alignment=Alignment(vertical='top', wrap_text=True)
ewb.save(out_equip); ewb.close()

print('written', out_calc, out_equip)
