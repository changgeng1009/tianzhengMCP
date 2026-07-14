import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import os, shutil, math
from datetime import datetime

WORK = r"D:\CodexWork\天正\暖通课程设计\work"
OUT  = r"D:\CodexWork\天正\暖通课程设计\output"
SRC  = r"D:\CodexWork\天正\暖通课程设计\REDACTED_CLASS 课程设计资料\REDACTED_CLASS 课程设计资料\REDACTED_CLASS-暖通课程设计计算表 .xlsx"
os.makedirs(WORK,exist_ok=True); os.makedirs(OUT,exist_ok=True)
dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ============ PARAMETERS ============
CORR = 1.1; DH = 28.8; RHO = 1.2
# 中餐厅 (全空气) - keep existing
# 包厢 (空气-水)
BX_COLD = 330; BX_DENS = 0.5; BX_FA_P = 25; BX_H = 4.2
# 客房 (空气-水)
KF_COLD = 120; KF_DENS = 0.1; KF_FA_P = 30; KF_PERS = 2; KF_H = 4.2

# FCU models: (model, cooling_kW, airflow, water_th, water_kPa, noise_dB, BxHxD_mm)
FCU_MODELS = [
    ("FP-34",  1.8,  340,  0.31, 12, 38, "850x480x230"),
    ("FP-51",  2.7,  510,  0.47, 15, 40, "950x480x230"),
    ("FP-68",  3.6,  680,  0.62, 20, 42, "1050x480x230"),
    ("FP-85",  4.5,  850,  0.78, 25, 44, "1150x480x230"),
    ("FP-102", 5.4, 1020,  0.93, 30, 46, "1250x480x230"),
    ("FP-136", 7.2, 1360,  1.24, 35, 48, "1400x550x260"),
    ("FP-170", 9.0, 1700,  1.55, 40, 50, "1550x550x260"),
    ("FP-204", 10.8, 2040, 1.86, 45, 52, "1700x550x260"),
    ("FP-238", 13.3, 2380, 2.30, 50, 54, "1900x600x280"),
]

# Fresh air units: (model, airflow_m3h, cooling_kW, motor_kW, noise_dB)
FA_UNITS = [
    ("XF-800",   800,  12.0, 0.55, 58),
    ("XF-1000", 1000,  15.0, 0.75, 60),
    ("XF-1500", 1500,  22.5, 1.10, 62),
    ("XF-2000", 2000,  30.0, 1.50, 65),
    ("XF-3000", 3000,  45.0, 2.20, 68),
    ("XF-4000", 4000,  60.0, 3.00, 70),
]

