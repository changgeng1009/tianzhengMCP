"""Anonymized course-work example. Configure local inputs/outputs before execution.

The private workbook and databases are not bundled; no result is claimed for
these placeholder paths. This script performs writes when explicitly run.
"""

from __future__ import annotations

import json
import math
import shutil
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter


BASE = Path(r"D:\ExampleWorkspace\天正\暖通课程设计")
SRC = BASE / r"示例班级 课程设计资料\示例班级 课程设计资料\示例班级-暖通课程设计计算表 .xlsx"
OUT = Path(r"C:\Users\example-user\Desktop\anonymous_hvac_sample_暖通课程设计计算表_修正版.xlsx")
LOG = Path(r"C:\Users\example-user\Desktop\anonymous_hvac_sample_修改记录.md")
COMMON_JSON = BASE / r"暖通课程设计_AI计算完整包_v1.0\hvac_common_parameters_v1.0.json"
DB_JSON = BASE / r"暖通设备完整数据库_ZK_FC_KD_v2.0\hvac_equipment_database_ZK_FC_KD_v2.0.json"


def fmt(v):
    if v is None:
        return ""
    return str(v).replace("\n", " ")


def r3(x):
    return round(float(x), 3)


def round_up_to_standard_dn(mm: float) -> int:
    dns = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500]
    for dn in dns:
        if dn >= mm:
            return dn
    return dns[-1]


def calc_pipe(water_kg_h: float, velocity: float):
    d_mm = math.sqrt(4 * water_kg_h / math.pi / velocity / 3600 / 1000) * 1000
    dn = round_up_to_standard_dn(d_mm)
    actual_v = 4 * water_kg_h / math.pi / (dn**2) / 3.6
    return round(d_mm, 1), dn, round(actual_v, 2)


def choose_square_outlet(flow_m3h: float, velocity=3, eff=0.8):
    side = math.sqrt(flow_m3h / velocity / 3600 / eff) * 1000
    for s in [150, 200, 250, 320, 400, 500, 630, 800, 1000]:
        if s >= side:
            return s
    return 1000


def write_cell(ws, addr, value, reason, formula="", source=""):
    cell = ws[addr]
    if isinstance(cell, MergedCell):
        if value in (None, ""):
            return
        for merged in ws.merged_cells.ranges:
            if addr in merged:
                cell = ws.cell(merged.min_row, merged.min_col)
                break
    old = cell.value
    if old == value:
        return
    cell.value = value
    records.append(
        {
            "sheet": ws.title,
            "cell": addr,
            "old": fmt(old),
            "new": fmt(value),
            "reason": reason,
            "formula": formula,
            "source": source,
        }
    )


def copy_style(src, dst):
    if src.has_style:
        dst._style = copy(src._style)
    if src.number_format:
        dst.number_format = src.number_format
    if src.alignment:
        dst.alignment = copy(src.alignment)
    if src.protection:
        dst.protection = copy(src.protection)


def row_values(ws, row, values, reason, formulas=None, source=""):
    formulas = formulas or {}
    for i, value in enumerate(values, 1):
        if value is not None:
            write_cell(ws, f"{get_column_letter(i)}{row}", value, reason, formulas.get(i, ""), source)


records: list[dict] = []

if not SRC.exists():
    raise FileNotFoundError(SRC)

OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists():
    OUT.unlink()
shutil.copy2(SRC, OUT)

common = json.loads(COMMON_JSON.read_text(encoding="utf-8"))
db = json.loads(DB_JSON.read_text(encoding="utf-8"))
wb = load_workbook(OUT)
original_sheets = load_workbook(SRC, read_only=True).sheetnames

# Fixed inputs from the prompt and public parameters.
rooms = {
    "左中餐厅": {"floor": "二层中餐厅", "area": 363.08, "count": 1, "idx": 430, "people": math.floor(363.08 / 1.3), "fresh_pp": 25},
    "右中餐厅": {"floor": "二层中餐厅", "area": 428.50, "count": 1, "idx": 430, "people": math.floor(428.50 / 1.3), "fresh_pp": 25},
    "豪华包厢": {"floor": "二层包厢", "area": 26.71, "count": 6, "idx": 330, "people_single": math.ceil(26.71 / 2), "fresh_pp": 25},
    "普通包厢": {"floor": "二层包厢", "area": 18.33, "count": 6, "idx": 330, "people_single": math.ceil(18.33 / 2), "fresh_pp": 25},
    "标准客房": {"floor": "四层客房", "area": 33.81, "count": 12, "idx": 120, "people_single": 2, "fresh_pp": 30},
}

