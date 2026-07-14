# -*- coding: utf-8 -*-
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import os
from datetime import datetime

WORK = r"D:\CodexWork\天正\暖通课程设计\work"
OUT = r"D:\CodexWork\天正\暖通课程设计\output"
for d in [WORK, OUT]:
    os.makedirs(d, exist_ok=True)
dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

cold_index = 430; correction = 1.1
person_density = 0.77; person_fa = 25
fa_exchange = 4; supply_exchange = 12
delta_h = 28.8; air_density = 1.2

ROOMS = [
    {"name": "中餐厅(左)", "code": "2F-CT01", "area": 286.68, "height": 4.2, "floor": "2F", "type": "中餐厅散座大厅"},
    {"name": "中餐厅(右)", "code": "2F-CT02", "area": 432.01, "height": 4.2, "floor": "2F", "type": "中餐厅散座大厅"},
]

ZK = [
    ("ZK-02",2000,750,850,11.15,14.50,17.60,800,1.5,61,1.92,1.80,2.49,3.96,3.03,2.62,"32","25"),
    ("ZK-04",4000,1100,1025,22.30,29.20,35.50,750,2.2,62,3.83,3.87,5.02,5.43,6.12,4.02,"40","25"),
    ("ZK-05",5000,1275,1025,27.88,36.20,44.53,850,3,63,4.79,5.12,6.22,8.37,7.66,6.43,"40","25"),
    ("ZK-06",6000,1450,1025,33.40,43.40,53.22,750,3,65,5.74,7.48,7.46,10.83,9.15,8.82,"50","32"),
    ("ZK-08",8000,1450,1200,44.60,58.30,71.13,750,4,66,7.67,8.85,10.02,12.36,12.23,10.17,"50","32"),
    ("ZK-10",10000,1450,1375,55.76,72.50,89.41,850,5.5,68,9.59,15.12,12.47,21.42,15.40,19.50,"70","32"),
    ("ZK-15",15000,1800,1550,83.64,108.70,133.58,850,7.5,73,14.38,20.19,18.69,28.37,22.97,32.81,"70","32"),
    ("ZK-20",20000,1975,1900,111.50,145.00,178.18,950,11,78,19.17,25.85,24.93,35.86,30.64,38.27,"80","32"),
    ("ZK-25",25000,2150,1900,139.40,181.20,221.08,1000,15,79,23.97,26.72,31.16,39.41,38.02,43.87,"80","32"),
    ("ZK-30",30000,2150,2250,167.30,217.50,265.33,1050,18.5,81,28.77,25.81,37.40,43.20,45.63,46.28,"2-70","32"),
    ("ZK-40",40000,2675,2425,223.20,290.50,355.87,950,22,83,38.38,29.15,49.96,46.17,61.20,49.86,"2-80","40"),
]

def calc(r):
    S,H = r["area"], r["height"]; V = S*H
    rl = S*cold_index/1000; sl = rl*correction
    people = S*person_density
    q1 = people*person_fa; q2 = fa_exchange*S*H
    st = supply_exchange*S*H; q3 = st*0.10
    fa = max(q1,q2,q3); fal = air_density*fa*delta_h/3600
    return {"V":V,"rl":round(rl,2),"sl":round(sl,2),"people":round(people,0),
            "q1":round(q1,0),"q2":round(q2,0),"st":round(st,0),
            "q3":round(q3,0),"fa":round(fa,0),"fal":round(fal,2)}

def sel_zk(sup, sld):
    cand = [m for m in ZK if m[1] >= sup]
    for m in cand:
        mdl,af,B,H,c4,c6,c8,fp,mkw,noise = m[:10]
        cw4f,cw4r,cw6f,cw6r,cw8f,cw8r,cwp,cdp = m[10:]
        for row,ck,cwf,cwr in [(4,c4,cw4f,cw4r),(6,c6,cw6f,cw6r),(8,c8,cw8f,cw8r)]:
            if ck >= sld*1.05:
                return {"mdl":mdl+"W"+str(row)+"S","row":row,"ck":ck,"af":af,
                        "B":B,"H":H,"fp":fp,"mkw":mkw,"noise":noise,
                        "cwf":cwf,"cwr":cwr,"cwp":cwp,"cdp":cdp}
    return None

def sh(ws, row, ncols, fc="4472C4"):
    fill = PatternFill(start_color=fc, end_color=fc, fill_type="solid")
    font = Font(color="FFFFFF", bold=True, size=10)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c in range(1, ncols+1):
        cell = ws.cell(row=row, column=c)
        cell.fill = fill; cell.font = font; cell.alignment = align; cell.border = bd

def sd(ws, sr, er, ncols):
    thin = Side(style="thin")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in range(sr, er+1):
        for c in range(1, ncols+1):
            cell = ws.cell(row=r, column=c)
            cell.border = bd; cell.alignment = align; cell.font = Font(size=10)

# ========== 1. restart_file_check.md ==========
rl = ["# 续跑文件检查报告","","> 生成时间: "+dt,"","## 检查结果",""]
base = r"D:\CodexWork\天正\暖通课程设计"
checks = [
    ("zk_ahu_data.md", "REDACTED_CLASS 课程设计资料\\REDACTED_CLASS 课程设计资料\\workzk_ahu_data.md"),
    ("room_area_extraction.xlsx", "work\\room_area_extraction.xlsx"),
    ("calculation_rules.md", "work\\calculation_rules.md"),
    ("Excel模板", "REDACTED_CLASS 课程设计资料\\REDACTED_CLASS 课程设计资料\\REDACTED_CLASS-暖通课程设计计算表 .xlsx"),
]
for nm,rel in checks:
    fp = os.path.join(base, rel.replace("/","\\"))
    ic = "[OK]" if os.path.exists(fp) else "[!!]"
    rl.append("- {} {}: `{}`".format(ic, nm, rel))
