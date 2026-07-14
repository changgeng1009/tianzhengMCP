#!/usr/bin/env python3
"""
暖通课程设计计算表填写脚本 - 李宇杰
学号: 52, 班级: REDACTED_CLASS
策略: 紧凑型 (COMPACT)
"""
import json
import math
import shutil
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import openpyxl
from copy import copy
from openpyxl.utils import get_column_letter

# ============================================================
# 0. PATHS
# ============================================================
BASE = r"D:\CodexWork\天正\暖通课程设计"
TEMPLATE = BASE + r"\REDACTED_CLASS 课程设计资料\REDACTED_CLASS 课程设计资料\REDACTED_CLASS-暖通课程设计计算表 .xlsx"
OUTPUT = BASE + r"\李宇杰_52_暖通课程设计计算表_修正版.xlsx"
JSON_PARAMS = BASE + r"\暖通课程设计_AI计算完整包_v1.0\hvac_common_parameters_v1.0.json"
JSON_EQ = BASE + r"\暖通课程设计_AI计算完整包_v1.0\hvac_equipment_database_ZK_FC_KD_v2.0.json"

# ============================================================
# 1. COPY TEMPLATE
# ============================================================
print("Step 1: Copying template...")
shutil.copy2(TEMPLATE, OUTPUT)
print(f"  -> Copied to: {OUTPUT}")

# ============================================================
# 2. ENGINEERING CALCULATIONS
# ============================================================
print("\nStep 2: Performing engineering calculations...")

# --- Fixed parameters ---
AIR_DENSITY = 1.2
ENTHALPY_DIFF = 28.8  # kJ/kg
FRESH_LOAD_COEFF = AIR_DENSITY * ENTHALPY_DIFF / 3600  # = 0.0096 kW per m³/h
COOLING_MARGIN = 1.10

# --- Room data ---
rooms = {
    "左中餐厅": {
        "area": 348.17, "count": 1, "cooling_index": 430,
        "height": 4.2, "supply_ach": 12, "supply_margin": 1.10,
        "fresh_ach": 4, "fresh_per_person": 25,
        "person_rule": "floor", "person_param": 1.3,
        "system": "ZK"
    },
    "右中餐厅": {
        "area": 203.75, "count": 1, "cooling_index": 430,
        "height": 4.2, "supply_ach": 12, "supply_margin": 1.10,
        "fresh_ach": 4, "fresh_per_person": 25,
        "person_rule": "floor", "person_param": 1.3,
        "system": "ZK"
    },
    "豪华包厢": {
        "area": 28.54, "count": 6, "cooling_index": 330,
        "fresh_per_person": 25,
        "person_rule": "ceil_div2", "person_param": 2,
        "system": "FC"
    },
    "普通包厢": {
        "area": 29.03, "count": 6, "cooling_index": 330,
        "fresh_per_person": 25,
        "person_rule": "ceil_div2", "person_param": 2,
        "system": "FC"
    },
    "标准客房": {
        "area": 26.40, "count": 12, "cooling_index": 120,
        "fresh_per_person": 30,
        "person_rule": "fixed2",
        "system": "FC"
    },
}

