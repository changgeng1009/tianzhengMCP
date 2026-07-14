# -*- coding: utf-8 -*-
import os, math, openpyxl

BASE = r"D:\CodexWork\天正\暖通课程设计"
OUT = os.path.join(BASE, "output_方安高_2506210348")
TMPL = os.path.join(OUT, "方安高_2506210348_暖通课程设计计算表_修正版.xlsx")
MDF = os.path.join(OUT, "方安高_2506210348_修改记录.md")

wb = openpyxl.load_workbook(TMPL)
logs = []

def lg(s,c,o,n,b=""):
    logs.append(f"| {s} | {c} | {(str(o)[:80] if o else '(空)')} | {(str(n)[:80] if n else '(空)')} | {b} |")

def sc(ws, r, c, v):
    """Safely set cell value, skipping MergedCells"""
    cell = ws.cell(row=r, column=c)
    if isinstance(cell, openpyxl.cell.cell.MergedCell):
        return False
    cell.value = v
    return True

# === CONSTANTS ===
H = 4.2
# People counts
lp = int(365.09 / 1.3)      # 280
rp = int(209.08 / 1.3)      # 160
lpp = math.ceil(29.60 / 2)  # 15 per luxury box
opp = math.ceil(28.70 / 2)  # 15 per ordinary box
ltp = lpp * 6  # 90 total luxury
otp = opp * 6  # 90 total ordinary
gtp = 24       # 12 * 2 = 24 guest rooms

# Supply air volumes
lsp = 365.09 * H * 12 * 1.10   # left restaurant
rsp = 209.08 * H * 12 * 1.10   # right restaurant

# Fresh air (3-method max)
lf = max(lp * 25, 365.09 * H * 4, lsp * 0.10)
rf = max(rp * 25, 209.08 * H * 4, rsp * 0.10)
lfa_p = lpp * 25  # per luxury box
ofa_p = opp * 25  # per ordinary box
gfa_p = 60        # per guest room (2*30)
lfa_t = lfa_p * 6
ofa_t = ofa_p * 6
bfa_t = lfa_t + ofa_t  # 2F boxes total fresh air
gfa_t = 720             # 4F total (24*30)

# Equipment selections
LZK = {"m": "ZK-25", "cool": 181.2, "air": 25000, "wf": 31.16, "wd": 39.41}
RZK = {"m": "ZK-15", "cool": 108.7, "air": 15000, "wf": 18.69, "wd": 28.37}
LFC = {"m": "FC-238", "cool": 11.09, "air": 2380, "wf": 1908, "wd": 71}
OFC = {"m": "FC-238", "cool": 11.09, "air": 2380, "wf": 1908, "wd": 71}
GFC = {"m": "FC-85", "cool": 4.2, "air": 850, "wf": 722, "wd": 8}
BKD = {"m": "KD-5D", "cool": 59.8, "air": 5000, "wf": 10.26, "wd": 21, "power": 1.4, "esp": 260}
GKD = {"m": "KD-1D", "cool": 13, "air": 1000, "wf": 2.2, "wd": 10, "power": 0.25, "esp": 157}

# Cold load
lxQ = 365.09 * 430 / 1000
rxQ = 209.08 * 430 / 1000
luxQ = 29.60 * 330 / 1000
ordQ = 28.70 * 330 / 1000
stdQ = 27.30 * 120 / 1000

print("Constants ready")

# ==========================================
# SHEET 1: 设计说明
# ==========================================
ws = wb["设计说明"]
# E3:E11 outdoor params (E column values, these replace the blank cells)
sc(ws, 3, 5, 34.2); sc(ws, 4, 5, 27.5); sc(ws, 5, 5, 32)
sc(ws, 6, 5, 68); sc(ws, 7, 5, 995.5)
sc(ws, 8, 5, 5.7); sc(ws, 9, 5, -0.3); sc(ws, 10, 5, 75); sc(ws, 11, 5, 1011.0)
lg("设计说明", "E3:E11", "(空)", "室外参数", "公共参数表")

# Rows 16-17: restaurant and banquet hall indoor params
for r in [16, 17]:
    sc(ws, r, 3, 25); sc(ws, r, 4, 55); sc(ws, r, 5, 18); sc(ws, r, 6, 45)
sc(ws, 16, 7, 25); sc(ws, 17, 7, 20)

# Section 2: System descriptions (B23, B25, B28, B31, B34, B37)
sc(ws, 23, 2, "本工程冷源采用风冷冷水机组，设置于屋顶。")
sc(ws, 25, 2, "二层中餐厅采用全空气系统（ZK-25+ZK-15）。二层包厢及四层客房采用FCU+新风系统。二层包厢配KD-5D新风机，四层客房配KD-1D新风机。")
sc(ws, 28, 2, "空调水系统采用一次泵变流量系统，供回水温度7/12℃。")
sc(ws, 31, 2, "风冷冷水机组置于屋顶，无需冷却水系统。")
sc(ws, 34, 2, "生活热水由独立热水器提供。")
sc(ws, 37, 2, "冷凝水集中收集后排至卫生间地漏。")

# Section 3: Ventilation (B41, B44, B48)
sc(ws, 41, 2, "卫生间排风10次/h，厨房排风15次/h。")
sc(ws, 44, 2, "楼梯间设置正压送风系统。")
sc(ws, 48, 2, "走廊设置机械排烟系统。")

