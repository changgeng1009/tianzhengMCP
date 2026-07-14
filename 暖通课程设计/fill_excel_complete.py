#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
暖通课程设计计算表填写脚本 - 李宇杰
学号: 52, 班级: REDACTED_CLASS, 策略: 紧凑型
完整版：计算 + 设备选型 + Excel填写
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import json, math, shutil, openpyxl

# ============================================================
# CONSTANTS
# ============================================================
BASE = r"D:\CodexWork\天正\暖通课程设计"
TEMPLATE = BASE + r"\REDACTED_CLASS 课程设计资料\REDACTED_CLASS 课程设计资料\REDACTED_CLASS-暖通课程设计计算表 .xlsx"
OUTPUT = BASE + r"\李宇杰_52_暖通课程设计计算表_修正版.xlsx"
JSON_EQ = BASE + r"\暖通课程设计_AI计算完整包_v1.0\hvac_equipment_database_ZK_FC_KD_v2.0.json"

AIR_DENSITY = 1.2
ENTHALPY_DIFF = 28.8
FRESH_COEFF = AIR_DENSITY * ENTHALPY_DIFF / 3600  # = 0.0096
COOLING_MARGIN = 1.10

# ============================================================
# 1. COPY TEMPLATE
# ============================================================
print("Step 1: Copying template...")
shutil.copy2(TEMPLATE, OUTPUT)

# ============================================================
# 2. CALCULATIONS
# ============================================================
print("Step 2: Calculations...")

# Room data per prompt
rooms = {
    "左中餐厅": dict(area=348.17, count=1, cool_idx=430,
                     height=4.2, supply_ach=12, supply_margin=1.10,
                     fresh_ach=4, fp=25, person_rule="floor", pp=1.3, sys="ZK"),
    "右中餐厅": dict(area=203.75, count=1, cool_idx=430,
                     height=4.2, supply_ach=12, supply_margin=1.10,
                     fresh_ach=4, fp=25, person_rule="floor", pp=1.3, sys="ZK"),
    "豪华包厢": dict(area=28.54, count=6, cool_idx=330, fp=25,
                     person_rule="ceil_div2", pp=2, sys="FC"),
    "普通包厢": dict(area=29.03, count=6, cool_idx=330, fp=25,
                     person_rule="ceil_div2", pp=2, sys="FC"),
    "标准客房": dict(area=26.40, count=12, cool_idx=120, fp=30,
                     person_rule="fixed2", sys="FC"),
}

for name, r in rooms.items():
    # Persons
    if r["person_rule"] == "floor":
        r["sp"] = math.floor(r["area"] / r["pp"])
    elif r["person_rule"] == "ceil_div2":
        r["sp"] = math.ceil(r["area"] / r["pp"])
    elif r["person_rule"] == "fixed2":
        r["sp"] = 2
    r["tp"] = r["sp"] * r["count"]
    # Cooling
    r["sc"] = r["area"] * r["cool_idx"] / 1000
    r["ss"] = r["sc"] * COOLING_MARGIN
    r["tc"] = r["sc"] * r["count"]
    # Fresh air per room
    r["sf"] = r["sp"] * r["fp"]
    # ZK-specific
    if r["sys"] == "ZK":
        r["vol"] = r["area"] * r["height"]
        r["sa"] = r["area"] * r["height"] * r["supply_ach"] * r["supply_margin"]
        r["f1"] = r["tp"] * r["fp"]
        r["f2"] = r["area"] * r["height"] * r["fresh_ach"]
        r["f3"] = r["sa"] * 0.10
        r["df"] = max(r["f1"], r["f2"], r["f3"])
        r["fl"] = r["df"] * FRESH_COEFF
    else:
        r["fl"] = r["sf"] * FRESH_COEFF

# KD aggregates
box_tf = rooms["豪华包厢"]["sf"] * 6 + rooms["普通包厢"]["sf"] * 6
box_sf = box_tf * 1.10
box_fl = box_tf * FRESH_COEFF

guest_tf = rooms["标准客房"]["sf"] * 12
guest_sf = guest_tf * 1.10
guest_fl = guest_tf * FRESH_COEFF

# ============================================================
# 3. EQUIPMENT SELECTION
# ============================================================
print("Step 3: Equipment selection...")
with open(JSON_EQ, 'r', encoding='utf-8') as f:
    eq = json.load(f)

zk_models = eq["zk"]["models"]
fc_units = eq["fc"]["concealed_units"]
fc_dim = {d["model"]: d for d in eq["fc"]["concealed_dimensions"]}
kd_perf = eq["kd"]["hanging_air_handler"]["performance"]