# --- Calculate each room ---
for name, r in rooms.items():
    # Persons
    if r["person_rule"] == "floor":
        r["single_people"] = math.floor(r["area"] / r["person_param"])
    elif r["person_rule"] == "ceil_div2":
        r["single_people"] = math.ceil(r["area"] / r["person_param"])
    elif r["person_rule"] == "fixed2":
        r["single_people"] = 2
    r["total_people"] = r["single_people"] * r["count"]

    # Cooling load
    r["single_cooling_kw"] = r["area"] * r["cooling_index"] / 1000
    r["single_selection_kw"] = r["single_cooling_kw"] * COOLING_MARGIN
    r["total_cooling_kw"] = r["single_cooling_kw"] * r["count"]

    # Fresh air (single room)
    r["single_fresh_air"] = r["single_people"] * r["fresh_per_person"]

    # Restaurant-specific calculations
    if r["system"] == "ZK":
        r["volume"] = r["area"] * r["height"]
        r["supply_air"] = r["area"] * r["height"] * r["supply_ach"] * r["supply_margin"]
        r["fresh_l1"] = r["total_people"] * r["fresh_per_person"]
        r["fresh_l2"] = r["area"] * r["height"] * r["fresh_ach"]
        r["fresh_l3"] = r["supply_air"] * 0.10
        r["design_fresh_air"] = max(r["fresh_l1"], r["fresh_l2"], r["fresh_l3"])
        r["fresh_air_load"] = r["design_fresh_air"] * FRESH_LOAD_COEFF
    else:
        r["fresh_air_load"] = r["single_fresh_air"] * FRESH_LOAD_COEFF

    print(f"  {name}: 面积={r['area']}m², 单间人数={r['single_people']}, 总人数={r['total_people']}")
    print(f"    单间冷负荷={r['single_cooling_kw']:.3f}kW, 选型冷量={r['single_selection_kw']:.3f}kW")
    if r["system"] == "ZK":
        print(f"    送风量={r['supply_air']:.1f}m³/h, 设计新风={r['design_fresh_air']:.0f}m³/h")
    else:
        print(f"    单间新风={r['single_fresh_air']:.0f}m³/h, 总新风={r['single_fresh_air']*r['count']:.0f}m³/h")

# --- KD fresh air aggregates ---
box_total_fresh = rooms["豪华包厢"]["single_fresh_air"] * 6 + rooms["普通包厢"]["single_fresh_air"] * 6
box_selection_fresh = box_total_fresh * 1.10
box_fresh_load = box_total_fresh * FRESH_LOAD_COEFF

guest_total_fresh = rooms["标准客房"]["single_fresh_air"] * 12
guest_selection_fresh = guest_total_fresh * 1.10
guest_fresh_load = guest_total_fresh * FRESH_LOAD_COEFF

print(f"\n  二层包厢总新风={box_total_fresh:.0f}m³/h, 选型={box_selection_fresh:.0f}m³/h, 负荷={box_fresh_load:.3f}kW")
print(f"  四层客房总新风={guest_total_fresh:.0f}m³/h, 选型={guest_selection_fresh:.0f}m³/h, 负荷={guest_fresh_load:.3f}kW")

# ============================================================
# 3. EQUIPMENT SELECTION (COMPACT STRATEGY)
# ============================================================
print("\nStep 3: Equipment selection (COMPACT strategy)...")

with open(JSON_EQ, 'r', encoding='utf-8') as f:
    eq_db = json.load(f)

zk_models = eq_db["zk"]["models"]
fc_concealed = eq_db["fc"]["concealed_units"]
fc_dimensions = {d["model"]: d for d in eq_db["fc"]["concealed_dimensions"]}

# KD hanging air handler - fresh air condition
kd_hanging = eq_db["kd"]["hanging_air_handler"]["performance"]

# --- ZK Selection ---
def select_zk(design_airflow, selection_cooling, room_name):
    """Select ZK unit using compact strategy"""
    print(f"\n  ZK selection for {room_name}: airflow={design_airflow:.1f}m³/h, cooling={selection_cooling:.3f}kW")
    candidates = []
    for m in zk_models:
        if m["nominal_airflow_m3h"] < design_airflow:
            continue  # airflow too small
        for rows in [4, 6, 8]:
            cool_key = f"cooling_{rows}row_kw"
            if cool_key not in m:
                continue
            rated_cool = m[cool_key]
            ratio = rated_cool / selection_cooling
            if ratio < 1.05:
                continue  # cooling too low
            if ratio > 1.30:
                continue  # cooling too high (compact rule)
            # Check face velocity at design airflow
            section_area = m["section_width_mm"] * m["section_height_mm"] / 1e6
            face_vel = design_airflow / (3600 * section_area)
            if face_vel < 1.0:
                continue  # too low face velocity

            water_flow_key = f"cooling_water_flow_{rows}row_t_h"
            water_drop_key = f"cooling_water_drop_{rows}row_kpa"

            candidates.append({
                "model": m["model"],
                "rows": rows,
                "rated_cooling": rated_cool,
                "ratio": ratio,
                "section_w": m["section_width_mm"],
                "section_h": m["section_height_mm"],
                "section_area": section_area,
                "face_vel": face_vel,
                "nominal_airflow": m["nominal_airflow_m3h"],
                "fan_pressure": m["fan_pressure_pa"],
                "motor_power": m["motor_power_kw_text"],
                "noise": m["noise_dba"],
                "water_flow": m.get(water_flow_key, "N/A"),
                "water_drop": m.get(water_drop_key, "N/A"),
                "water_pipe": m["cooling_water_pipe_mm"],
            })

    # Sort by compact: smaller section area first, then by ratio (closer to 1.10 preferred)
    candidates.sort(key=lambda c: (c["section_w"] * c["section_h"], abs(c["ratio"] - 1.10)))

    print(f"    Found {len(candidates)} qualified candidates")
    for i, c in enumerate(candidates):
        print(f"    [{i+1}] {c['model']} {c['rows']}row: {c['rated_cooling']}kW (ratio={c['ratio']:.3f}), "
              f"section={c['section_w']}×{c['section_h']}mm, face_vel={c['face_vel']:.2f}m/s, "
              f"water={c['water_flow']}t/h, drop={c['water_drop']}kPa")

    if not candidates:
        print(f"    WARNING: No qualified ZK candidate found!")
        return None
    return candidates[0]