# ============ ROOM DEFINITIONS ============
ROOMS = [
    # (code, name, area, floor, type, cold_index, person_dens, fa_per_person, system)
    ("2F-CT01", "中餐厅(左)", 286.68, 4.2, 430, 0.77, 25, "all_air", "ZK-20W6S"),
    ("2F-CT02", "中餐厅(右)", 432.01, 4.2, 430, 0.77, 25, "all_air", "ZK-25W8S"),
    ("2F-BX01", "豪华包厢1(A)", 19.99, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX02", "豪华包厢2(B)", 21.65, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX03", "普通包厢1", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX04", "普通包厢2", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX05", "普通包厢3", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX06", "普通包厢4", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX07", "普通包厢5", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("2F-BX08", "普通包厢6", 18.13, 4.2, BX_COLD, BX_DENS, BX_FA_P, "fcu_fa", None),
    ("4F-K01", "客房01", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K02", "客房02", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K03", "客房03", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K04", "客房04", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K05", "客房05", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K06", "客房06", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K07", "客房07", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K08", "客房08", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K09", "客房09", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
    ("4F-K10", "客房10", 26.10, 4.2, KF_COLD, KF_DENS, KF_FA_P, "fcu_fa", None),
]

def sel_fcu(sl):
    for m in FCU_MODELS:
        if m[1] >= sl: return m
    return FCU_MODELS[-1]

def sel_fau(flow):
    for m in FA_UNITS:
        if m[1] >= flow: return m
    return FA_UNITS[-1]

# ============ CALCULATE ALL ROOMS ============
results = []
for rd in ROOMS:
    code, name, area, H, ci, pd, fap, sys, pre_sel = rd
    V = area * H
    rl = area * ci / 1000
    sl = rl * CORR
    if sys == "all_air":
        people = area * pd
        q1 = people * fap
        q2 = 4 * area * H
        st = 12 * area * H
        q3 = st * 0.10
        fa = max(q1, q2, q3)
    else:
        if "客房" in name:
            people = KF_PERS
        else:
            people = math.ceil(area * pd)
        fa = people * fap
        q1 = fa; q2 = 0; q3 = 0; st = 0
    fal = RHO * fa * DH / 3600
    fcu = None
    if sys == "fcu_fa":
        fcu = sel_fcu(sl)
    results.append({
        "code": code, "name": name, "area": area, "H": H, "V": round(V,2),
        "ci": ci, "rl": round(rl,2), "sl": round(sl,2),
        "people": int(people), "q1": int(q1), "q2": int(q2), "q3": int(q3),
        "st": int(st), "fa": int(fa), "fal": round(fal,2),
        "sys": sys, "pre_sel": pre_sel, "fcu": fcu,
    })

# Print summary
for r in results:
    print("{} | {}m2 | RL={}kW | SL={}kW | FA={} | FAL={}kW | FCU={}".format(
        r["code"], r["area"], r["rl"], r["sl"], r["fa"], r["fal"],
        r["fcu"][0] if r["fcu"] else (r["pre_sel"] or "-")))

# ============ FA UNIT SELECTION ============
fa_2f = sum(r["fa"] for r in results if r["code"].startswith("2F-BX"))
fa_4f = sum(r["fa"] for r in results if r["code"].startswith("4F"))
print("\n=== Fresh Air Totals ===")
print(f"2F包厢总新风: {fa_2f} m3/h")
print(f"4F客房总新风: {fa_4f} m3/h")
fau_2f = sel_fau(fa_2f)
fau_4f = sel_fau(fa_4f)
print(f"2F新风机组: {fau_2f[0]} ({fau_2f[1]} m3/h, {fau_2f[2]} kW)")
print(f"4F新风机组: {fau_4f[0]} ({fau_4f[1]} m3/h, {fau_4f[2]} kW)")

# ============ STYLE HELPERS ============
def sh(ws, row, ncols, fc="4472C4"):
    fill = PatternFill(start_color=fc, end_color=fc, fill_type="solid")
    font = Font(color="FFFFFF", bold=True, size=10)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c in range(1, ncols+1):
        cell = ws.cell(row=row, column=c)
        cell.fill = fill; cell.font = font; cell.alignment = align; cell.border = bd

def sd(ws, sr, er, ncols):
    thin = Side(style="thin"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in range(sr, er+1):
        for c in range(1, ncols+1):
            cell = ws.cell(row=r, column=c)
            cell.border = bd; cell.alignment = align; cell.font = Font(size=10)

# ============ GENERATE ALL OUTPUT EXCELS ============

# --- Complete Load Calculation ---
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "冷负荷计算"
h = ["序号","楼层","房间编号","房间名称","功能类型","面积(m2)","冷负荷指标(W/m2)","房间冷负荷(kW)","修正系数","选型冷量(kW)","系统类型","备注"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h))
for idx,r in enumerate(results):
    row = idx+2
    vs = [idx+1, r["code"][:2]+"F", r["code"], r["name"], "散座" if "中餐" in r["name"] else ("包厢" if "包厢" in r["name"] else "客房"),
          r["area"], r["ci"], r["rl"], CORR, r["sl"],
          "全空气" if r["sys"]=="all_air" else "FCU+新风",
          "保有" if r["pre_sel"] else ("同型" if r["area"]==18.13 else (""))]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(results),len(h))
wb.save(os.path.join(WORK,"full_load_calculation.xlsx"))
print("\nfull_load_calculation.xlsx [OK]")

# --- Complete Fresh Air ---
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "新风量计算"
h = ["序号","编号","房间名称","面积","层高","体积","人员密度","人数","人均新风","人员法FA","FA负荷(kW)","系统"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h))
for idx,r in enumerate(results):
    row = idx+2
    vs = [idx+1, r["code"], r["name"], r["area"], r["H"], r["V"],
          BX_DENS if "包厢" in r["name"] else (KF_DENS if "客房" in r["name"] else 0.77),
          r["people"], (BX_FA_P if "包厢" in r["name"] else (KF_FA_P if "客房" in r["name"] else 25)),
          r["fa"], r["fal"], r["sys"]]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(results),len(h))