# --- ZK ---
def sel_zk(sa_val, ss_val, name):
    candidates = []
    for m in zk_models:
        if m["nominal_airflow_m3h"] < sa_val:
            continue
        for rows in [4, 6, 8]:
            ck = f"cooling_{rows}row_kw"
            if ck not in m: continue
            rc = m[ck]
            ratio = rc / ss_val
            if ratio < 1.05 or ratio > 1.30: continue
            sa_sec = m["section_width_mm"] * m["section_height_mm"] / 1e6
            fv = sa_val / (3600 * sa_sec)
            if fv < 1.0 or fv > 3.5: continue
            wfk = f"cooling_water_flow_{rows}row_t_h"
            wdk = f"cooling_water_drop_{rows}row_kpa"
            candidates.append(dict(
                model=m["model"], rows=rows, rc=rc, ratio=ratio,
                sw=m["section_width_mm"], sh=m["section_height_mm"],
                sa_sec=sa_sec, fv=fv, na=m["nominal_airflow_m3h"],
                fp_pa=m["fan_pressure_pa"], mp=m["motor_power_kw_text"],
                noise=m["noise_dba"],
                wf=m.get(wfk, 0), wd=m.get(wdk, 0),
                wp=m["cooling_water_pipe_mm"]))
    candidates.sort(key=lambda c: (c["sw"]*c["sh"], abs(c["ratio"]-1.10)))
    for i, c in enumerate(candidates[:5]):
        print(f"  ZK-{name} [{i+1}] {c['model']} {c['rows']}row: {c['rc']}kW r={c['ratio']:.3f} {c['sw']}x{c['sh']}mm")
    return candidates[0] if candidates else None

zk_l = sel_zk(rooms["左中餐厅"]["sa"], rooms["左中餐厅"]["ss"], "左中餐厅")
zk_r = sel_zk(rooms["右中餐厅"]["sa"], rooms["右中餐厅"]["ss"], "右中餐厅")

# --- FC ---
def sel_fc(ss_val, name):
    candidates = []
    for u in fc_units:
        if u["coil_configuration"] not in ["2排管", "3排管"]: continue
        rc = u["rated_cooling_kw"]
        ratio = rc / ss_val
        if ratio < 1.05 or ratio > 1.30: continue
        dim = fc_dim.get(u["model"])
        if not dim: continue
        mp = u["motor_power_W"].get("50Pa") or u["motor_power_W"].get("30Pa") or u["motor_power_W"].get("12Pa")
        mp_w = int(mp["input"]) if isinstance(mp, dict) and "input" in mp else (int(mp) if isinstance(mp, str) else 0)
        nz = u["noise_dba"].get("50Pa") or u["noise_dba"].get("30Pa") or 0
        candidates.append(dict(
            model=u["model"], coil=u["coil_configuration"], rc=rc, ratio=ratio,
            af=u["airflow_m3h"]["high"], wf=u["water_flow_kg_h"], wd=u["water_pressure_drop_kpa"],
            da=dim["A_mm"], db=dim["B_mm"], dc=dim["C_mm"],
            mp=mp_w, noise=nz))
    candidates.sort(key=lambda c: (c["da"]*c["db"], 0 if c["coil"]=="3排管" else 1))
    for i, c in enumerate(candidates[:5]):
        print(f"  FC-{name} [{i+1}] FC-{c['model']} {c['coil']}: {c['rc']}kW r={c['ratio']:.3f} {c['da']}x{c['db']}x{c['dc']}mm")
    return candidates[0] if candidates else None

fc_lx = sel_fc(rooms["豪华包厢"]["ss"], "豪华包厢")
fc_pt = sel_fc(rooms["普通包厢"]["ss"], "普通包厢")
fc_kf = sel_fc(rooms["标准客房"]["ss"], "标准客房")

# --- KD (Hanging, Fresh Air) ---
def sel_kd(sa_val, fl_val, name):
    candidates = []
    for u in kd_perf:
        fd = u.get("fresh_condition")
        if not fd: continue
        af = u["airflow_m3h"]
        if af < sa_val: continue
        rc = fd["cooling_kw"]
        ratio = rc / fl_val if fl_val > 0 else 999
        if ratio < 1.0: continue
        esp = u["external_static_pa"]
        if isinstance(esp, dict): esp = esp.get("class_I", esp.get("class_II", 0))
        mp = u["motor_power_kw"]
        if isinstance(mp, dict): mp = mp.get("class_I", mp.get("class_II", "0"))
        candidates.append(dict(
            model=u["model"], rows=u["coil_rows"], af=af, rc=rc, ratio=ratio,
            wf=fd["water_flow_m3h"], wd=fd["water_drop_kpa"],
            esp=esp, mp=mp, wt=u.get("weight_kg","?")))
    candidates.sort(key=lambda c: (c["af"], abs(c["ratio"]-1.15)))
    for i, c in enumerate(candidates[:5]):
        print(f"  KD-{name} [{i+1}] {c['model']} {c['rows']}row: air={c['af']} cool={c['rc']}kW r={c['ratio']:.3f} ESP={c['esp']}Pa motor={c['mp']}kW")
    return candidates[0] if candidates else None