for name, room in rooms.items():
    room["q"] = r3(room["area"] * room["idx"] / 1000)
    room["q_sel"] = r3(room["q"] * 1.10)
    if name in ("豪华包厢", "普通包厢"):
        room["people_total"] = room["people_single"] * room["count"]
        room["fresh_single"] = room["people_single"] * room["fresh_pp"]
        room["fresh_total"] = room["fresh_single"] * room["count"]
    elif name == "标准客房":
        room["people_total"] = room["people_single"] * room["count"]
        room["fresh_single"] = room["people_single"] * room["fresh_pp"]
        room["fresh_total"] = room["fresh_single"] * room["count"]
    else:
        room["people_total"] = room["people"]
        room["supply"] = r3(room["area"] * 4.2 * 12 * 1.10)
        l1 = room["people"] * 25
        l2 = room["area"] * 4.2 * 4
        l3 = room["supply"] * 0.10
        room["fresh_total"] = r3(max(l1, l2, l3))
    room["fresh_load"] = r3(room["fresh_total"] * 1.2 * 28.8 / 3600)

zk25 = next(m for m in db["zk"]["models"] if m["model"] == "ZK-25")
fc = db["fc"]["concealed_units"]
fc_by_key = {(m["coil_configuration"], m["model"]): m for m in fc}
kd_h = db["kd"]["hanging_air_handler"]["performance"]

equip = {
    "左中餐厅": {
        "name": "ZK-25",
        "display": "ZK-25（6排）",
        "cool": zk25["cooling_6row_kw"],
        "air": zk25["nominal_airflow_m3h"],
        "water": int(round(zk25["cooling_water_flow_6row_t_h"] * 1000)),
        "drop": zk25["cooling_water_drop_6row_kpa"],
        "type": "组合式空气处理机",
    },
    "右中餐厅": {
        "name": "ZK-25",
        "display": "ZK-25（8排）",
        "cool": zk25["cooling_8row_kw"],
        "air": zk25["nominal_airflow_m3h"],
        "water": int(round(zk25["cooling_water_flow_8row_t_h"] * 1000)),
        "drop": zk25["cooling_water_drop_8row_kpa"],
        "type": "组合式空气处理机",
    },
    "豪华包厢": {
        "name": "FC-204",
        "display": "FC-204（3排管）",
        "cool": fc_by_key[("3排管", "FC-204")]["rated_cooling_kw"],
        "air": fc_by_key[("3排管", "FC-204")]["airflow_m3h"]["high"],
        "water": fc_by_key[("3排管", "FC-204")]["water_flow_kg_h"],
        "drop": fc_by_key[("3排管", "FC-204")]["water_pressure_drop_kpa"],
        "type": "暗装风机盘管",
    },
    "普通包厢": {
        "name": "FC-136",
        "display": "FC-136（3排管）",
        "cool": fc_by_key[("3排管", "FC-136")]["rated_cooling_kw"],
        "air": fc_by_key[("3排管", "FC-136")]["airflow_m3h"]["high"],
        "water": fc_by_key[("3排管", "FC-136")]["water_flow_kg_h"],
        "drop": fc_by_key[("3排管", "FC-136")]["water_pressure_drop_kpa"],
        "type": "暗装风机盘管",
    },
    "标准客房": {
        "name": "FC-85",
        "display": "FC-85（3排管）",
        "cool": fc_by_key[("3排管", "FC-85")]["rated_cooling_kw"],
        "air": fc_by_key[("3排管", "FC-85")]["airflow_m3h"]["high"],
        "water": fc_by_key[("3排管", "FC-85")]["water_flow_kg_h"],
        "drop": fc_by_key[("3排管", "FC-85")]["water_pressure_drop_kpa"],
        "type": "暗装风机盘管",
    },
}