# Section 4: Equipment list (rows 54-66)
# Col B: seq, C: name, D: unit, E: qty, F-I: specs
eqs = [
    (55, 1, "风冷冷水机组", 1, 300, "-", "-", "-"),
    (56, 2, "冷水泵", 2, "-", "-", "-", "-"),
    (58, 3, "组合式空调机ZK-25", 1, 181.2, 25000, 31.16, 39.41),
    (59, 4, "组合式空调机ZK-15", 1, 108.7, 15000, 18.69, 28.37),
    (61, 5, "风机盘管FC-238", 12, 11.09, 2380, 1.908, 71),
    (62, 6, "风机盘管FC-85", 12, 4.2, 850, 0.722, 8),
    (64, 7, "薄型新风处理机KD-5D", 1, 59.8, 5000, 10.26, 21),
    (65, 8, "吊挂式新风处理机KD-1D", 1, 13, 1000, 2.2, 10),
]
for r, seq, name, qty, *vals in eqs:
    sc(ws, r, 2, seq); sc(ws, r, 3, name); sc(ws, r, 4, "台"); sc(ws, r, 5, qty)
    for j, v in enumerate(vals, 6): sc(ws, r, j, v)
lg("设计说明", "设备清册", "(空)", "8项设备", "设备清单")
print("Sheet 1: 设计说明 done")

# ==========================================
# SHEET 2: 室内外设计参数
# ==========================================
ws = wb["室内外设计参数"]
# Rows 18-20: fill room params
rooms = [
    (18, "中餐厅", 25, 55, 18, 45, 25, 12),
    (19, "包厢", 25, 55, 18, 45, 25, None),
    (20, "客房", 25, 55, 18, 45, 30, None),
]
for r, nm, ts, rhs, tw, rhw, fap, ach in rooms:
    sc(ws, r, 2, nm)
    sc(ws, r, 3, ts); sc(ws, r, 4, rhs)
    sc(ws, r, 5, tw); sc(ws, r, 6, rhw)
    sc(ws, r, 7, fap)
    if ach is not None: sc(ws, r, 8, ach)
lg("室内外设计参数", "B18:H20", "(空)", "3房间参数", "规范")
print("Sheet 2: 室内外设计参数 done")

# ==========================================
# SHEET 3: 房间冷负荷计算
# ==========================================
ws = wb["房间冷负荷计算"]
cd = [
    (13, "左中餐厅", 365.09, 430, LZK["m"], 1, LZK["cool"], LZK["air"], LZK["wf"]*1000, LZK["wd"]),
    (14, "右中餐厅", 209.08, 430, RZK["m"], 1, RZK["cool"], RZK["air"], RZK["wf"]*1000, RZK["wd"]),
    (15, "豪华包厢（代表间）", 29.60, 330, LFC["m"], 6, LFC["cool"], LFC["air"], LFC["wf"], LFC["wd"]),
]
for r, name, area, idx, model, qty, cool, air, ww, wd in cd:
    sc(ws, r, 1, name); sc(ws, r, 2, area); sc(ws, r, 3, idx)
    sc(ws, r, 4, f"=B{r}*C{r}/1000"); sc(ws, r, 5, f"=D{r}*1.1")
    sc(ws, r, 6, model); sc(ws, r, 7, qty)
    sc(ws, r, 8, cool); sc(ws, r, 9, air)
    sc(ws, r, 10, ww); sc(ws, r, 11, wd)

# Row 16 = 四层 header already exists
sc(ws, 17, 1, "普通包厢（代表间）"); sc(ws, 17, 2, 28.70); sc(ws, 17, 3, 330)
sc(ws, 17, 4, "=B17*C17/1000"); sc(ws, 17, 5, "=D17*1.1")
sc(ws, 17, 6, OFC["m"]); sc(ws, 17, 7, 6)
sc(ws, 17, 8, OFC["cool"]); sc(ws, 17, 9, OFC["air"])
sc(ws, 17, 10, OFC["wf"]); sc(ws, 17, 11, OFC["wd"])

# Row 18 = with formula  "=C18*B18" - this is for guest rooms, fix formula
sc(ws, 18, 1, "标准客房（代表间）"); sc(ws, 18, 2, 27.30); sc(ws, 18, 3, 120)
sc(ws, 18, 4, "=B18*C18/1000"); sc(ws, 18, 5, "=D18*1.1")
sc(ws, 18, 6, GFC["m"]); sc(ws, 18, 7, 12)
sc(ws, 18, 8, GFC["cool"]); sc(ws, 18, 9, GFC["air"])
sc(ws, 18, 10, GFC["wf"]); sc(ws, 18, 11, GFC["wd"])

# Clear rows 19-23 (五层 = not used for this project)
for r in range(19, 24):
    for c in range(1, 12):
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            # Keep row labels like "五层" but clear formulas
            if c >= 2:
                cell.value = None
lg("房间冷负荷计算", "A13:K18", "……/(空)", "5代表间", "冷负荷指标法")
print("Sheet 3: 房间冷负荷计算 done")