kd_2 = sel_kd(box_sf, box_fl, "二层包厢")
kd_4 = sel_kd(guest_sf, guest_fl, "四层客房")

print("\n=== FINAL SELECTION ===")
for label, s in [("左ZK",zk_l),("右ZK",zk_r),("豪FC",fc_lx),("普FC",fc_pt),("客FC",fc_kf),("2KD",kd_2),("4KD",kd_4)]:
    if s:
        if "sw" in s:
            print(f"  {label}: {s['model']} {s['rows']}row {s['rc']}kW {s['sw']}x{s['sh']}mm wf={s['wf']}t/h wd={s['wd']}kPa")
        elif "da" in s:
            print(f"  {label}: FC-{s['model']} {s['coil']} {s['rc']}kW {s['da']}x{s['db']}mm wf={s['wf']}kg/h wd={s['wd']}kPa mp={s['mp']}W")
        else:
            print(f"  {label}: {s['model']} {s['rows']}row air={s['af']} cool={s['rc']}kW wf={s['wf']}m³/h wd={s['wd']}kPa mp={s['mp']}kW")
    else:
        print(f"  {label}: FAILED!")

# ============================================================
# 4. FILL EXCEL
# ============================================================
print("\nStep 4: Filling Excel...")
wb = openpyxl.load_workbook(OUTPUT)

# --- Helper: set cell value, handling merged cells ---
def sv(ws, cell, value):
    """Set cell value. If merged, write to the top-left cell of the merge range."""
    try:
        ws[cell] = value
    except AttributeError:
        # It's a MergedCell - find the parent merge range
        for mr in ws.merged_cells.ranges:
            if cell in mr:
                tl = mr.min_row, mr.min_col
                ws.cell(row=tl[0], column=tl[1], value=value)
                return
        # Fallback: try unmerge first then set
        print(f"  WARNING: Cannot set merged cell {cell}")

# ---------- 4a. 设计说明 ----------
print("  4a. 设计说明...")
ws_ds = wb["设计说明"]
# Update existing content with student info (row 62-63 area)
for row in ws_ds.iter_rows(min_row=1, max_row=ws_ds.max_row):
    for c in row:
        v = c.value
        if v is not None and isinstance(v, str) and "REDACTED_PERSON_7" in v:
            c.value = v.replace("REDACTED_PERSON_7", "李宇杰")
# Try to fill student info in known locations
ws_ds["A60"] = "设计人：李宇杰"
ws_ds["A61"] = "学号：52"
ws_ds["A62"] = "班级：REDACTED_CLASS"

# ---------- 4b. 室内外设计参数 ----------
print("  4b. 室内外设计参数...")
ws_cs = wb["室内外设计参数"]
# Already has correct values from template (34.2/27.5 etc), keep as-is
# Update project location if needed
ws_cs["E2"] = "南宁"

# ---------- 4c. 房间冷负荷计算 ----------
print("  4c. 房间冷负荷计算...")
ws_lh = wb["房间冷负荷计算"]

# Template rows:
# R13=二层, R14-15, R16=四层, R17-19, R20=汇总, R21-23
# We need to fill: rows 13-23 with our room data
# Headers at row 10-12: A=房间名称 B=面积 C=冷负荷指标 D=房间冷负荷 E=选型冷量 F=型号 G=数量 H=制冷量 I=风量 J=水流量 K=水压降

# 二层 section (rows 13-15)
# Row 13: 左中餐厅
sv(ws_lh, "A13", "左中餐厅")
sv(ws_lh, "B13", rooms["左中餐厅"]["area"])
sv(ws_lh, "C13", rooms["左中餐厅"]["cool_idx"])
# D13 formula: =B13*C13/1000
sv(ws_lh, "D13", round(rooms["左中餐厅"]["sc"], 3))
# E13 formula: =D13*1.1
sv(ws_lh, "E13", round(rooms["左中餐厅"]["ss"], 3))
sv(ws_lh, "F13", zk_l["model"])
sv(ws_lh, "G13", rooms["左中餐厅"]["count"])
sv(ws_lh, "H13", zk_l["rc"])
sv(ws_lh, "I13", zk_l["na"])  # nominal airflow for ZK
sv(ws_lh, "J13", round(zk_l["wf"] * 1000, 0))  # convert t/h to kg/h
sv(ws_lh, "K13", zk_l["wd"])