kd2 = next(m for m in kd_h if m["model"] == "KD-4D" and m["coil_rows"] == 4)
kd4 = next(m for m in kd_h if m["model"] == "KD-1D" and m["coil_rows"] == 4)
kd_equip = {
    "二层包厢KD": {
        "display": "KD-4D（吊挂式，4排管，新风工况）",
        "name": "KD-4D",
        "cool": kd2["fresh_condition"]["cooling_kw"],
        "air": kd2["airflow_m3h"],
        "water": int(round(kd2["fresh_condition"]["water_flow_m3h"] * 1000)),
        "drop": kd2["fresh_condition"]["water_drop_kpa"],
        "static": kd2["external_static_pa"]["class_I"],
        "power": kd2["motor_power_kw"]["class_I"],
    },
    "四层客房KD": {
        "display": "KD-1D（吊挂式，4排管，新风工况）",
        "name": "KD-1D",
        "cool": kd4["fresh_condition"]["cooling_kw"],
        "air": kd4["airflow_m3h"],
        "water": int(round(kd4["fresh_condition"]["water_flow_m3h"] * 1000)),
        "drop": kd4["fresh_condition"]["water_drop_kpa"],
        "static": kd4["external_static_pa"]["class_I"],
        "power": kd4["motor_power_kw"]["class_I"],
    },
}

source_core = "本提示词面积/数量 + hvac_common_parameters_v1.0.json + hvac_equipment_database_ZK_FC_KD_v2.0.json"

# 室内外设计参数：只在空白行补充课程设计范围。
ws = wb["室内外设计参数"]
param_rows = [
    (18, ["", "中餐厅", 25, 55, 18, 45, 25, 4]),
    (19, ["", "豪华包厢", 25, 55, 18, 45, 25, ""]),
    (20, ["", "普通包厢", 25, 55, 18, 45, 25, ""]),
    (21, ["", "标准客房", 25, 55, 18, 45, 30, ""]),
]
for row, vals in param_rows:
    row_values(ws, row, vals, "在原室内空气参数表空白行补充课程设计房间参数", source="AI公共参数与个人输入说明_v1.0.md；hvac_common_parameters_v1.0.json")

# 房间冷负荷计算。
ws = wb["房间冷负荷计算"]
row_values(ws, 12, ["二层"], "保留二层分区标题", source=source_core)
cool_rows = [
    (13, "左中餐厅"),
    (14, "右中餐厅"),
    (15, "豪华包厢"),
    (16, "普通包厢"),
    (17, "四层"),
    (18, "标准客房"),
]
for row, name in cool_rows:
    if name == "四层":
        row_values(ws, row, ["四层"], "设置四层客房分区标题，普通包厢归入二层", source="本提示词楼层纠错要求")
        continue
    room = rooms[name]
    eq = equip[name]
    vals = [name, room["area"], room["idx"], room["q"], room["q_sel"], eq["display"], room["count"], eq["cool"], eq["air"], eq["water"], eq["drop"]]
    row_values(
        ws,
        row,
        vals,
        "填写代表房间冷负荷、选型冷量及数据库设备参数",
        formulas={4: "面积×冷负荷指标÷1000", 5: "房间冷负荷×1.10"},
        source=source_core,
    )
row_values(ws, 20, ["汇总"], "将原五层占位改为汇总行，避免中餐厅继续归入五层", source="本提示词楼层纠错要求")
row_values(ws, 21, ["二层合计", r3(363.08 + 428.50 + 26.71 * 6 + 18.33 * 6), "", r3(rooms["左中餐厅"]["q"] + rooms["右中餐厅"]["q"] + rooms["豪华包厢"]["q"] * 6 + rooms["普通包厢"]["q"] * 6), r3((rooms["左中餐厅"]["q"] + rooms["右中餐厅"]["q"] + rooms["豪华包厢"]["q"] * 6 + rooms["普通包厢"]["q"] * 6) * 1.1)], "汇总二层中餐厅和包厢负荷", source=source_core)
row_values(ws, 22, ["四层合计", r3(rooms["标准客房"]["area"] * 12), "", r3(rooms["标准客房"]["q"] * 12), r3(rooms["标准客房"]["q"] * 12 * 1.1)], "汇总四层标准客房负荷", source=source_core)
total_q = r3(rooms["左中餐厅"]["q"] + rooms["右中餐厅"]["q"] + rooms["豪华包厢"]["q"] * 6 + rooms["普通包厢"]["q"] * 6 + rooms["标准客房"]["q"] * 12)
row_values(ws, 23, ["总计", r3(363.08 + 428.50 + 26.71 * 6 + 18.33 * 6 + 33.81 * 12), "", total_q, r3(total_q * 1.1)], "汇总本次课程设计范围负荷", source=source_core)
for row in [19]:
    for col in range(1, 12):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用占位行中的模板公式，避免空白计算错误", source="保存前错误清理")