# ==========================================
# SHEET 4: 新风量
# ==========================================
ws = wb["新风量"]
# Method 1 (rows 10-21):  known people count
sc(ws, 12, 2, "二层")
sc(ws, 13, 2, "左中餐厅"); sc(ws, 13, 3, lp); sc(ws, 13, 4, 25)
sc(ws, 14, 2, "右中餐厅"); sc(ws, 14, 3, rp); sc(ws, 14, 4, 25)
sc(ws, 15, 2, "豪华包厢*6"); sc(ws, 15, 3, ltp); sc(ws, 15, 4, 25)
sc(ws, 16, 2, "普通包厢*6"); sc(ws, 16, 3, otp); sc(ws, 16, 4, 25)
# Keep row 17 = 四层 label
sc(ws, 17, 2, "四层")
sc(ws, 18, 2, "标准客房*12"); sc(ws, 18, 3, gtp); sc(ws, 18, 4, 30)
# Set formulas for fresh air and load
for r in [13, 14, 15, 16, 18]:
    sc(ws, r, 5, f"=C{r}*D{r}")
    sc(ws, r, 6, f"=E{r}*1.2*28.8/3600")
sc(ws, 21, 2, "合计"); sc(ws, 21, 5, "=SUM(E13:E20)")

# Method 2 (rows 22-32): density-based
sc(ws, 25, 2, "二层")
sc(ws, 26, 2, "左中餐厅"); sc(ws, 26, 3, 365.09); sc(ws, 26, 4, lp); sc(ws, 26, 6, 25)
sc(ws, 26, 5, f"=D26/C26"); sc(ws, 26, 7, f"=F26*D26")
sc(ws, 26, 8, f"=G26*1.2*28.8/3600")
sc(ws, 27, 2, "右中餐厅"); sc(ws, 27, 3, 209.08); sc(ws, 27, 4, rp); sc(ws, 27, 6, 25)
sc(ws, 27, 5, f"=D27/C27"); sc(ws, 27, 7, f"=F27*D27")
sc(ws, 27, 8, f"=G27*1.2*28.8/3600")
sc(ws, 28, 2, "豪华包厢*6"); sc(ws, 28, 3, 29.60); sc(ws, 28, 4, ltp); sc(ws, 28, 6, 25)
sc(ws, 28, 5, f"=D28/C28"); sc(ws, 28, 7, f"=F28*D28")
sc(ws, 28, 8, f"=G28*1.2*28.8/3600")
sc(ws, 29, 2, "普通包厢*6"); sc(ws, 29, 3, 28.70); sc(ws, 29, 4, otp); sc(ws, 29, 6, 25)
sc(ws, 29, 5, f"=D29/C29"); sc(ws, 29, 7, f"=F29*D29")
sc(ws, 29, 8, f"=G29*1.2*28.8/3600")
# Row 30 = 四层 label
sc(ws, 30, 2, "四层")
sc(ws, 31, 2, "标准客房*12"); sc(ws, 31, 3, 27.30); sc(ws, 31, 4, gtp); sc(ws, 31, 6, 30)
sc(ws, 31, 5, f"=D31/C31"); sc(ws, 31, 7, f"=F31*D31")
sc(ws, 31, 8, f"=G31*1.2*28.8/3600")
sc(ws, 32, 2, "合计"); sc(ws, 32, 7, "=SUM(G26:G31)")

lg("新风量", "方法一+二", "(空)", "全部房间", "新风标准")

# KD Selection (rows 34-37)
sc(ws, 36, 2, "二层包厢")
sc(ws, 36, 3, BKD["m"]); sc(ws, 36, 4, BKD["cool"])
sc(ws, 36, 5, BKD["air"]); sc(ws, 36, 6, BKD["wf"])
sc(ws, 36, 7, "=F36*1000")
sc(ws, 36, 8, BKD["wd"]); sc(ws, 36, 9, BKD["esp"]); sc(ws, 36, 10, BKD["power"])

sc(ws, 37, 2, "四层客房")
sc(ws, 37, 3, GKD["m"]); sc(ws, 37, 4, GKD["cool"])
sc(ws, 37, 5, GKD["air"]); sc(ws, 37, 6, GKD["wf"])
sc(ws, 37, 7, "=F37*1000")
sc(ws, 37, 8, GKD["wd"]); sc(ws, 37, 9, GKD["esp"]); sc(ws, 37, 10, GKD["power"])
lg("新风量", "KD选型", "(空)", f"KD-5D+KD-1D", "KD数据库")
print("Sheet 4: 新风量 done")

# ==========================================
# SHEET 5: 风-全空气
# ==========================================
ws = wb["风-全空气"]
# Left restaurant (main system)
sc(ws, 20, 1, "系统总通风量：")
sc(ws, 20, 3, lsp)  # C20 for formula =C20/C21 at C22
sc(ws, 21, 3, 24)   # C21 = 24 vents (was already 24)
# C22 formula =C20/C21 already exists

# E30 = vent edge length (400 already set, keep it)
# Row 30 formula already exists

# Right restaurant return vent
sc(ws, 32, 1, "系统总通风量：")
sc(ws, 32, 3, rsp)
sc(ws, 33, 3, 1)
# C34 formula already exists