wb.save(os.path.join(WORK,"full_fresh_air_calculation.xlsx"))
print("full_fresh_air_calculation.xlsx [OK]")

# --- FCU Selection ---
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "FCU选型"
h = ["序号","编号","房间","选型冷量(kW)","型号","制冷量(kW)","风量(m3/h)","水流量(t/h)","水阻(kPa)","噪声dB","尺寸(mm)","数量"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h),"548235")
fcus = [r for r in results if r["fcu"]]
for idx,r in enumerate(fcus):
    row = idx+2; f = r["fcu"]
    vs = [idx+1, r["code"], r["name"], r["sl"], f[0], f[1], f[2], f[3], f[4], f[5], f[6], 1]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(fcus),len(h))
wb.save(os.path.join(WORK,"full_fcu_selection.xlsx"))
print("full_fcu_selection.xlsx [OK]")

# --- FA Unit Selection ---
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "新风机组选型"
h = ["序号","服务区域","总新风量(m3/h)","新风负荷(kW)","型号","风量(m3/h)","制冷量(kW)","电机(kW)","噪声dB","数量"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h),"2F5496")
fa_zones = [
    ("2F","2F包厢区", fa_2f, sum(r["fal"] for r in results if r["code"].startswith("2F-BX")), fau_2f),
    ("4F","4F客房区", fa_4f, sum(r["fal"] for r in results if r["code"].startswith("4F")), fau_4f),
]
for idx,(floor,zone,flow,total_fal,unit) in enumerate(fa_zones):
    row = idx+2
    vs = [idx+1, zone, int(flow), round(total_fal,2), unit[0], unit[1], unit[2], unit[3], unit[4], 1]
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(fa_zones),len(h))
wb.save(os.path.join(WORK,"full_fau_selection.xlsx"))
print("full_fau_selection.xlsx [OK]")

# ============ COMPLETE EXCEL TEMPLATE BACKFILL ============
shutil.copy2(SRC, os.path.join(OUT,"暖通课程设计计算表-完整填写.xlsx"))
wb = openpyxl.load_workbook(os.path.join(OUT,"暖通课程设计计算表-完整填写.xlsx"))

# Sheet: 房间冷负荷计算
ws = wb["房间冷负荷计算"]
# Rows 13-21 二层, Rows 17-19 四层
row2f = 13
for r in results:
    if r["code"] == "2F-CT01":
        ws.cell(row=13,column=1,value="二层"); ws.cell(row=13,column=2,value="中餐厅(左)")
        ws.cell(row=13,column=3,value=r["area"]); ws.cell(row=13,column=4,value=r["ci"])
    elif r["code"] == "2F-CT02":
        ws.cell(row=14,column=1,value="二层"); ws.cell(row=14,column=2,value="中餐厅(右)")
        ws.cell(row=14,column=3,value=r["area"]); ws.cell(row=14,column=4,value=r["ci"])
    elif r["code"] == "2F-BX01":
        ws.cell(row=15,column=1,value="二层"); ws.cell(row=15,column=2,value="豪华包厢A")
        ws.cell(row=15,column=3,value=r["area"]); ws.cell(row=15,column=4,value=r["ci"])
    elif r["code"] == "2F-BX02":
        ws.cell(row=16,column=1,value="二层"); ws.cell(row=16,column=2,value="豪华包厢B")
        ws.cell(row=16,column=3,value=r["area"]); ws.cell(row=16,column=4,value=r["ci"])
# Fill remaining rows 17+ for 包厢 3-8
for i in range(6):
    ws.cell(row=17+i,column=1,value="二层")
    ws.cell(row=17+i,column=2,value=f"普通包厢{i+1}")
    ws.cell(row=17+i,column=3,value=18.13); ws.cell(row=17+i,column=4,value=BX_COLD)