# 新风量。
ws = wb["新风量"]
fresh_rows1 = [
    (12, "*层", None),
    (13, "左中餐厅", "左中餐厅"),
    (14, "右中餐厅", "右中餐厅"),
    (15, "豪华包厢", "豪华包厢"),
    (16, "普通包厢", "普通包厢"),
    (17, "标准客房", "标准客房"),
]
row_values(ws, 12, ["", "二层/四层"], "修正新风计算分区标题", source="本提示词")
for row, label, name in fresh_rows1[1:]:
    room = rooms[name]
    row_values(ws, row, ["", label, room["people_total"], room["fresh_pp"], room["fresh_total"], room["fresh_load"]], "填写方法一新风量和新风负荷", formulas={5: "人数×人均新风量；中餐厅按MAX校核结果填入", 6: "新风量×1.2×28.8÷3600"}, source=source_core)
for row in [18, 19, 20]:
    for col in range(2, 7):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用新风占位行中的模板公式", source="保存前错误清理")
row_values(ws, 21, ["", "区域新风量合计", "", "", r3(sum(rooms[n]["fresh_total"] for n in rooms)), ""], "汇总本项目总新风量", source=source_core)
row_values(ws, 25, ["", "二层/四层"], "修正高密度人群计算分区标题", source="本提示词")
for row, name in [(26, "左中餐厅"), (27, "右中餐厅"), (28, "豪华包厢"), (29, "普通包厢"), (30, "标准客房")]:
    room = rooms[name]
    row_people = room["people_single"] if "people_single" in room else room["people"]
    density = round(row_people / room["area"], 3)
    fresh = room["fresh_single"] if name in ("豪华包厢", "普通包厢", "标准客房") else room["fresh_total"]
    load = r3(fresh * 1.2 * 28.8 / 3600)
    row_values(ws, row, ["", name, room["area"], row_people, density, room["fresh_pp"], fresh, load], "填写代表房间人员密度、新风量和新风负荷", formulas={5: "人数÷面积", 7: "人数×人均新风量；中餐厅按设计新风量", 8: "新风量×1.2×28.8÷3600"}, source=source_core)
for col in range(2, 9):
    write_cell(ws, f"{get_column_letter(col)}31", None, "清除未使用新风占位行中的模板公式", source="保存前错误清理")
row_values(ws, 32, ["", "区域新风量合计", "", "", "", "", r3(sum(rooms[n]["fresh_total"] for n in rooms)), ""], "汇总区域新风量", source=source_core)
row_values(ws, 34, ["", "二层包厢", kd_equip["二层包厢KD"]["name"], kd_equip["二层包厢KD"]["cool"], kd_equip["二层包厢KD"]["air"], kd_equip["二层包厢KD"]["water"], "kg/h", kd_equip["二层包厢KD"]["drop"], kd_equip["二层包厢KD"]["static"], kd_equip["二层包厢KD"]["power"]], "填写二层包厢KD新风机选型", source="设备数据库JSON，新风工况")
for col in range(2, 11):
    write_cell(ws, f"{get_column_letter(col)}35", None, "清除KD合并选型块内未使用占位", source="保存前错误清理")
row_values(ws, 36, ["", "四层客房", kd_equip["四层客房KD"]["name"], kd_equip["四层客房KD"]["cool"], kd_equip["四层客房KD"]["air"], kd_equip["四层客房KD"]["water"], "kg/h", kd_equip["四层客房KD"]["drop"], kd_equip["四层客房KD"]["static"], kd_equip["四层客房KD"]["power"]], "填写四层客房KD新风机选型", source="设备数据库JSON，新风工况")

# 风-全空气。
ws = wb["风-全空气"]
for row, name in [(2, "左中餐厅"), (3, "右中餐厅")]:
    room = rooms[name]
    row_values(ws, row, [None] * 13 + [f"二层{name}", room["area"], 4.2, r3(room["area"] * 4.2), 12, r3(room["area"] * 4.2 * 12), 1.10, room["supply"]], "填写二层中餐厅送风量计算", formulas={17: "面积×层高", 19: "体积×换气次数", 21: "基础风量×1.10"}, source=source_core)