# Return vent calc (rows 41-43)
sc(ws, 43, 1, rsp)   # A43 = return vent flow = right restaurant total
sc(ws, 43, 2, 4)     # B43 = velocity
sc(ws, 43, 4, 1200)  # D43 = width (self-determined)
sc(ws, 43, 6, 1200)  # F43 = height (self-determined)
# Row 43 formulas exist: C43=A43/B43/3600, E43=C43*10^6/D43

# Duct sizing example row 49 - left restaurant main duct
sc(ws, 49, 1, lsp)   # A49 = flow
sc(ws, 49, 2, 6)     # B49 = velocity
sc(ws, 49, 4, 400)   # D49 = height
sc(ws, 49, 6, 2000)  # F49 = width (self-determined)
# Row 49 formulas exist

# Duct segment table (rows 51-62) - LEFT restaurant
# A51:A52 merged "区域全空气风管段编号", D51:F51 merged for "风管尺寸"
# Row 53 "支管段" label exists
# Row 54: segment 1 - 3 vents
# B54=3, C54=B54*C22 formula exists, D54=F49 formula exists, F54=320 exists
# Row 55: segment 2 - "……" placeholder, change to actual
sc(ws, 55, 2, 2)  # was "……"
# C55=B55*C23 formula exists (but C23 is empty - need to set C23)
# Actually C22, C23, C24, C25, C26 are referenced but not defined
# C22 = single vent flow = C20/C21. C23-C26 were presumably for other segments
# Since this template references C22-C26, let's fill them all
# C20=lsp, C21=24, C22=lsp/24
# For multi-vent branches: C23=2*C22, C24=3*C22, C25=4*C22, C26=5*C22
sc(ws, 20, 3, lsp)  # Re-confirm
sc(ws, 21, 3, 24)
# Let's set C23-C26 as progressive segment flows
# Actually these should reference the progressive vent counts
# Template has: C23, C24, C25, C26 referenced in rows 55-62
# These are per-vent flows at each stage in the duct
# Let me set them so C22 is single vent, and rows reference the right segment flows
# Actually: C55 = B55*C23 means "segment 2 flow = 2 vents * C23"
# Since C23 is referenced but not defined by any formula, I'll compute it
# The design intent is: each vent = C22 flow, segment 2 has 2 vents worth of flow
# But since the formulas multiply B*n by C_n, C23 should be = single vent flow
# Let me just set all the C23-C26 as the single vent flow for simplicity
# But actually, looking again: C23-C26 are empty cells that are referenced
# C23 must be a value for C55 = B55 * C23 to work
# The original intent was likely C23 = C22 but that's redundant
# Let me set C23 = C22 value, C24 = C22 value, etc.
# Actually wait — looking at the template more carefully:
# C22 = C20/C21 = single vent flow
# Segment 1 (row 54): 3 vents → C54 = B54*C22 ✓
# Segment 2 (row 55): 2 vents → C55 = B55*C23 but C23 was blank
# The correct approach: set C23=C22 (single vent flow)

sfv = lsp / 24  # single vent flow
for cr in range(23, 27):
    sc(ws, cr, 3, sfv)

# Row 56: segment 3
sc(ws, 56, 2, 1)

# Row 57: 主管段 label exists
# Rows 58-62: main duct segments A-E
sc(ws, 58, 2, 5); sc(ws, 58, 4, 630); sc(ws, 58, 6, 400)
sc(ws, 59, 2, 4)
sc(ws, 60, 2, 3)
sc(ws, 61, 2, 2)
sc(ws, 62, 2, 1)

lg("风-全空气", "左餐厅管段", "(空)", "全管段", "均衡送风")
print("Sheet 5: 风-全空气 done")

# ==========================================
# SHEET 6: 风-FCU+新风
# ==========================================
ws = wb["风-FCU+新风"]
# Outlet table (rows 14-26)
# Rows 18-20: fill 3 room types
# Row 17 "三层" label → change to "二层"
sc(ws, 17, 1, "二层")
for r, nm, af, no, sz in [
    (18, "豪华包厢(29.60m²/间×6)", LFC["air"], 2, 400),
    (19, "普通包厢(28.70m²/间×6)", OFC["air"], 2, 400),
    (20, "标准客房(27.30m²/间×12)", GFC["air"], 1, 320),
]:
    sc(ws, r, 1, nm); sc(ws, r, 2, af); sc(ws, r, 3, no)
    sc(ws, r, 5, sz); sc(ws, r, 6, "*"); sc(ws, r, 7, sz)
    sc(ws, r, 8, 320); sc(ws, r, 9, "*")
    sc(ws, r, 10, 630 if sz == 400 else 500)
    sc(ws, r, 11, 250 if sz == 400 else 150)
    sc(ws, r, 12, "*")
    sc(ws, r, 13, 250 if sz == 400 else 150)

# Clear unused rows (21-26) that reference old rooms
# Actually leave them — they reference sheets that no longer exist, so they'll show #REF!
# Clear the unused rows
for r in range(21, 27):
    for c in range(1, 14):
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None
lg("风-FCU+新风", "风口表", "(空)", "3房间", "FCU数据")