# Row 14: 右中餐厅
sv(ws_lh, "A14", "右中餐厅")
sv(ws_lh, "B14", rooms["右中餐厅"]["area"])
sv(ws_lh, "C14", rooms["右中餐厅"]["cool_idx"])
sv(ws_lh, "D14", round(rooms["右中餐厅"]["sc"], 3))
sv(ws_lh, "E14", round(rooms["右中餐厅"]["ss"], 3))
sv(ws_lh, "F14", zk_r["model"])
sv(ws_lh, "G14", rooms["右中餐厅"]["count"])
sv(ws_lh, "H14", zk_r["rc"])
sv(ws_lh, "I14", zk_r["na"])
sv(ws_lh, "J14", round(zk_r["wf"] * 1000, 0))
sv(ws_lh, "K14", zk_r["wd"])

# Row 15: 豪华包厢 (representative)
sv(ws_lh, "A15", "豪华包厢")
sv(ws_lh, "B15", rooms["豪华包厢"]["area"])
sv(ws_lh, "C15", rooms["豪华包厢"]["cool_idx"])
sv(ws_lh, "D15", round(rooms["豪华包厢"]["sc"], 3))
sv(ws_lh, "E15", round(rooms["豪华包厢"]["ss"], 3))
sv(ws_lh, "F15", f"FC-{fc_lx['model']}")
sv(ws_lh, "G15", rooms["豪华包厢"]["count"])
sv(ws_lh, "H15", fc_lx["rc"])
sv(ws_lh, "I15", fc_lx["af"])
sv(ws_lh, "J15", fc_lx["wf"])
sv(ws_lh, "K15", fc_lx["wd"])

# 四层 section (rows 16-19)
sv(ws_lh, "A16", "四层")

# Row 17: 普通包厢 (representative) - template row 17 was for 四层/客房, we adapt
sv(ws_lh, "A17", "普通包厢")
sv(ws_lh, "B17", rooms["普通包厢"]["area"])
sv(ws_lh, "C17", rooms["普通包厢"]["cool_idx"])
sv(ws_lh, "D17", round(rooms["普通包厢"]["sc"], 3))
sv(ws_lh, "E17", round(rooms["普通包厢"]["ss"], 3))
sv(ws_lh, "F17", f"FC-{fc_pt['model']}")
sv(ws_lh, "G17", rooms["普通包厢"]["count"])
sv(ws_lh, "H17", fc_pt["rc"])
sv(ws_lh, "I17", fc_pt["af"])
sv(ws_lh, "J17", fc_pt["wf"])
sv(ws_lh, "K17", fc_pt["wd"])

# Row 18: 标准客房 (representative)
sv(ws_lh, "A18", "标准客房")
sv(ws_lh, "B18", rooms["标准客房"]["area"])
sv(ws_lh, "C18", rooms["标准客房"]["cool_idx"])
sv(ws_lh, "D18", round(rooms["标准客房"]["sc"], 3))
sv(ws_lh, "E18", round(rooms["标准客房"]["ss"], 3))
sv(ws_lh, "F18", f"FC-{fc_kf['model']}")
sv(ws_lh, "G18", rooms["标准客房"]["count"])
sv(ws_lh, "H18", fc_kf["rc"])
sv(ws_lh, "I18", fc_kf["af"])
sv(ws_lh, "J18", fc_kf["wf"])
sv(ws_lh, "K18", fc_kf["wd"])

# Row 19: empty or merge
sv(ws_lh, "A19", None)

# 汇总 section (rows 20-23)
sv(ws_lh, "A20", "汇总")
# Row 21-23: totals by floor/system
sv(ws_lh, "A21", "二层合计")
sv(ws_lh, "B21", rooms["左中餐厅"]["area"] + rooms["右中餐厅"]["area"] + rooms["豪华包厢"]["area"] * 6 + rooms["普通包厢"]["area"] * 6)
total_2f_cool = rooms["左中餐厅"]["tc"] + rooms["右中餐厅"]["tc"] + rooms["豪华包厢"]["tc"] + rooms["普通包厢"]["tc"]
sv(ws_lh, "D21", round(total_2f_cool, 3))

sv(ws_lh, "A22", "四层合计")
sv(ws_lh, "B22", rooms["标准客房"]["area"] * 12)
sv(ws_lh, "D22", round(rooms["标准客房"]["tc"], 3))

sv(ws_lh, "A23", "总计")
sv(ws_lh, "B23", rooms["左中餐厅"]["area"] + rooms["右中餐厅"]["area"] + rooms["豪华包厢"]["area"] * 6 + rooms["普通包厢"]["area"] * 6 + rooms["标准客房"]["area"] * 12)
sv(ws_lh, "D23", round(total_2f_cool + rooms["标准客房"]["tc"], 3))