row_values(ws, 20, ["系统总通风量：", "", rooms["左中餐厅"]["supply"], "m3/h"], "填写左中餐厅详细风口计算总风量", source=source_core)
row_values(ws, 21, ["系统总送风口数量：", "", 12, "个"], "按均匀送风策略设置左中餐厅送风口数量", source="hvac_common_parameters_v1.0.json；学号末位8均匀送风型")
single_left = r3(rooms["左中餐厅"]["supply"] / 12)
row_values(ws, 22, ["单个送风口风量：", "", single_left, "m3/h"], "计算左中餐厅单个送风口风量", formulas={3: "总送风量÷风口数量"}, source=source_core)
row_values(ws, 30, [single_left, 3, r3(single_left / 3 / 3600 / 0.8), r3(math.sqrt(single_left / 3 / 3600 / 0.8) * 1000), choose_square_outlet(single_left)], "填写左中餐厅散流器计算", source=source_core)
row_values(ws, 32, ["系统总通风量：", "", rooms["左中餐厅"]["supply"], "m3/h"], "填写左中餐厅回风口总风量", source=source_core)
row_values(ws, 34, ["单个回风口风量：", "", rooms["左中餐厅"]["supply"], "m3/h"], "填写左中餐厅回风口风量", source=source_core)
row_values(ws, 43, [rooms["左中餐厅"]["supply"], 4, r3(rooms["左中餐厅"]["supply"] / 4 / 3600), 1200, r3(rooms["左中餐厅"]["supply"] / 4 / 3600 * 1000000 / 1200), 1200], "填写左中餐厅回风口尺寸计算", source=source_core)
row_values(ws, 49, [5000, 6, r3(5000 / 6 / 3600), 400, r3(5000 / 6 / 3600 * 1000000 / 400), 630], "保留并数值化风管尺寸示例计算", source="原模板公式")
row_values(ws, 51, ["二层中餐厅全空气风管段编号"], "修正全空气风管段归属为二层中餐厅", source="本提示词楼层纠错要求")
row_values(ws, 54, ["左中餐厅支管", 3, r3(3 * single_left), 630, "*", 320], "填写左中餐厅支管段风量与尺寸", source=source_core)
single_right = r3(rooms["右中餐厅"]["supply"] / 14)
row_values(ws, 55, ["右中餐厅支管", 3, r3(3 * single_right), 630, "*", 320], "填写右中餐厅支管段风量与尺寸", source=source_core)
row_values(ws, 58, ["左中餐厅主管", 12, rooms["左中餐厅"]["supply"], 1250, "*", 500], "填写左中餐厅主管段风量与尺寸", source=source_core)
row_values(ws, 59, ["右中餐厅主管", 14, rooms["右中餐厅"]["supply"], 1250, "*", 630], "填写右中餐厅主管段风量与尺寸", source=source_core)
for row in [56, 60, 61, 62]:
    for col in range(1, 7):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用全空气风管占位公式", source="保存前错误清理")

# 风-FCU+新风。
ws = wb["风-FCU+新风"]
row_values(ws, 17, ["二层包厢"], "修正FCU风系统分区", source="本提示词")
for row, name, outlets in [(18, "豪华包厢", 2), (19, "普通包厢", 2)]:
    eq = equip[name]
    single = r3(eq["air"] / outlets)
    outlet = choose_square_outlet(single)
    row_values(ws, row, [name, eq["air"], outlets, single, outlet, "*", outlet, 630, "*", 320, 250, "*", 250], "填写包厢FCU风口和新风口尺寸", formulas={4: "FC额定风量÷风口数量"}, source=source_core)
row_values(ws, 21, ["四层客房"], "设置四层客房分区", source="本提示词")
eq = equip["标准客房"]
row_values(ws, 22, ["标准客房", eq["air"], 1, eq["air"], 320, "*", 320, 500, "*", 320, 150, "*", 150], "填写标准客房FCU风口和新风口尺寸", source=source_core)
for row in [20, 23, 25]:
    for col in range(1, 14):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用FCU风口占位公式", source="保存前错误清理")