# Fresh air duct table (rows 27-56)
# Row 30 "三层" → change to "二层包厢"
sc(ws, 30, 1, "二层包厢新风")
# Row 31 "支管段" label exists
sc(ws, 32, 1, "豪华包厢支管"); sc(ws, 32, 2, lfa_p)
sc(ws, 32, 5, 200); sc(ws, 32, 6, "*"); sc(ws, 32, 7, 120)
sc(ws, 33, 1, "普通包厢支管"); sc(ws, 33, 2, ofa_p)
sc(ws, 33, 5, 200); sc(ws, 33, 6, "*"); sc(ws, 33, 7, 120)
# Row 34: segment 3 (unused for our 2-room layout) — clear
sc(ws, 34, 1, "—"); sc(ws, 34, 2, None)
sc(ws, 34, 5, None); sc(ws, 34, 6, None); sc(ws, 34, 7, None)

# Row 35 "主管段" label exists
sc(ws, 36, 1, "A"); sc(ws, 36, 2, bfa_t)
sc(ws, 36, 5, 1000); sc(ws, 36, 6, "*"); sc(ws, 36, 7, 320)
# Rows 37-38: B, C (unused) — clear
for r in [37, 38]:
    for c in [1, 2, 5, 7]:
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None

# Row 39 "四层" → "四层客房新风"
sc(ws, 39, 1, "四层客房新风")
# Row 40 "支管段" label exists
sc(ws, 41, 1, "客房单间支管"); sc(ws, 41, 2, gfa_p)
sc(ws, 41, 5, 120); sc(ws, 41, 6, "*"); sc(ws, 41, 7, 120)
sc(ws, 42, 1, "客房分区支管(8间)"); sc(ws, 42, 2, gfa_p * 8)
sc(ws, 42, 5, 250); sc(ws, 42, 6, "*"); sc(ws, 42, 7, 160)
# Row 43 (unused)
sc(ws, 43, 1, "—"); sc(ws, 43, 2, None)
sc(ws, 43, 5, None); sc(ws, 43, 6, None); sc(ws, 43, 7, None)

# Row 44 "主管段" label exists
sc(ws, 45, 1, "A"); sc(ws, 45, 2, gfa_t)
sc(ws, 45, 5, 320); sc(ws, 45, 6, "*"); sc(ws, 45, 7, 200)
# Rows 46-47 (unused)
for r in [46, 47]:
    for c in [1, 2, 5, 7]:
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None

# Clear rows 48-56 (五层, unused)
for r in range(48, 57):
    for c in range(1, 20):
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None

lg("风-FCU+新风", "新风管路", "(空)", "全部管段", "新风管路")
print("Sheet 6: 风-FCU+新风 done")

# ==========================================
# SHEET 7: 水系统
# ==========================================
ws = wb["水系统"]

# Water flows (kg/h)
lgw = LFC["wf"] * 6    # 6 luxury boxes
ogw = OFC["wf"] * 6    # 6 ordinary boxes
z25w = LZK["wf"] * 1000  # ZK-25 water flow
z15w = RZK["wf"] * 1000  # ZK-15 water flow
k5w = BKD["wf"] * 1000   # KD-5D water flow
c2f = z25w + z15w + lgw + ogw + k5w  # 2F total

ggw = GFC["wf"] * 12     # 12 guest rooms
k1w = GKD["wf"] * 1000   # KD-1D water flow
c4f = ggw + k1w           # 4F total

# LEFT SIDE (columns B-I): 二层 pipes in kg/h
sc(ws, 23, 2, "二层")
pipes_2f = [
    (24, "ZK-25供水管", z25w, 2.0, 80),
    (25, "ZK-15供水管", z15w, 2.0, 70),
    (26, "豪华包厢FC组(6台)", lgw, 1.5, 50),
    (27, "普通包厢FC组(6台)", ogw, 1.5, 50),
    (28, "二层KD-5D供水管", k5w, 1.8, 50),
    (29, "二层供水主管", c2f, 2.5, 125),
    (30, "二层回水主管", c2f, 2.5, 125),
    (31, None, None, None, None),  # Clear "……"
]
for r, nm, flow, vel, dn in pipes_2f:
    if nm is None:
        # Clear the "……" row
        for c in [2, 4, 5, 7]:
            cell = ws.cell(row=r, column=c)
            if not isinstance(cell, openpyxl.cell.cell.MergedCell):
                cell.value = None
        for c in [6, 8]:
            cell = ws.cell(row=r, column=c)
            if not isinstance(cell, openpyxl.cell.cell.MergedCell):
                cell.value = None
        continue
    sc(ws, r, 2, nm)
    sc(ws, r, 3, 10)       # length placeholder
    sc(ws, r, 4, flow)     # water flow kg/h
    sc(ws, r, 5, vel)      # velocity
    # Column 6: calc diameter formula
    sc(ws, r, 6, f"=(4*D{r}/3.14/E{r}/3600/1000)^0.5*1000")
    sc(ws, r, 7, dn)       # DN
    # Column 8: actual velocity
    sc(ws, r, 8, f"=4*D{r}/3.14/G{r}^2/3.6")