# 4F rows
for i in range(10):
    ws.cell(row=23+i,column=1,value="四层")
    ws.cell(row=23+i,column=2,value=f"客房{i+1:02d}")
    ws.cell(row=23+i,column=3,value=26.10); ws.cell(row=23+i,column=4,value=KF_COLD)

# Sheet: 新风量
ws2 = wb["新风量"]
# Fill method 2 table (row 28+)
all_rooms = results
for idx, r in enumerate(all_rooms):
    row = 28 + idx
    if row <= 36:
        ws2.cell(row=row,column=1,value=r["code"][:2])
        ws2.cell(row=row,column=2,value=r["name"])
        ws2.cell(row=row,column=3,value=r["area"])
        ws2.cell(row=row,column=4,value=r["people"])
        ws2.cell(row=row,column=5,value=(BX_FA_P if "包厢" in r["name"] else (KF_FA_P if "客房" in r["name"] else 25)))

# Sheet: 风-FCU+新风 - fill FCU room data
ws3 = wb["风-FCU+新风"]
# Build mapping: room area -> FCU selection
fcu_map = {r["code"]: r for r in results if r["fcu"]}
# Fill FCU+FA sheet with room data starting row 16
for idx, r in enumerate([r for r in results if r["sys"]=="fcu_fa"]):
    row = 16 + idx
    ws3.cell(row=row,column=1,value=r["code"][:2])
    ws3.cell(row=row,column=2,value=r["name"])
    ws3.cell(row=row,column=3,value=r["area"])
    ws3.cell(row=row,column=4,value=r["rl"])
    if r["fcu"]:
        ws3.cell(row=row,column=5,value=r["fcu"][0])

# Sheet: 设备汇总表
ws4 = wb["设备汇总表"]
# Clear existing may not be needed; append rows
# 二层区
eq_row = 6
# ZK units first
for idx,(code,name,model) in enumerate([("2F-AHU-01","中餐厅(左)","ZK-20W6S"),("2F-AHU-02","中餐厅(右)","ZK-25W8S")]):
    ws4.cell(row=eq_row+idx,column=1,value="二层")
    ws4.cell(row=eq_row+idx,column=2,value=idx+1)
    ws4.cell(row=eq_row+idx,column=3,value=code)
    ws4.cell(row=eq_row+idx,column=4,value="组合式空调机组")
    ws4.cell(row=eq_row+idx,column=5,value=model)
    ws4.cell(row=eq_row+idx,column=10,value="台"); ws4.cell(row=eq_row+idx,column=11,value=1)
    ws4.cell(row=eq_row+idx,column=12,value=name)

# FCU entries
eq_row = 10
fcu_types = {}
for r in results:
    if r["fcu"]:
        key = r["fcu"][0]
        if key not in fcu_types:
            fcu_types[key] = {"count":0, "rooms":[], "fcu":r["fcu"]}
        fcu_types[key]["count"] += 1
        fcu_types[key]["rooms"].append(r["name"])

for idx,(fcu_name,info) in enumerate(sorted(fcu_types.items())):
    ws4.cell(row=eq_row+idx,column=1,value="二层" if "包厢" in ",".join(info["rooms"]) else "四层")
    ws4.cell(row=eq_row+idx,column=2,value=idx+1)
    ws4.cell(row=eq_row+idx,column=3,value=f"FCU-{idx+1:02d}")
    ws4.cell(row=eq_row+idx,column=4,value="风机盘管")
    ws4.cell(row=eq_row+idx,column=5,value=info["fcu"][0])
    ws4.cell(row=eq_row+idx,column=6,value=info["fcu"][1])
    ws4.cell(row=eq_row+idx,column=7,value=info["fcu"][2])
    ws4.cell(row=eq_row+idx,column=8,value=info["fcu"][3]*1000)
    ws4.cell(row=eq_row+idx,column=9,value=info["fcu"][4])
    ws4.cell(row=eq_row+idx,column=10,value="台")
    ws4.cell(row=eq_row+idx,column=11,value=info["count"])
    ws4.cell(row=eq_row+idx,column=12,value=",".join(info["rooms"]))