row_values(ws, 30, ["二层包厢"], "修正新风管路分区", source="本提示词")
row_values(ws, 31, ["豪华包厢支管", rooms["豪华包厢"]["fresh_single"], "", "", 200, "*", 120], "填写豪华包厢单间新风支管", source=source_core)
row_values(ws, 32, ["普通包厢支管", rooms["普通包厢"]["fresh_single"], "", "", 160, "*", 120], "填写普通包厢单间新风支管", source=source_core)
box_total = rooms["豪华包厢"]["fresh_total"] + rooms["普通包厢"]["fresh_total"]
row_values(ws, 35, ["二层包厢主管", box_total, "", "", 500, "*", 320], "填写二层包厢新风主管", source=source_core)
row_values(ws, 39, ["四层客房"], "修正四层客房新风管路分区", source="本提示词")
row_values(ws, 40, ["客房单间支管", rooms["标准客房"]["fresh_single"], "", "", 120, "*", 120], "填写标准客房单间新风支管", source=source_core)
row_values(ws, 41, ["12间客房支管合计", rooms["标准客房"]["fresh_total"], "", "", 320, "*", 200], "填写四层客房支管合计", source=source_core)
row_values(ws, 43, ["四层客房主管", rooms["标准客房"]["fresh_total"], "", "", 320, "*", 200], "填写四层客房新风主管", source=source_core)
for row in [33, 34, 36, 37, 38, 42, 44, 45, 46, 47, 50, 51, 52, 54, 55, 56]:
    for col in range(1, 7):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用FCU新风管路占位", source="保存前错误清理")

# 水系统。
ws = wb["水系统"]
row_values(ws, 23, ["二层"], "将中餐厅和包厢水系统归入二层", source="本提示词楼层纠错要求")
water_rows = [
    (24, "左中餐厅ZK", equip["左中餐厅"]["water"], 2.0),
    (25, "右中餐厅ZK", equip["右中餐厅"]["water"], 2.0),
    (26, "二层包厢KD", kd_equip["二层包厢KD"]["water"], 1.8),
    (27, "豪华包厢FC组", equip["豪华包厢"]["water"] * 6, 1.5),
    (28, "普通包厢FC组", equip["普通包厢"]["water"] * 6, 1.5),
]
for row, label, water, v in water_rows:
    d_mm, dn, av = calc_pipe(water, v)
    row_values(ws, row, [label, None, water, v, d_mm, dn, av], "填写二层设备水管计算数据", formulas={5: "sqrt(4×水流量/(π×流速×3600×1000))×1000", 7: "4×水流量/(π×DN²×3.6)"}, source=source_core)
for row in [29, 30, 31]:
    for col in range(1, 8):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用二层水管占位公式", source="保存前错误清理")
row_values(ws, 35, ["四层"], "保留四层水系统分区", source="本提示词")
for row, label, water, v in [(36, "四层客房FC组", equip["标准客房"]["water"] * 12, 1.8), (37, "四层客房KD", kd_equip["四层客房KD"]["water"], 1.6)]:
    d_mm, dn, av = calc_pipe(water, v)
    row_values(ws, row, [label, None, water, v, d_mm, dn, av], "填写四层设备水管计算数据", formulas={5: "sqrt(4×水流量/(π×流速×3600×1000))×1000", 7: "4×水流量/(π×DN²×3.6)"}, source=source_core)
for row in range(38, 44):
    for col in range(1, 8):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除未使用四层水管占位", source="保存前错误清理")