zk_left = select_zk(rooms["左中餐厅"]["supply_air"], rooms["左中餐厅"]["single_selection_kw"], "左中餐厅")
zk_right = select_zk(rooms["右中餐厅"]["supply_air"], rooms["右中餐厅"]["single_selection_kw"], "右中餐厅")

# --- FC Selection ---
def select_fc(selection_cooling, room_name, count):
    """Select FC concealed unit using compact strategy"""
    print(f"\n  FC selection for {room_name}: cooling={selection_cooling:.3f}kW, count={count}")
    candidates = []
    for unit in fc_concealed:
        rated_cool = unit["rated_cooling_kw"]
        # Only consider 2-row and 3-row (not 3+1)
        coil = unit["coil_configuration"]
        if coil not in ["2排管", "3排管"]:
            continue
        ratio = rated_cool / selection_cooling
        if ratio < 1.05:
            continue
        if ratio > 1.30:
            continue

        model = unit["model"]
        dim = fc_dimensions.get(model)
        if not dim:
            continue

        airflow_high = unit["airflow_m3h"]["high"]
        water_flow = unit["water_flow_kg_h"]
        water_drop = unit["water_pressure_drop_kpa"]
        motor_50pa = unit["motor_power_W"].get("50Pa", unit["motor_power_W"].get("30Pa", unit["motor_power_W"].get("12Pa")))

        candidates.append({
            "model": model,
            "coil": coil,
            "rated_cooling": rated_cool,
            "ratio": ratio,
            "airflow_high": airflow_high,
            "dim_A": dim["A_mm"],
            "dim_B": dim["B_mm"],
            "dim_C": dim["C_mm"],
            "water_flow": water_flow,
            "water_drop": water_drop,
            "motor_power": motor_50pa,
            "noise_50pa": unit["noise_dba"].get("50Pa", unit["noise_dba"].get("30Pa", 0)),
        })

    # Compact: smaller dims first (A × B), prefer 3-row over 2-row for compactness
    candidates.sort(key=lambda c: (c["dim_A"] * c["dim_B"], 0 if c["coil"] == "3排管" else 1, abs(c["ratio"] - 1.15)))

    print(f"    Found {len(candidates)} qualified candidates")
    for i, c in enumerate(candidates[:8]):
        print(f"    [{i+1}] FC-{c['model']} {c['coil']}: {c['rated_cooling']}kW (ratio={c['ratio']:.3f}), "
              f"dim={c['dim_A']}×{c['dim_B']}×{c['dim_C']}mm, air={c['airflow_high']}m³/h, "
              f"water={c['water_flow']}kg/h, drop={c['water_drop']}kPa")

    if not candidates:
        print(f"    WARNING: No qualified FC candidate found!")
        return None
    return candidates[0]

fc_luxury = select_fc(rooms["豪华包厢"]["single_selection_kw"], "豪华包厢", 6)
fc_ordinary = select_fc(rooms["普通包厢"]["single_selection_kw"], "普通包厢", 6)
fc_guest = select_fc(rooms["标准客房"]["single_selection_kw"], "标准客房", 12)