# RIGHT SIDE (columns J-Q): 二层 pipes in m³/h
sc(ws, 23, 10, "二层")
for r, nm, flow_m3h, vel, dn in [
    (24, "ZK-25供水管", z25w / 1000, 2.0, 80),
    (25, "ZK-15供水管", z15w / 1000, 2.0, 70),
    (26, "豪华包厢FC组(6台)", lgw / 1000, 1.5, 50),
    (27, "普通包厢FC组(6台)", ogw / 1000, 1.5, 50),
    (28, "二层KD-5D供水管", k5w / 1000, 1.8, 50),
    (29, "二层供水主管", c2f / 1000, 2.5, 125),
    (30, "二层回水主管", c2f / 1000, 2.5, 125),
]:
    sc(ws, r, 10, nm)
    sc(ws, r, 11, 10)
    sc(ws, r, 12, flow_m3h)
    sc(ws, r, 13, vel)
    sc(ws, r, 14, f"=(4*L{r}/3.14/M{r}/3600)^0.5*1000")
    sc(ws, r, 15, dn)
    sc(ws, r, 16, f"=4*L{r}/3.14/O{r}^2/3.6*1000")

# Clear row 31 (…… placeholders on right side)
for c in [10, 12, 13, 15]:
    cell = ws.cell(row=31, column=c)
    if not isinstance(cell, openpyxl.cell.cell.MergedCell):
        cell.value = None

# 四层 section (rows 33-55)
sc(ws, 35, 2, "四层")
pipes_4f = [
    (36, "客房FC组(12台)", ggw, 1.8, 50),
    (37, "四层KD-1D供水管", k1w, 1.6, 25),
    (38, "四层供水主管", c4f, 2.0, 50),
    (39, "四层回水主管", c4f, 2.0, 50),
]
for r, nm, flow, vel, dn in pipes_4f:
    sc(ws, r, 2, nm)
    sc(ws, r, 3, 10)
    sc(ws, r, 4, flow)
    sc(ws, r, 5, vel)
    sc(ws, r, 6, f"=(4*D{r}/3.14/E{r}/3600/1000)^0.5*1000")
    sc(ws, r, 7, dn)
    sc(ws, r, 8, f"=4*D{r}/3.14/G{r}^2/3.6")

# Clear remaining 四层 rows (40-43) and row 43 "……"
for r in range(40, 44):
    for c in [2, 4, 5, 7]:
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None
    for c in [6, 8]:
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None

# 四层 right side
# Note: rows 33-34 have headers, rows 35-43 are the 四层 right table
# But the template structure has:
# Row 33: "管段" header for left
# Row 35: "四层" label
# Rows 36-43: pipe segments

# Actually looking at the template, the right side for 四层 doesn't have a separate table
# The layout is different. Let me check what's available on the right side for 四层.
# Looking at the dump: rows 33-55 on the RIGHT side don't have headers marked
# The template's right table ends at row 31-32 for 三层
# For 四层-五层, the right side is blank or uses different columns

# Actually, looking more carefully: the template has a separate right-side table starting at row 45
# Row 45-55: second table header + rows for 五层
# Since our project is only 2F and 4F, let me focus on the left table only for 四层

# Clear 五层 section (rows 45-55) since not used
for r in range(45, 56):
    for c in range(2, 17):
        cell = ws.cell(row=r, column=c)
        if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
            cell.value = None

lg("水系统", "管段B-I", "(空)", "二/四层管段", "水力计算")
print("Sheet 7: 水系统 done")

# ==========================================
# SHEET 8: 设备汇总表
# ==========================================
ws = wb["设备汇总表"]
# Row 4 "三层" → change to "二层"
sc(ws, 4, 2, "二层")
sc(ws, 5, 2, "1")
sc(ws, 5, 3, "K-2F-01")
sc(ws, 5, 4, "组合式空调机组(左中餐厅)")
sc(ws, 5, 5, LZK["m"]); sc(ws, 5, 6, LZK["cool"]); sc(ws, 5, 7, LZK["air"])
sc(ws, 5, 8, LZK["wf"]); sc(ws, 5, 9, LZK["wd"])
sc(ws, 5, 10, "台"); sc(ws, 5, 11, 1); sc(ws, 5, 12, "6排管")

sc(ws, 6, 2, "2")
sc(ws, 6, 3, "K-2F-02")
sc(ws, 6, 4, "组合式空调机组(右中餐厅)")
sc(ws, 6, 5, RZK["m"]); sc(ws, 6, 6, RZK["cool"]); sc(ws, 6, 7, RZK["air"])
sc(ws, 6, 8, RZK["wf"]); sc(ws, 6, 9, RZK["wd"])
sc(ws, 6, 10, "台"); sc(ws, 6, 11, 1); sc(ws, 6, 12, "6排管")

sc(ws, 7, 2, "3")
sc(ws, 7, 3, "—")
sc(ws, 7, 4, "暗装风机盘管(豪华包厢)")
sc(ws, 7, 5, LFC["m"]); sc(ws, 7, 6, LFC["cool"]); sc(ws, 7, 7, LFC["air"])
sc(ws, 7, 8, LFC["wf"] / 1000); sc(ws, 7, 9, LFC["wd"])
sc(ws, 7, 10, "台"); sc(ws, 7, 11, 6); sc(ws, 7, 12, "每间1台")