# FA unit entries
eq_row_fau = eq_row + len(fcu_types)
ws4.cell(row=eq_row_fau,column=1,value="二层"); ws4.cell(row=eq_row_fau,column=2,value=len(fcu_types)+1)
ws4.cell(row=eq_row_fau,column=3,value="2F-FAU-01"); ws4.cell(row=eq_row_fau,column=4,value="新风处理机")
ws4.cell(row=eq_row_fau,column=5,value=fau_2f[0]); ws4.cell(row=eq_row_fau,column=6,value=fau_2f[2])
ws4.cell(row=eq_row_fau,column=7,value=fau_2f[1]); ws4.cell(row=eq_row_fau,column=10,value="台")
ws4.cell(row=eq_row_fau,column=11,value=1); ws4.cell(row=eq_row_fau,column=12,value="2F包厢区")

ws4.cell(row=eq_row_fau+1,column=1,value="四层"); ws4.cell(row=eq_row_fau+1,column=2,value=len(fcu_types)+2)
ws4.cell(row=eq_row_fau+1,column=3,value="4F-FAU-01"); ws4.cell(row=eq_row_fau+1,column=4,value="新风处理机")
ws4.cell(row=eq_row_fau+1,column=5,value=fau_4f[0]); ws4.cell(row=eq_row_fau+1,column=6,value=fau_4f[2])
ws4.cell(row=eq_row_fau+1,column=7,value=fau_4f[1]); ws4.cell(row=eq_row_fau+1,column=10,value="台")
ws4.cell(row=eq_row_fau+1,column=11,value=1); ws4.cell(row=eq_row_fau+1,column=12,value="4F客房区")

wb.save(os.path.join(OUT,"暖通课程设计计算表-完整填写.xlsx"))
print("\n暖通课程设计计算表-完整填写.xlsx [OK]")

# ============ EQUIPMENT SUMMARY ============
wb2 = openpyxl.Workbook(); ws = wb2.active; ws.title = "设备选型汇总"
h = ["序号","设备编号","设备名称","型号","服务区域","制冷量(kW)","风量(m3/h)","水量(t/h)","水压降(kPa)","噪声dB","电机(kW)","尺寸(mm)","数量"]
for i,v in enumerate(h,1): ws.cell(row=1,column=i,value=v)
sh(ws,1,len(h),"4472C4")

eq_items = []
# ZK
eq_items.append(("2F-AHU-01","组合式空调机组","ZK-20W6S","中餐厅(左)",145.00,20000,24.93,35.86,78,11,"1975x1900",1))
eq_items.append(("2F-AHU-02","组合式空调机组","ZK-25W8S","中餐厅(右)",221.08,25000,38.02,43.87,79,15,"2150x1900",1))

# FCU by type
for idx,(fcu_name,info) in enumerate(sorted(fcu_types.items())):
    eq_items.append((f"FCU-{idx+1:02d}","风机盘管(高静压)",info["fcu"][0],
                     ",".join(info["rooms"]),info["fcu"][1],info["fcu"][2],
                     info["fcu"][3],info["fcu"][4],info["fcu"][5],
                     "-",info["fcu"][6],info["count"]))

# FA units
eq_items.append(("2F-FAU-01","新风处理机",fau_2f[0],"2F包厢区",fau_2f[2],fau_2f[1],"-","-",fau_2f[4],fau_2f[3],"-",1))
eq_items.append(("4F-FAU-01","新风处理机",fau_4f[0],"4F客房区",fau_4f[2],fau_4f[1],"-","-",fau_4f[4],fau_4f[3],"-",1))

for idx,item in enumerate(eq_items):
    row = idx+2
    vs = [idx+1] + list(item)
    for ci,v in enumerate(vs,1): ws.cell(row=row,column=ci,value=v)
sd(ws,2,1+len(eq_items),len(h))
for c in range(1,len(h)+1): ws.column_dimensions[get_column_letter(c)].width = max(14, ws.column_dimensions[get_column_letter(c)].width)
wb2.save(os.path.join(OUT,"暖通设备选型汇总表-完整.xlsx"))
print("暖通设备选型汇总表-完整.xlsx [OK]")

print("\n=== DONE: Calculations + Backfill ===")