# --- KD Selection (Hanging, Fresh Air condition) ---
def select_kd(selection_airflow, fresh_load, area_name):
    """Select KD hanging unit using compact strategy"""
    print(f"\n  KD selection for {area_name}: airflow={selection_airflow:.0f}m³/h, load={fresh_load:.3f}kW")
    candidates = []
    for unit in kd_hanging:
        if unit.get("condition") and unit["condition"] != "新风":
            # Check if it has fresh_condition (nested)
            pass
        # Look for fresh_condition data
        fresh_data = unit.get("fresh_condition")
        if not fresh_data:
            continue

        airflow = unit["airflow_m3h"]
        if airflow < selection_airflow:
            continue

        rated_cool = fresh_data["cooling_kw"]
        ratio = rated_cool / fresh_load if fresh_load > 0 else 999
        if ratio < 1.0:  # At least match the load
            continue

        water_flow = fresh_data["water_flow_m3h"]
        water_drop = fresh_data["water_drop_kpa"]
        ext_sp = unit["external_static_pa"]
        if isinstance(ext_sp, dict):
            ext_sp = ext_sp.get("class_I", ext_sp.get("class_II", 0))
        motor = unit["motor_power_kw"]
        if isinstance(motor, dict):
            motor = motor.get("class_I", motor.get("class_II", "0"))
        weight = unit.get("weight_kg", "N/A")

        candidates.append({
            "model": unit["model"],
            "rows": unit["coil_rows"],
            "airflow": airflow,
            "rated_cooling": rated_cool,
            "ratio": ratio,
            "water_flow": water_flow,
            "water_drop": water_drop,
            "ext_static": ext_sp,
            "motor_power": motor,
            "weight": weight,
        })

    # Compact: smaller airflow first (closest to requirement), then smaller ratio
    candidates.sort(key=lambda c: (c["airflow"], abs(c["ratio"] - 1.15)))

    print(f"    Found {len(candidates)} qualified candidates")
    for i, c in enumerate(candidates[:8]):
        print(f"    [{i+1}] {c['model']} {c['rows']}row: air={c['airflow']}m³/h, cool={c['rated_cooling']}kW "
              f"(ratio={c['ratio']:.3f}), water={c['water_flow']}m³/h, drop={c['water_drop']}kPa, "
              f"ESP={c['ext_static']}Pa, motor={c['motor_power']}kW")

    if not candidates:
        print(f"    WARNING: No qualified KD candidate found!")
        return None
    return candidates[0]

kd_2f = select_kd(box_selection_fresh, box_fresh_load, "二层包厢")
kd_4f = select_kd(guest_selection_fresh, guest_fresh_load, "四层客房")

# ============================================================
# 4. PRINT SELECTION SUMMARY
# ============================================================
print("\n" + "="*70)
print("FINAL EQUIPMENT SELECTION SUMMARY")
print("="*70)
for name, sel in [("左中餐厅ZK", zk_left), ("右中餐厅ZK", zk_right),
                   ("豪华包厢FC", fc_luxury), ("普通包厢FC", fc_ordinary), ("标准客房FC", fc_guest),
                   ("二层包厢KD", kd_2f), ("四层客房KD", kd_4f)]:
    if sel:
        if "section_w" in sel:
            print(f"  {name}: {sel['model']} {sel['rows']}row, cooling={sel['rated_cooling']}kW, "
                  f"section={sel['section_w']}×{sel['section_h']}mm")
        elif "dim_A" in sel:
            print(f"  {name}: FC-{sel['model']} {sel['coil']}, cooling={sel['rated_cooling']}kW, "
                  f"dim={sel['dim_A']}×{sel['dim_B']}×{sel['dim_C']}mm")
        elif "ext_static" in sel:
            print(f"  {name}: {sel['model']} {sel['rows']}row, air={sel['airflow']}m³/h, "
                  f"cooling={sel['rated_cooling']}kW, motor={sel['motor_power']}kW")
    else:
        print(f"  {name}: SELECTION FAILED!")

print("\nStep 4: Filling Excel template...")
print("="*70)