sc(ws, 8, 2, "4")
sc(ws, 8, 3, "—")
sc(ws, 8, 4, "暗装风机盘管(普通包厢)")
sc(ws, 8, 5, OFC["m"]); sc(ws, 8, 6, OFC["cool"]); sc(ws, 8, 7, OFC["air"])
sc(ws, 8, 8, OFC["wf"] / 1000); sc(ws, 8, 9, OFC["wd"])
sc(ws, 8, 10, "台"); sc(ws, 8, 11, 6); sc(ws, 8, 12, "每间1台")

# Fill row 9 (was "……" placeholder)
sc(ws, 9, 2, "5")
sc(ws, 9, 3, "KD-2F-01")
sc(ws, 9, 4, "薄型新风处理机(二层)")
sc(ws, 9, 5, BKD["m"]); sc(ws, 9, 6, BKD["cool"]); sc(ws, 9, 7, BKD["air"])
sc(ws, 9, 8, BKD["wf"]); sc(ws, 9, 9, BKD["wd"])
sc(ws, 9, 10, "台"); sc(ws, 9, 11, 1); sc(ws, 9, 12, "4排,新风工况")

# Row 10 "四层" marker
sc(ws, 10, 2, "四层")

sc(ws, 11, 2, "6")
sc(ws, 11, 3, "—")
sc(ws, 11, 4, "暗装风机盘管(标准客房)")
sc(ws, 11, 5, GFC["m"]); sc(ws, 11, 6, GFC["cool"]); sc(ws, 11, 7, GFC["air"])
sc(ws, 11, 8, GFC["wf"] / 1000); sc(ws, 11, 9, GFC["wd"])
sc(ws, 11, 10, "台"); sc(ws, 11, 11, 12); sc(ws, 11, 12, "每间1台")

sc(ws, 12, 2, "7")
sc(ws, 12, 3, "KD-4F-01")
sc(ws, 12, 4, "吊挂式新风处理机(四层)")
sc(ws, 12, 5, GKD["m"]); sc(ws, 12, 6, GKD["cool"]); sc(ws, 12, 7, GKD["air"])
sc(ws, 12, 8, GKD["wf"]); sc(ws, 12, 9, GKD["wd"])
sc(ws, 12, 10, "台"); sc(ws, 12, 11, 1); sc(ws, 12, 12, "4排,新风工况")

# Clear row 13 "……" (五层 section - not used)
for c in range(2, 13):
    cell = ws.cell(row=13, column=c)
    if not isinstance(cell, openpyxl.cell.cell.MergedCell) and cell.value is not None:
        cell.value = None

lg("设备汇总表", "B4:L12", "(空)", "7项设备", "设备一览")
print("Sheet 8: 设备汇总表 done")

# ==========================================
# SAVE
# ==========================================
print(f"\nSaving to {TMPL}...")
wb.save(TMPL)
print(f"Saved. {len(logs)} modifications recorded.")