# ---------- 4d. 新风量 ----------
print("  4d. 新风量...")
ws_xf = wb["新风量"]

# Section 1: rows 10-21 (density-based)
# Row 13: 左中餐厅
sv(ws_xf, "B13", "左中餐厅")
sv(ws_xf, "C13", rooms["左中餐厅"]["tp"])
sv(ws_xf, "D13", 25)
sv(ws_xf, "E13", rooms["左中餐厅"]["df"])
sv(ws_xf, "F13", round(rooms["左中餐厅"]["fl"], 3))

# Row 14: 右中餐厅
sv(ws_xf, "B14", "右中餐厅")
sv(ws_xf, "C14", rooms["右中餐厅"]["tp"])
sv(ws_xf, "D14", 25)
sv(ws_xf, "E14", rooms["右中餐厅"]["df"])
sv(ws_xf, "F14", round(rooms["右中餐厅"]["fl"], 3))

# Row 15: 豪华包厢
sv(ws_xf, "B15", "豪华包厢")
sv(ws_xf, "C15", rooms["豪华包厢"]["tp"])
sv(ws_xf, "D15", 25)
sv(ws_xf, "E15", rooms["豪华包厢"]["sf"] * 6)
sv(ws_xf, "F15", round(rooms["豪华包厢"]["fl"] * 6, 3))

# Row 16: 普通包厢
sv(ws_xf, "B16", "普通包厢")
sv(ws_xf, "C16", rooms["普通包厢"]["tp"])
sv(ws_xf, "D16", 25)
sv(ws_xf, "E16", rooms["普通包厢"]["sf"] * 6)
sv(ws_xf, "F16", round(rooms["普通包厢"]["fl"] * 6, 3))

# Row 17: 标准客房
sv(ws_xf, "B17", "标准客房")
sv(ws_xf, "C17", rooms["标准客房"]["tp"])
sv(ws_xf, "D17", 30)
sv(ws_xf, "E17", guest_tf)
sv(ws_xf, "F17", round(guest_fl, 3))

# Row 21: total
sv(ws_xf, "E21", rooms["左中餐厅"]["df"] + rooms["右中餐厅"]["df"] + box_tf + guest_tf)

# Section 2: rows 22-32 (density method)
# Row 26: 左中餐厅
sv(ws_xf, "B26", "左中餐厅")
sv(ws_xf, "C26", rooms["左中餐厅"]["area"])
sv(ws_xf, "D26", rooms["左中餐厅"]["tp"])
sv(ws_xf, "F26", 25)
sv(ws_xf, "G26", rooms["左中餐厅"]["f1"])
sv(ws_xf, "H26", round(rooms["左中餐厅"]["f1"] * FRESH_COEFF, 3))

# Row 27: 右中餐厅
sv(ws_xf, "B27", "右中餐厅")
sv(ws_xf, "C27", rooms["右中餐厅"]["area"])
sv(ws_xf, "D27", rooms["右中餐厅"]["tp"])
sv(ws_xf, "F27", 25)
sv(ws_xf, "G27", rooms["右中餐厅"]["f1"])
sv(ws_xf, "H27", round(rooms["右中餐厅"]["f1"] * FRESH_COEFF, 3))

# Row 28: 豪华包厢
sv(ws_xf, "B28", "豪华包厢")
sv(ws_xf, "C28", rooms["豪华包厢"]["area"])
sv(ws_xf, "D28", rooms["豪华包厢"]["sp"])
sv(ws_xf, "F28", 25)
sv(ws_xf, "G28", rooms["豪华包厢"]["sf"])
sv(ws_xf, "H28", round(rooms["豪华包厢"]["fl"], 3))

# Row 29: 普通包厢
sv(ws_xf, "B29", "普通包厢")
sv(ws_xf, "C29", rooms["普通包厢"]["area"])
sv(ws_xf, "D29", rooms["普通包厢"]["sp"])
sv(ws_xf, "F29", 25)
sv(ws_xf, "G29", rooms["普通包厢"]["sf"])
sv(ws_xf, "H29", round(rooms["普通包厢"]["fl"], 3))

# Row 30: 标准客房
sv(ws_xf, "B30", "标准客房")
sv(ws_xf, "C30", rooms["标准客房"]["area"])
sv(ws_xf, "D30", rooms["标准客房"]["sp"])
sv(ws_xf, "F30", 30)
sv(ws_xf, "G30", rooms["标准客房"]["sf"])
sv(ws_xf, "H30", round(rooms["标准客房"]["fl"], 3))