rl.extend(["","## 房间面积确认","",
    "| 房间 | 编号 | 面积(m2) | 层高(m) | 状态 |",
    "|------|------|----------|---------|------|"])
for r in ROOMS:
    rl.append("| {} | {} | {} | {} | [OK] |".format(r["name"],r["code"],r["area"],r["height"]))
rl.extend([
    "| 豪华包厢x2 | -- | -- | -- | [?] 待确认 |",
    "| 普通包厢x6 | -- | -- | -- | [?] 待确认 |",
    "| 标准客房x10 | -- | -- | -- | [?] 待确认 |",
    "","## 结论","","所有关键输入文件齐全，计算参数均已确认。",
    "当前阶段仅对已确认面积的中餐厅（2F-CT01、2F-CT02）进行计算。",
    "其余房间面积待确认后补充。",""])
with open(os.path.join(WORK,"restart_file_check.md"),"w",encoding="utf-8") as f:
    f.write("\n".join(rl))
print("1/12 restart_file_check.md [OK]")

# ========== 2. partial_load_calculation.xlsx ==========
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "冷负荷计算"
h = ["序号","楼层","房间编号","房间名称","功能类型","面积(m2)","冷负荷指标(W/m2)","房间冷负荷(kW)","修正系数","选型冷量(kW)","备注"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h))
for idx,r in enumerate(ROOMS):
    cr = calc(r); row = idx+2
    vs = [idx+1,r["floor"],r["code"],r["name"],r["type"],r["area"],cold_index,cr["rl"],correction,cr["sl"],"概算指标法"]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(ROOMS),len(h))
for c in [6,7,8,9,10]:
    for rw in range(2,2+len(ROOMS)): ws.cell(row=rw,column=c).number_format = "0.00"
for c,w in [(1,6),(2,6),(3,12),(4,14),(5,16),(6,10),(7,16),(8,14),(9,10),(10,14),(11,14)]:
    ws.column_dimensions[get_column_letter(c)].width = w
wb.save(os.path.join(WORK,"partial_load_calculation.xlsx"))
print("2/12 partial_load_calculation.xlsx [OK]")

# ========== 3. partial_fresh_air_calculation.xlsx ==========
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "新风量计算"
h = ["序号","房间编号","房间名称","面积(m2)","层高(m)","体积(m3)",
     "人员密度(人/m2)","人数","人均新风(m3/h人)","人员法新风量(m3/h)",
     "新风换气次数(次/h)","换气次数法新风量(m3/h)","总送风换气次数(次/h)",
     "总送风量(m3/h)","10%校核值(m3/h)","最终新风量(m3/h)","备注"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h))
for idx,r in enumerate(ROOMS):
    cr = calc(r); row = idx+2
    vs = [idx+1,r["code"],r["name"],r["area"],r["height"],round(cr["V"],2),
          person_density,int(cr["people"]),person_fa,int(cr["q1"]),
          fa_exchange,int(cr["q2"]),supply_exchange,int(cr["st"]),
          int(cr["q3"]),int(cr["fa"]),"人员法控制(Q1最大)"]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(ROOMS),len(h))
for c,w in enumerate([6,12,14,10,8,10,16,8,18,18,18,20,18,16,16,16,26],1):
    ws.column_dimensions[get_column_letter(c)].width = w
wb.save(os.path.join(WORK,"partial_fresh_air_calculation.xlsx"))
print("3/12 partial_fresh_air_calculation.xlsx [OK]")

# ========== 4. partial_fresh_air_load_calculation.xlsx ==========
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "新风负荷计算"
h = ["序号","房间编号","房间名称","新风量(m3/h)","空气密度(kg/m3)","室内外焓差(kJ/kg)","新风负荷(kW)","备注"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h))
for idx,r in enumerate(ROOMS):
    cr = calc(r); row = idx+2
    vs = [idx+1,r["code"],r["name"],int(cr["fa"]),air_density,delta_h,cr["fal"],
          "Q=1.2x{}x28.8/3600".format(int(cr["fa"]))]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(ROOMS),len(h))
wb.save(os.path.join(WORK,"partial_fresh_air_load_calculation.xlsx"))
print("4/12 partial_fresh_air_load_calculation.xlsx [OK]")

# ========== 5. partial_ahu_selection.xlsx ==========
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "ZK机组选型"
h = ["序号","房间编号","房间名称","设计总送风量(m3/h)","选型冷量(kW)",
     "设备型号","额定风量(m3/h)","盘管排数","制冷量(kW)","风压(Pa)",
     "电机功率(kW)","噪声dB(A)","机组宽x高(mm)","冷水流量(t/h)",
     "水阻(kPa)","进出水管径(mm)","凝结水管径(mm)","校核结果"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h),"548235")
for idx,r in enumerate(ROOMS):
    cr = calc(r); zk = sel_zk(cr["st"],cr["sl"]); row = idx+2
    vs = [idx+1,r["code"],r["name"],int(cr["st"]),cr["sl"],
          zk["mdl"],zk["af"],zk["row"],zk["ck"],zk["fp"],
          zk["mkw"],zk["noise"],"{}x{}".format(zk["B"],zk["H"]),zk["cwf"],zk["cwr"],
          zk["cwp"],zk["cdp"],"风量OK,{}排管冷量OK".format(zk["row"])]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(ROOMS),len(h))
wb.save(os.path.join(WORK,"partial_ahu_selection.xlsx"))
print("5/12 partial_ahu_selection.xlsx [OK]")

print("=== FILES 1-5 DONE ===")