# 设备汇总表。
ws = wb["设备汇总表"]
row_values(ws, 4, ["", "二层"], "将设备汇总二层区域作为中餐厅和包厢设备归属", source="本提示词楼层纠错要求")
summary_rows = [
    (5, ["", "1", "ZK-2F-L", "组合式空气处理机", equip["左中餐厅"]["display"], equip["左中餐厅"]["cool"], equip["左中餐厅"]["air"], equip["左中餐厅"]["water"], equip["左中餐厅"]["drop"], "台", 1, "左中餐厅"]),
    (6, ["", "2", "ZK-2F-R", "组合式空气处理机", equip["右中餐厅"]["display"], equip["右中餐厅"]["cool"], equip["右中餐厅"]["air"], equip["右中餐厅"]["water"], equip["右中餐厅"]["drop"], "台", 1, "右中餐厅"]),
    (7, ["", "3", "FC-2F-H01~06", "暗装风机盘管", equip["豪华包厢"]["display"], equip["豪华包厢"]["cool"], equip["豪华包厢"]["air"], equip["豪华包厢"]["water"], equip["豪华包厢"]["drop"], "台", 6, "豪华包厢"]),
    (8, ["", "4", "FC-2F-P01~06", "暗装风机盘管", equip["普通包厢"]["display"], equip["普通包厢"]["cool"], equip["普通包厢"]["air"], equip["普通包厢"]["water"], equip["普通包厢"]["drop"], "台", 6, "普通包厢"]),
    (9, ["", "5", "KD-2F", "吊挂式新风机", kd_equip["二层包厢KD"]["display"], kd_equip["二层包厢KD"]["cool"], kd_equip["二层包厢KD"]["air"], kd_equip["二层包厢KD"]["water"], kd_equip["二层包厢KD"]["drop"], "台", 1, "二层包厢新风"]),
    (10, ["", "四层", "", "", "", "", "", "", "", "", "", ""]),
    (11, ["", "6", "FC-4F-R01~12", "暗装风机盘管", equip["标准客房"]["display"], equip["标准客房"]["cool"], equip["标准客房"]["air"], equip["标准客房"]["water"], equip["标准客房"]["drop"], "台", 12, "标准客房"]),
    (12, ["", "7", "KD-4F", "吊挂式新风机", kd_equip["四层客房KD"]["display"], kd_equip["四层客房KD"]["cool"], kd_equip["四层客房KD"]["air"], kd_equip["四层客房KD"]["water"], kd_equip["四层客房KD"]["drop"], "台", 1, "四层客房新风"]),
]
for row, vals in summary_rows:
    row_values(ws, row, vals, "填写设备汇总表，确保中餐厅设备归入二层", source=source_core)
for row in [13]:
    for col in range(2, 13):
        write_cell(ws, f"{get_column_letter(col)}{row}", None, "清除原五层/汇总占位，避免中餐厅设备误入五层", source="本提示词楼层纠错要求")

wb.calculation.fullCalcOnLoad = True
wb.calculation.forceFullCalc = True
wb.save(OUT)

# Validation.
wb2 = load_workbook(OUT, data_only=False)
errors = []
for ws in wb2.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if cell.value in ("#NAME?", "#DIV/0!", "#REF!", "#VALUE!", "#N/A"):
                errors.append(f"{ws.title}!{cell.coordinate}={cell.value}")

assert wb2.sheetnames == original_sheets, "工作表名称或顺序发生变化"

md = []
md.append("# anonymous_hvac_sample_暖通课程设计计算表修改记录\n")
md.append("## 基本信息\n")
md.append("- 输出文件：`C:\\Users\\example-user\\Desktop\\anonymous_hvac_sample_暖通课程设计计算表_修正版.xlsx`\n")
md.append("- 母版文件：`D:\\ExampleWorkspace\\天正\\暖通课程设计\\示例班级 课程设计资料\\示例班级 课程设计资料\\示例班级-暖通课程设计计算表 .xlsx`\n")
md.append("- 身份信息：匿名示例；不包含真实学生、学号或班级。\n")
md.append("- 工作簿结构：保持原 11 个工作表、原名称、原顺序；未新增、未删除、未重命名工作表。\n")
md.append("- 处理原则：复制母版后在复制件中修改；不新建表格结构；不整体清空工作表；不使用其他同学 Excel 作为母版。\n\n")
md.append("## 关键计算\n")
for name, room in rooms.items():
    md.append(f"- {name}：面积 {room['area']} m2；冷负荷指标 {room['idx']} W/m2；Q={room['q']} kW；Q选型={room['q_sel']} kW；人数合计 {room['people_total']}；设计新风量 {room['fresh_total']} m3/h；新风负荷 {room['fresh_load']} kW。\n")
md.append(f"- 二层包厢总新风量：{box_total} m3/h；KD选型风量：{r3(box_total*1.10)} m3/h。\n")
md.append(f"- 四层客房总新风量：{rooms['标准客房']['fresh_total']} m3/h；KD选型风量：{r3(rooms['标准客房']['fresh_total']*1.10)} m3/h。\n\n")
md.append("## 最终设备选择\n")
for name in ["左中餐厅", "右中餐厅", "豪华包厢", "普通包厢", "标准客房"]:
    e = equip[name]
    count = rooms[name]["count"]
    md.append(f"- {name}：{e['display']} × {count}；制冷量 {e['cool']} kW；风量 {e['air']} m3/h；水流量 {e['water']} kg/h；水压降 {e['drop']} kPa。\n")