# Row 32: total
sv(ws_xf, "G32", rooms["左中餐厅"]["f1"] + rooms["右中餐厅"]["f1"] + rooms["豪华包厢"]["sf"]*6 + rooms["普通包厢"]["sf"]*6 + guest_tf)

# Section 3: KD selection rows 33-36
sv(ws_xf, "B34", "二层包厢")
sv(ws_xf, "C34", kd_2["model"])
sv(ws_xf, "D34", kd_2["rc"])
sv(ws_xf, "E34", kd_2["af"])
sv(ws_xf, "F34", kd_2["wf"])
sv(ws_xf, "H34", kd_2["wd"])
sv(ws_xf, "I34", kd_2["esp"])
sv(ws_xf, "J34", float(kd_2["mp"]) if isinstance(kd_2["mp"], str) else kd_2["mp"])

sv(ws_xf, "B35", "四层客房")
sv(ws_xf, "C35", kd_4["model"])
sv(ws_xf, "D35", kd_4["rc"])
sv(ws_xf, "E35", kd_4["af"])
sv(ws_xf, "F35", kd_4["wf"])
sv(ws_xf, "H35", kd_4["wd"])
sv(ws_xf, "I35", kd_4["esp"])
sv(ws_xf, "J35", float(kd_4["mp"]) if isinstance(kd_4["mp"], str) else kd_4["mp"])

# ---------- 4e. 风-全空气 ----------
print("  4e. 风-全空气...")
ws_qk = wb["风-全空气"]

# 左中餐厅 (rows 2-): N2=左中餐厅, O2=area, P2=height, Q2=volume, R2=ACH, S2=supply, T2=margin, U2=total
sv(ws_qk, "N2", "左中餐厅")
sv(ws_qk, "O2", rooms["左中餐厅"]["area"])
sv(ws_qk, "P2", rooms["左中餐厅"]["height"])
sv(ws_qk, "Q2", rooms["左中餐厅"]["vol"])
sv(ws_qk, "R2", rooms["左中餐厅"]["supply_ach"])
sv(ws_qk, "S2", rooms["左中餐厅"]["vol"] * rooms["左中餐厅"]["supply_ach"])
sv(ws_qk, "T2", rooms["左中餐厅"]["supply_margin"])
sv(ws_qk, "U2", rooms["左中餐厅"]["sa"])

# Row 3: 右中餐厅
sv(ws_qk, "N3", "右中餐厅")
sv(ws_qk, "O3", rooms["右中餐厅"]["area"])
sv(ws_qk, "P3", rooms["右中餐厅"]["height"])
sv(ws_qk, "Q3", rooms["右中餐厅"]["vol"])
sv(ws_qk, "R3", rooms["右中餐厅"]["supply_ach"])
sv(ws_qk, "S3", rooms["右中餐厅"]["vol"] * rooms["右中餐厅"]["supply_ach"])
sv(ws_qk, "T3", rooms["右中餐厅"]["supply_margin"])
sv(ws_qk, "U3", rooms["右中餐厅"]["sa"])

# Supply outlet calculation: C20 m3/h, C21 outlets, C22 per outlet
# Use the existing formulas but update the total airflow
sv(ws_qk, "C20", rooms["左中餐厅"]["sa"])
sv(ws_qk, "C21", 12)  # fixed 12 outlets per room
sv(ws_qk, "C22", round(rooms["左中餐厅"]["sa"] / 12, 1))
# Return air
sv(ws_qk, "C32", rooms["左中餐厅"]["sa"])
sv(ws_qk, "C33", 1)
sv(ws_qk, "C34", round(rooms["左中餐厅"]["sa"], 1))

# ZK equipment info - fill in rows around 50-55
# Rows for ZK parameters
for row in ws_qk.iter_rows(min_row=48, max_row=62):
    for c in row:
        v = c.value
        if v is not None and isinstance(v, str) and "ZK-" in v:
            if "左" in str(ws_qk.cell(row=c.row, column=1).value or ""):
                continue
            # Just note the existing ZK references

# ---------- 4f. 风-FCU+新风 ----------
print("  4f. 风-FCU+新风...")
ws_fcu = wb["风-FCU+新风"]

# Outlet calculation table (rows 15-25)
# Row 18: 豪华包厢
sv(ws_fcu, "A18", "豪华包厢")
sv(ws_fcu, "B18", fc_lx["af"])  # FC airflow
sv(ws_fcu, "C18", 2)  # 2 outlets
sv(ws_fcu, "D18", round(fc_lx["af"] / 2, 1))
sv(ws_fcu, "E18", 400)
sv(ws_fcu, "G18", 400)