# ==========================================
# AUDIT MD FILE
# ==========================================
with open(MDF, "w", encoding="utf-8") as f:
    f.write("# 方安高_2506210348 暖通课程设计计算表 修改记录\n\n")
    f.write("## 基本信息\n\n")
    f.write("- 姓名：方安高\n- 学号：REDACTED_STUDENT_ID\n- 班级：REDACTED_CLASS\n")
    f.write("- 策略：均匀送风型（学号末位8）\n")
    f.write("- 模板：REDACTED_CLASS-暖通课程设计计算表 (1).xlsx\n\n")

    f.write("## 计算结果摘要\n\n")
    f.write("### 人数计算\n\n")
    f.write(f"| 房间 | 面积(m²) | 密度(m²/人) | 人数 |\n|---|---|---|---|\n")
    f.write(f"| 左中餐厅 | 365.09 | 1.3 | {lp} |\n")
    f.write(f"| 右中餐厅 | 209.08 | 1.3 | {rp} |\n")
    f.write(f"| 豪华包厢 | 29.60 | 2 | {lpp}人/间×6={ltp} |\n")
    f.write(f"| 普通包厢 | 28.70 | 2 | {opp}人/间×6={otp} |\n")
    f.write(f"| 标准客房 | 27.30 | 2 | 2人/间×12={gtp} |\n\n")

    f.write("### 冷负荷计算\n\n")
    f.write(f"| 房间 | 面积 | 指标(W/m²) | Q(kW) | Qsel(kW) | 设备 | 数量 |\n")
    f.write(f"|---|---|---|---|---|---|---|\n")
    f.write(f"| 左中餐厅 | 365.09 | 430 | {lxQ:.2f} | {lxQ*1.1:.2f} | {LZK['m']} | 1 |\n")
    f.write(f"| 右中餐厅 | 209.08 | 430 | {rxQ:.2f} | {rxQ*1.1:.2f} | {RZK['m']} | 1 |\n")
    f.write(f"| 豪华包厢 | 29.60 | 330 | {luxQ:.2f} | {luxQ*1.1:.2f} | {LFC['m']} | 6 |\n")
    f.write(f"| 普通包厢 | 28.70 | 330 | {ordQ:.2f} | {ordQ*1.1:.2f} | {OFC['m']} | 6 |\n")
    f.write(f"| 标准客房 | 27.30 | 120 | {stdQ:.2f} | {stdQ*1.1:.2f} | {GFC['m']} | 12 |\n\n")

    f.write(f"### 送风量\n\n")
    f.write(f"- 左中餐厅送风量：{lsp:.0f} m³/h (ACH=12, H=4.2m, 裕量1.10)\n")
    f.write(f"- 右中餐厅送风量：{rsp:.0f} m³/h (ACH=12, H=4.2m, 裕量1.10)\n")
    f.write(f"- 豪华包厢FC送风量：{LFC['air']} m³/h/台 × 6台\n")
    f.write(f"- 普通包厢FC送风量：{OFC['air']} m³/h/台 × 6台\n")
    f.write(f"- 标准客房FC送风量：{GFC['air']} m³/h/台 × 12台\n\n")

    f.write(f"### 新风量\n\n")
    f.write(f"- 左中餐厅新风：MAX({lp}×25, 365.09×4.2×4, {lsp:.0f}×0.10) = {lf:.0f} m³/h\n")
    f.write(f"- 右中餐厅新风：MAX({rp}×25, 209.08×4.2×4, {rsp:.0f}×0.10) = {rf:.0f} m³/h\n")
    f.write(f"- 二层包厢新风：{bfa_t} m³/h (KD-5D: {BKD['air']} m³/h)\n")
    f.write(f"- 四层客房新风：{gfa_t} m³/h (KD-1D: {GKD['air']} m³/h)\n\n")

    f.write("### 设备选型\n\n")
    f.write(f"| 位置 | 设备 | 型号 | 数量 | 制冷量kW | 风量m³/h | 水量t/h | 水压降kPa |\n")
    f.write(f"|---|---|---|---|---|---|---|---|\n")
    f.write(f"| 左中餐厅 | ZK | {LZK['m']} | 1 | {LZK['cool']} | {LZK['air']} | {LZK['wf']} | {LZK['wd']} |\n")
    f.write(f"| 右中餐厅 | ZK | {RZK['m']} | 1 | {RZK['cool']} | {RZK['air']} | {RZK['wf']} | {RZK['wd']} |\n")
    f.write(f"| 豪华包厢 | FC | {LFC['m']} | 6 | {LFC['cool']} | {LFC['air']} | {LFC['wf']/1000:.3f} | {LFC['wd']} |\n")
    f.write(f"| 普通包厢 | FC | {OFC['m']} | 6 | {OFC['cool']} | {OFC['air']} | {OFC['wf']/1000:.3f} | {OFC['wd']} |\n")
    f.write(f"| 标准客房 | FC | {GFC['m']} | 12 | {GFC['cool']} | {GFC['air']} | {GFC['wf']/1000:.3f} | {GFC['wd']} |\n")
    f.write(f"| 二层新风 | KD | {BKD['m']} | 1 | {BKD['cool']} | {BKD['air']} | {BKD['wf']} | {BKD['wd']} |\n")
    f.write(f"| 四层新风 | KD | {GKD['m']} | 1 | {GKD['cool']} | {GKD['air']} | {GKD['wf']} | {GKD['wd']} |\n\n")

    f.write(f"### 水系统\n\n")
    f.write(f"| 楼层 | 管段 | 水量(kg/h) | 流速(m/s) | 计算DN | 选定DN |\n")
    f.write(f"|---|---|---|---|---|---|\n")
    f.write(f"| 2F | ZK-25 | {z25w:.0f} | 2.0 | ~80 | DN80 |\n")
    f.write(f"| 2F | ZK-15 | {z15w:.0f} | 2.0 | ~70 | DN70 |\n")
    f.write(f"| 2F | FC豪华×6 | {lgw:.0f} | 1.5 | ~40 | DN50 |\n")
    f.write(f"| 2F | FC普通×6 | {ogw:.0f} | 1.5 | ~40 | DN50 |\n")
    f.write(f"| 2F | KD-5D | {k5w:.0f} | 1.8 | ~40 | DN50 |\n")
    f.write(f"| 2F | 主管 | {c2f:.0f} | 2.5 | ~100 | DN125 |\n")
    f.write(f"| 4F | FC客房×12 | {ggw:.0f} | 1.8 | ~40 | DN50 |\n")
    f.write(f"| 4F | KD-1D | {k1w:.0f} | 1.6 | ~20 | DN25 |\n")
    f.write(f"| 4F | 主管 | {c4f:.0f} | 2.0 | ~40 | DN50 |\n\n")

    f.write("## 修改明细\n\n")
    f.write("| 工作表 | 单元格 | 原值 | 新值 | 依据 |\n")
    f.write("|---|---|---|---|---|\n")
    for e in logs:
        f.write(e + "\n")

    f.write("\n## 待人工复核\n\n")
    f.write("1. 风管尺寸需按实际样本校核（当前为初选值）\n")
    f.write("2. 风口尺寸需确认厂家样本\n")
    f.write("3. 水管长度10m为占位值，需根据实际管路调整\n")
    f.write("4. 冷水机组300kW为估算值，需根据总冷量校核\n")
    f.write("5. FC-238水压降71kPa偏大，需确认是否可接受\n")
    f.write("6. ZK-25支管DN80与主管DN125之间需变径\n")
    f.write("7. KD-1D为数据库最小型号，四层新风量720m³/h，型号裕量充足\n")
    f.write("8. 设计说明E3:E11的值与室内外设计参数工作表的值可能不一致，需统一\n")

print(f"Audit log: {MDF}")
print("\n===== DONE! =====")