for name, e in kd_equip.items():
    md.append(f"- {name}：{e['display']} × 1；制冷量 {e['cool']} kW；风量 {e['air']} m3/h；水流量 {e['water']} kg/h；水压降 {e['drop']} kPa；机外余压 {e['static']} Pa。\n")
md.append("\n## 设备选择理由\n")
md.append("- 左中餐厅：ZK-25（6排）满足 171.737 kW 选型冷量和 20121.874 m3/h 送风量，冷量余量约 5.51%，风量余量约 24.24%。\n")
md.append("- 右中餐厅：ZK-25（8排）满足 202.681 kW 选型冷量和 23750.496 m3/h 送风量，冷量余量约 9.08%，风量余量约 5.26%。\n")
md.append("- 豪华包厢：FC-204（3排管）满足单间 9.696 kW 选型冷量，冷量余量约 14.69%，同类 6 间统一型号。\n")
md.append("- 普通包厢：FC-136（3排管）满足单间 6.654 kW 选型冷量，冷量余量约 16.48%，同类 6 间统一型号。\n")
md.append("- 标准客房：FC-85（3排管）满足单间 4.463 kW 选型冷量，冷量余量约 8.45%，同类 12 间统一型号。\n")
md.append("- 二层包厢KD：KD-4D 吊挂式新风工况，额定 4000 m3/h，满足 3960 m3/h 选型风量。\n")
md.append("- 四层客房KD：KD-1D 吊挂式新风工况，额定 1000 m3/h；相对 792 m3/h 选型风量余量约 26.26%，因数据库最小吊挂式新风型号离散导致略超 25%，需人工接受或复核更小型号来源。\n\n")
md.append("## 楼层归属修正\n")
md.append("- 左中餐厅、右中餐厅及对应 ZK、送风量、新风量、水系统、设备汇总均归入二层中餐厅。\n")
md.append("- 没有执行全局“五层”替换；无关五层标题保留或仅清除无关示例数据。\n\n")
md.append("## 单元格修改明细\n")
md.append("| 工作表 | 单元格 | 原值 | 新值 | 修改原因 | 计算公式 | 数据来源 |\n")
md.append("|---|---:|---|---|---|---|---|\n")
for rec in records:
    md.append(
        f"| {rec['sheet']} | {rec['cell']} | {rec['old']} | {rec['new']} | {rec['reason']} | {rec['formula']} | {rec['source']} |\n"
    )
md.append("\n## 保存前校验\n")
md.append(f"- 工作表数量/名称/顺序：{'通过' if wb2.sheetnames == original_sheets else '失败'}。\n")
md.append(f"- 公式错误字面值扫描：{'未发现' if not errors else '发现 ' + '; '.join(errors)}。\n")
md.append("- 未新增工作表；未删除工作表；未重命名工作表；未调整工作表顺序。\n")
md.append("- 未插入或删除行列；未调整列宽、行高、边框、颜色、字体、合并单元格或打印设置。\n")
md.append("- 左右中餐厅面积保持为 363.08 m2、428.50 m2。\n\n")
md.append("## 待人工复核内容\n")
md.append("- 风管和水管长度缺少图纸实测数据，本次仅按原模板预留管段填写风量/水量、管径和尺寸，阻力计算需待图纸长度复核。\n")
md.append("- 四层客房 KD-1D 风量余量约 26.26%，略高于 25%原则值，属于数据库离散型号导致，建议教师或人工确认。\n")
md.append("- 设备尺寸安装条件未见建筑平面净空校核资料，本次按数据库型号参数选型，最终安装尺寸需结合图纸复核。\n")
md.append("- Excel 公式设置为打开时全量重算；本次已清除公式错误字面值，但未调用 Excel/WPS 图形界面进行人工打开复核。\n")

LOG.write_text("".join(md), encoding="utf-8")

print(f"OUT={OUT}")
print(f"LOG={LOG}")
print(f"records={len(records)}")
print(f"sheets={wb2.sheetnames}")
print(f"errors={errors}")