# Row 19: 普通包厢
sv(ws_fcu, "A19", "普通包厢")
sv(ws_fcu, "B19", fc_pt["af"])
sv(ws_fcu, "C19", 2)
sv(ws_fcu, "D19", round(fc_pt["af"] / 2, 1))
sv(ws_fcu, "E19", 400)
sv(ws_fcu, "G19", 400)

# Row 20: 标准客房 - template had 包厢
sv(ws_fcu, "A20", "标准客房")
sv(ws_fcu, "B20", fc_kf["af"])
sv(ws_fcu, "C20", 1)
sv(ws_fcu, "D20", fc_kf["af"])
sv(ws_fcu, "E20", 320)
sv(ws_fcu, "G20", 320)

# Fresh air duct section (rows 27-56)
# 二层 branch ducts
sv(ws_fcu, "A31", "豪华包厢支管")
sv(ws_fcu, "B31", rooms["豪华包厢"]["sf"])
sv(ws_fcu, "E31", 200)
sv(ws_fcu, "G31", 120)

sv(ws_fcu, "A32", "普通包厢支管")
sv(ws_fcu, "B32", rooms["普通包厢"]["sf"])
sv(ws_fcu, "E32", 200)
sv(ws_fcu, "G32", 120)

sv(ws_fcu, "A33", "二层包厢支管合计")
sv(ws_fcu, "B33", box_tf)

sv(ws_fcu, "A35", "二层包厢主管")
sv(ws_fcu, "B35", box_tf)

# Supply/return/fresh outlets for luxury box
sv(ws_fcu, "H18", 630)  # return a
sv(ws_fcu, "I18", 320)  # return b (single-width 320×630)
sv(ws_fcu, "K18", 250)  # fresh a
sv(ws_fcu, "L18", 250)  # fresh b

sv(ws_fcu, "H19", 630)
sv(ws_fcu, "I19", 320)
sv(ws_fcu, "K19", 250)
sv(ws_fcu, "L19", 250)

sv(ws_fcu, "H20", 500)  # guest return
sv(ws_fcu, "I20", 320)  # guest return b
sv(ws_fcu, "K20", 150)  # guest fresh
sv(ws_fcu, "L20", 150)  # guest fresh

# 四层 fresh ducts (rows 40-56)
sv(ws_fcu, "A40", "客房单间支管")
sv(ws_fcu, "B40", rooms["标准客房"]["sf"])

sv(ws_fcu, "A41", "8间客房支管-1")
sv(ws_fcu, "B41", rooms["标准客房"]["sf"] * 8)

sv(ws_fcu, "A42", "8间客房支管-2")
sv(ws_fcu, "B42", rooms["标准客房"]["sf"] * 8)

sv(ws_fcu, "A43", "四层客房主管")
sv(ws_fcu, "B43", guest_tf)

# ---------- 4g. 水系统 ----------
print("  4g. 水系统...")
ws_shui = wb["水系统"]

# 二层 water pipes (rows 23-31)
# Pipe segment data - update flow rates based on equipment
# 段1: 左中餐厅ZK
sv(ws_shui, "B24", "左中餐厅ZK")
sv(ws_shui, "D24", round(zk_l["wf"] * 1000, 0))
sv(ws_shui, "E24", 2.0)
sv(ws_shui, "G24", int(zk_l["wp"]))

# 段2: 右中餐厅ZK
sv(ws_shui, "B25", "右中餐厅ZK")
sv(ws_shui, "D25", round(zk_r["wf"] * 1000, 0))
sv(ws_shui, "E25", 2.0)
sv(ws_shui, "G25", int(zk_r["wp"]))

# 段3: 二层包厢KD
sv(ws_shui, "B26", "二层包厢KD")
sv(ws_shui, "D26", kd_2["wf"] * 1000 if isinstance(kd_2["wf"], (int, float)) else float(kd_2["wf"]) * 1000)
sv(ws_shui, "E26", 1.8)
sv(ws_shui, "G26", 50)

# 段4-5-6-7: FC groups
sv(ws_shui, "B27", "豪华包厢FC组")
sv(ws_shui, "D27", fc_lx["wf"] * 6)
sv(ws_shui, "E27", 1.5)
sv(ws_shui, "G27", 32)

sv(ws_shui, "B28", "普通包厢FC组")
sv(ws_shui, "D28", fc_pt["wf"] * 6)
sv(ws_shui, "E28", 1.5)
sv(ws_shui, "G28", 32)

# 四层 water pipes (rows 35-40)
sv(ws_shui, "B36", "四层客房FC组")
sv(ws_shui, "D36", fc_kf["wf"] * 12)
sv(ws_shui, "E36", 1.8)
sv(ws_shui, "G36", 25)

sv(ws_shui, "B37", "四层客房KD")
sv(ws_shui, "D37", kd_4["wf"] * 1000 if isinstance(kd_4["wf"], (int, float)) else float(kd_4["wf"]) * 1000)
sv(ws_shui, "E37", 1.6)
sv(ws_shui, "G37", 40)

# ---------- 4h. 设备汇总表 ----------
print("  4h. 设备汇总表...")
ws_hz = wb["设备汇总表"]

# 二层 (rows 4-7)
# Row 5: 左中餐厅ZK
sv(ws_hz, "B5", "二层")
sv(ws_hz, "C5", "ZK-01")
sv(ws_hz, "D5", "组合式空气处理机")
sv(ws_hz, "E5", zk_l["model"])
sv(ws_hz, "F5", zk_l["rc"])
sv(ws_hz, "G5", zk_l["na"])
sv(ws_hz, "H5", round(zk_l["wf"] * 1000, 0))
sv(ws_hz, "I5", zk_l["wd"])

# Row 6: 右中餐厅ZK
sv(ws_hz, "C6", "ZK-02")
sv(ws_hz, "D6", "组合式空气处理机")
sv(ws_hz, "E6", zk_r["model"])
sv(ws_hz, "F6", zk_r["rc"])
sv(ws_hz, "G6", zk_r["na"])
sv(ws_hz, "H6", round(zk_r["wf"] * 1000, 0))
sv(ws_hz, "I6", zk_r["wd"])

# Row 7: 豪华包厢FC
sv(ws_hz, "C7", "FC-01~06")
sv(ws_hz, "D7", "暗装风机盘管")
sv(ws_hz, "E7", f"FC-{fc_lx['model']}")
sv(ws_hz, "F7", fc_lx["rc"])
sv(ws_hz, "G7", fc_lx["af"])
sv(ws_hz, "H7", fc_lx["wf"])
sv(ws_hz, "I7", fc_lx["wd"])

# 四层 (rows 8-11)
sv(ws_hz, "B8", "四层")
sv(ws_hz, "B9", "四层")

# Row 9: 普通包厢FC
sv(ws_hz, "C9", "FC-07~12")
sv(ws_hz, "D9", "暗装风机盘管")
sv(ws_hz, "E9", f"FC-{fc_pt['model']}")
sv(ws_hz, "F9", fc_pt["rc"])
sv(ws_hz, "G9", fc_pt["af"])
sv(ws_hz, "H9", fc_pt["wf"])
sv(ws_hz, "I9", fc_pt["wd"])

# Row 10: 标准客房FC
sv(ws_hz, "C10", "FC-13~24")
sv(ws_hz, "D10", "暗装风机盘管")
sv(ws_hz, "E10", f"FC-{fc_kf['model']}")
sv(ws_hz, "F10", fc_kf["rc"])
sv(ws_hz, "G10", fc_kf["af"])
sv(ws_hz, "H10", fc_kf["wf"])
sv(ws_hz, "I10", fc_kf["wd"])

# 汇总 (rows 12-13)
sv(ws_hz, "B12", "汇总")
sv(ws_hz, "B13", "汇总")

# Row 13 column: KD units
# 二层KD
sv(ws_hz, "C13", "KD-2F")
sv(ws_hz, "D13", "吊挂式新风机")
sv(ws_hz, "E13", kd_2["model"])
sv(ws_hz, "F13", kd_2["rc"])
sv(ws_hz, "G13", kd_2["af"])
sv(ws_hz, "H13", kd_2["wf"] * 1000 if isinstance(kd_2["wf"], (int, float)) else float(kd_2["wf"]) * 1000)
sv(ws_hz, "I13", kd_2["wd"])
sv(ws_hz, "J13", float(kd_2["mp"]) if isinstance(kd_2["mp"], str) else kd_2["mp"])

# Row 14: 四层KD
sv(ws_hz, "C14", "KD-4F")
sv(ws_hz, "D14", "吊挂式新风机")
sv(ws_hz, "E14", kd_4["model"])
sv(ws_hz, "F14", kd_4["rc"])
sv(ws_hz, "G14", kd_4["af"])
sv(ws_hz, "H14", kd_4["wf"] * 1000 if isinstance(kd_4["wf"], (int, float)) else float(kd_4["wf"]) * 1000)
sv(ws_hz, "I14", kd_4["wd"])
sv(ws_hz, "J14", float(kd_4["mp"]) if isinstance(kd_4["mp"], str) else kd_4["mp"])

# ============================================================
# 5. SAVE
# ============================================================
print("\nStep 5: Saving...")
wb.save(OUTPUT)
print(f"  Saved to: {OUTPUT}")
print("Done!")
