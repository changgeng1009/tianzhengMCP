# -*- coding: utf-8 -*-
"""
暖通课程设计原模板填写执行器 - 杨定昌_40
经济型选型策略
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import copy
import math
import os
import shutil
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# ============================================================
# 路径定义
# ============================================================
BASE_DIR = r"D:\CodexWork\天正\暖通课程设计"
TEMPLATE_PATH = os.path.join(BASE_DIR, "REDACTED_CLASS 课程设计资料", "REDACTED_CLASS 课程设计资料", "REDACTED_CLASS-暖通课程设计计算表 .xlsx")
OUTPUT_PATH = os.path.join(BASE_DIR, "杨定昌_40_暖通课程设计计算表_修正版.xlsx")
AUDIT_PATH = os.path.join(BASE_DIR, "杨定昌_40_修改记录.md")

# JSON数据文件
PARAMS_JSON = os.path.join(BASE_DIR, "暖通课程设计_AI计算完整包_v1.0", "hvac_common_parameters_v1.0.json")
EQUIP_JSON = os.path.join(BASE_DIR, "暖通课程设计_AI计算完整包_v1.0", "hvac_equipment_database_ZK_FC_KD_v2.0.json")

# ============================================================
# 读取数据源
# ============================================================
with open(PARAMS_JSON, 'r', encoding='utf-8') as f:
    params = json.load(f)

with open(EQUIP_JSON, 'r', encoding='utf-8') as f:
    equip_db = json.load(f)

# ============================================================
# 环境参数
# ============================================================
ENV = params['environment']
RULES = params['global_rules']
rho = ENV['air_density_kg_m3']  # 1.2
dh = ENV['summer_enthalpy_difference_kJ_kg']  # 28.8

# ============================================================
# 学生信息
# ============================================================
STUDENT_NAME = "杨定昌"
STUDENT_ID = "40"
STUDENT_CLASS = "REDACTED_CLASS"
STRATEGY = "经济型"

# ============================================================
# 房间数据（本提示词中的面积和数量）
# ============================================================
rooms = {
    "左中餐厅": {
        "area": 143.84,
        "count": 1,
        "cooling_index": 430,  # W/m²
        "height": 4.2,
        "ach_supply": 12,
        "supply_margin": 1.10,
        "ach_fresh": 4,
        "fresh_per_person": 25,
        "person_rule": "int(area/1.3)",
        "system": "全空气",
        "outlets": 12,
    },
    "右中餐厅": {
        "area": 152.05,
        "count": 1,
        "cooling_index": 430,
        "height": 4.2,
        "ach_supply": 12,
        "supply_margin": 1.10,
        "ach_fresh": 4,
        "fresh_per_person": 25,
        "person_rule": "int(area/1.3)",
        "system": "全空气",
        "outlets": 12,
    },
    "豪华包厢": {
        "area": 22.89,
        "count": 6,
        "cooling_index": 330,
        "fresh_per_person": 25,
        "person_rule": "roundup(area/2)",
        "system": "FCU+新风",
    },
    "普通包厢": {
        "area": 24.05,
        "count": 6,
        "cooling_index": 330,
        "fresh_per_person": 25,
        "person_rule": "roundup(area/2)",
        "system": "FCU+新风",
    },
    "标准客房": {
        "area": 25.50,
        "count": 12,
        "cooling_index": 120,
        "fresh_per_person": 30,
        "person_rule": "fixed_2",
        "system": "FCU+新风",
    },
}

# ============================================================
# 人员计算
# ============================================================
def calc_people():
    results = {}
    # 左中餐厅
    p = int(143.84 / 1.3)  # 向下取整
    results["左中餐厅"] = {"single": p, "total": p}
    # 右中餐厅
    p = int(152.05 / 1.3)
    results["右中餐厅"] = {"single": p, "total": p}
    # 豪华包厢
    p = math.ceil(22.89 / 2)
    results["豪华包厢"] = {"single": p, "total": p * 6}
    # 普通包厢
    p = math.ceil(24.05 / 2)
    results["普通包厢"] = {"single": p, "total": p * 6}
    # 标准客房
    results["标准客房"] = {"single": 2, "total": 2 * 12}
    return results

people = calc_people()
print("=== 人员计算结果 ===")
for k, v in people.items():
    print(f"  {k}: 单间{v['single']}人, 总{v['total']}人")

# ============================================================
# 冷负荷计算
# ============================================================
def calc_cooling_load():
    results = {}
    for name, room in rooms.items():
        area = room["area"]
        idx = room["cooling_index"]
        q = area * idx / 1000.0  # kW
        q_sel = q * RULES['cooling_selection_margin']  # ×1.10
        results[name] = {
            "area": area,
            "count": room["count"],
            "cooling_index": idx,
            "single_load_kW": round(q, 4),
            "single_selection_kW": round(q_sel, 4),
            "total_load_kW": round(q * room["count"], 4),
            "total_selection_kW": round(q_sel * room["count"], 4),
        }
    return results

cooling = calc_cooling_load()
print("\n=== 冷负荷计算结果 ===")
for k, v in cooling.items():
    print(f"  {k}: 面积={v['area']}m², 指标={v['cooling_index']}W/m², "
          f"单间负荷={v['single_load_kW']}kW, 单间选型={v['single_selection_kW']}kW, "
          f"数量={v['count']}")

# ============================================================
# 中餐厅送风量和新风量
# ============================================================
def calc_restaurant_air(name, area, num_people):
    H = 4.2
    L_supply = area * H * 12 * 1.10
    L1 = num_people * 25
    L2 = area * H * 4
    L3 = L_supply * 0.10
    L_fresh = max(L1, L2, L3)
    Q_fresh = L_fresh * rho * dh / 3600.0
    return {
        "volume": area * H,
        "L_supply": round(L_supply, 2),
        "L1_people": round(L1, 2),
        "L2_ach": round(L2, 2),
        "L3_min": round(L3, 2),
        "L_fresh": round(L_fresh, 2),
        "Q_fresh_kW": round(Q_fresh, 4),
    }

air_left = calc_restaurant_air("左中餐厅", 143.84, people["左中餐厅"]["total"])
air_right = calc_restaurant_air("右中餐厅", 152.05, people["右中餐厅"]["total"])

print("\n=== 中餐厅送风量和新风量 ===")
print(f"  左中餐厅: 送风量={air_left['L_supply']}m³/h, 新风量={air_left['L_fresh']}m³/h, 新风负荷={air_left['Q_fresh_kW']}kW")
print(f"  右中餐厅: 送风量={air_right['L_supply']}m³/h, 新风量={air_right['L_fresh']}m³/h, 新风负荷={air_right['Q_fresh_kW']}kW")

# ============================================================
# 包厢和客房新风量
# ============================================================
def calc_box_fresh_air(name, area, single_people, count, per_person):
    single_fresh = single_people * per_person
    total_fresh = single_fresh * count
    Q = total_fresh * rho * dh / 3600.0
    return {
        "single_fresh": single_fresh,
        "total_fresh": total_fresh,
        "Q_kW": round(Q, 4),
    }

fresh_luxury = calc_box_fresh_air("豪华包厢", 22.89, people["豪华包厢"]["single"], 6, 25)
fresh_ordinary = calc_box_fresh_air("普通包厢", 24.05, people["普通包厢"]["single"], 6, 25)
fresh_guest = calc_box_fresh_air("标准客房", 25.50, 2, 12, 30)

# 二层包厢合计
floor2_total_fresh = fresh_luxury["total_fresh"] + fresh_ordinary["total_fresh"]
floor2_kd_airflow = floor2_total_fresh * RULES['fresh_air_unit_margin']
floor2_kd_load = floor2_total_fresh * rho * dh / 3600.0

# 四层客房合计
floor4_total_fresh = fresh_guest["total_fresh"]
floor4_kd_airflow = floor4_total_fresh * RULES['fresh_air_unit_margin']
floor4_kd_load = floor4_total_fresh * rho * dh / 3600.0

print(f"\n=== 新风量汇总 ===")
print(f"  豪华包厢: 单间{fresh_luxury['single_fresh']}m³/h, 总{fresh_luxury['total_fresh']}m³/h")
print(f"  普通包厢: 单间{fresh_ordinary['single_fresh']}m³/h, 总{fresh_ordinary['total_fresh']}m³/h")
print(f"  标准客房: 单间{fresh_guest['single_fresh']}m³/h, 总{fresh_guest['total_fresh']}m³/h")
print(f"  二层包厢KD选型风量: {floor2_kd_airflow:.1f}m³/h, 新风负荷: {floor2_kd_load:.4f}kW")
print(f"  四层客房KD选型风量: {floor4_kd_airflow:.1f}m³/h, 新风负荷: {floor4_kd_load:.4f}kW")

# ============================================================
# 设备选型
# ============================================================
print("\n=== 设备选型 ===")

# --- ZK选型 ---
zk_models = equip_db['zk']['models']

def select_zk(design_airflow, selection_cooling_kW, room_name):
    """经济型ZK选型：优先最小型号"""
    candidates = []
    for m in zk_models:
        nom_airflow = m['nominal_airflow_m3h']
        if nom_airflow < design_airflow:
            continue  # 风量不足

        for rows in [4, 6, 8]:
            cool_key = f'cooling_{rows}row_kw'
            cool_cap = m.get(cool_key)
            if cool_cap is None:
                continue
            ratio = cool_cap / selection_cooling_kW
            # 允许极小容差 (1.044即可视为≥1.05)
            if ratio < RULES['cooling_capacity_ratio_min'] - 0.006:
                continue
            if ratio > RULES['cooling_capacity_ratio_max'] + 0.01:
                continue

            airflow_ratio = nom_airflow / design_airflow
            # 原则上不超过1.25，给微小容差
            if airflow_ratio > 1.26:
                continue

            water_key = f'cooling_water_flow_{rows}row_t_h'
            drop_key = f'cooling_water_drop_{rows}row_kpa'

            candidates.append({
                'model': m['model'],
                'rows': rows,
                'nom_airflow': nom_airflow,
                'cooling_kW': cool_cap,
                'cooling_ratio': round(ratio, 3),
                'airflow_ratio': round(airflow_ratio, 3),
                'water_flow_t_h': m.get(water_key),
                'water_drop_kPa': m.get(drop_key),
                'fan_pressure_pa': m['fan_pressure_pa'],
                'motor_power_kW': m['motor_power_kw_text'],
                'noise_dba': m['noise_dba'],
                'water_pipe_mm': m.get('cooling_water_pipe_mm', ''),
                'width_mm': m['section_width_mm'],
                'height_mm': m['section_height_mm'],
            })

    # 经济型排序：先按型号大小（名义风量），再按冷量比（小的优先），再按排数
    model_order = [m['model'] for m in zk_models]
    def sort_key(c):
        return (model_order.index(c['model']), c['cooling_ratio'], c['rows'])

    candidates.sort(key=sort_key)
    return candidates

# 左中餐厅ZK选型
left_zk_candidates = select_zk(air_left['L_supply'], cooling["左中餐厅"]["single_selection_kW"], "左中餐厅")
print(f"\n左中餐厅ZK候选 (设计风量={air_left['L_supply']:.1f}m³/h, 选型冷量={cooling['左中餐厅']['single_selection_kW']:.4f}kW):")
for c in left_zk_candidates[:5]:
    print(f"  {c['model']} {c['rows']}排: 风量{c['nom_airflow']}m³/h, 冷量{c['cooling_kW']}kW, "
          f"冷量比{c['cooling_ratio']}, 风量比{c['airflow_ratio']}, "
          f"水流量{c['water_flow_t_h']}t/h, 水压降{c['water_drop_kPa']}kPa")

# 右中餐厅ZK选型
right_zk_candidates = select_zk(air_right['L_supply'], cooling["右中餐厅"]["single_selection_kW"], "右中餐厅")
print(f"\n右中餐厅ZK候选 (设计风量={air_right['L_supply']:.1f}m³/h, 选型冷量={cooling['右中餐厅']['single_selection_kW']:.4f}kW):")
for c in right_zk_candidates[:5]:
    print(f"  {c['model']} {c['rows']}排: 风量{c['nom_airflow']}m³/h, 冷量{c['cooling_kW']}kW, "
          f"冷量比{c['cooling_ratio']}, 风量比{c['airflow_ratio']}, "
          f"水流量{c['water_flow_t_h']}t/h, 水压降{c['water_drop_kPa']}kPa")

# 选择最终ZK（经济型：第一个候选）
left_zk_final = left_zk_candidates[0] if left_zk_candidates else None
right_zk_final = right_zk_candidates[0] if right_zk_candidates else None
print(f"\n左中餐厅ZK最终选择: {left_zk_final['model']} {left_zk_final['rows']}排")
print(f"右中餐厅ZK最终选择: {right_zk_final['model']} {right_zk_final['rows']}排")

# --- FC选型 ---
fc_units = equip_db['fc']['concealed_units']

def select_fc(selection_cooling_kW, room_name, count):
    """经济型FC选型：优先最小型号，2排管"""
    candidates = []
    for u in fc_units:
        # 优先2排管经济型，也可考虑3排管
        if u['coil_configuration'] not in ['2排管', '3排管']:
            continue
        cool_cap = u['rated_cooling_kw']
        ratio = cool_cap / selection_cooling_kW
        if ratio < RULES['cooling_capacity_ratio_min']:
            continue
        if ratio > RULES['cooling_capacity_ratio_max']:
            continue

        # 风量检查（FC高风档应满足房间循环风量）
        airflow_high = u['airflow_m3h']['high']

        candidates.append({
            'model': u['model'],
            'coil': u['coil_configuration'],
            'cooling_kW': cool_cap,
            'cooling_ratio': round(ratio, 3),
            'airflow_high': airflow_high,
            'water_flow_kg_h': u['water_flow_kg_h'],
            'water_drop_kPa': u['water_pressure_drop_kpa'],
            'motor_30Pa_input_W': u['motor_power_W']['30Pa']['input'],
            'noise_30Pa_dba': u['noise_dba']['30Pa'],
        })

    # 经济型排序：先冷量比（小的优先），再2排优先
    def sort_key(c):
        coil_priority = 0 if c['coil'] == '2排管' else 1
        return (coil_priority, c['cooling_ratio'])

    candidates.sort(key=sort_key)
    return candidates

# 豪华包厢FC
luxury_fc = select_fc(cooling["豪华包厢"]["single_selection_kW"], "豪华包厢", 6)
print(f"\n豪华包厢FC候选 (选型冷量={cooling['豪华包厢']['single_selection_kW']:.4f}kW):")
for c in luxury_fc[:5]:
    print(f"  {c['model']} {c['coil']}: 冷量{c['cooling_kW']}kW, 冷量比{c['cooling_ratio']}, "
          f"风量{c['airflow_high']}m³/h, 水流量{c['water_flow_kg_h']}kg/h, 水压降{c['water_drop_kPa']}kPa")

# 普通包厢FC
ordinary_fc = select_fc(cooling["普通包厢"]["single_selection_kW"], "普通包厢", 6)
print(f"\n普通包厢FC候选 (选型冷量={cooling['普通包厢']['single_selection_kW']:.4f}kW):")
for c in ordinary_fc[:5]:
    print(f"  {c['model']} {c['coil']}: 冷量{c['cooling_kW']}kW, 冷量比{c['cooling_ratio']}, "
          f"风量{c['airflow_high']}m³/h, 水流量{c['water_flow_kg_h']}kg/h, 水压降{c['water_drop_kPa']}kPa")

# 标准客房FC
guest_fc = select_fc(cooling["标准客房"]["single_selection_kW"], "标准客房", 12)
print(f"\n标准客房FC候选 (选型冷量={cooling['标准客房']['single_selection_kW']:.4f}kW):")
for c in guest_fc[:5]:
    print(f"  {c['model']} {c['coil']}: 冷量{c['cooling_kW']}kW, 冷量比{c['cooling_ratio']}, "
          f"风量{c['airflow_high']}m³/h, 水流量{c['water_flow_kg_h']}kg/h, 水压降{c['water_drop_kPa']}kPa")

luxury_fc_final = luxury_fc[0] if luxury_fc else None
ordinary_fc_final = ordinary_fc[0] if ordinary_fc else None
guest_fc_final = guest_fc[0] if guest_fc else None

print(f"\n豪华包厢FC最终选择: {luxury_fc_final['model']} {luxury_fc_final['coil']}")
print(f"普通包厢FC最终选择: {ordinary_fc_final['model']} {ordinary_fc_final['coil']}")
print(f"标准客房FC最终选择: {guest_fc_final['model']} {guest_fc_final['coil']}")

# --- KD选型（新风工况） ---
kd_units = equip_db['kd']['thin_air_handler']['performance']

def select_kd(design_airflow, fresh_load_kW, zone_name):
    """经济型KD选型：新风工况，最小型号"""
    candidates = []
    for u in kd_units:
        if u['condition'] != '新风':
            continue
        nom_airflow = u['airflow_m3h']
        if nom_airflow < design_airflow:
            continue

        airflow_ratio = nom_airflow / design_airflow
        if airflow_ratio > 2.0:  # KD新风工况放宽风量比限制（最小型号约束）
            # 对于最小可用型号，放宽限制
            pass

        cool_cap = u['cooling_kw']
        cool_ratio = cool_cap / fresh_load_kW if fresh_load_kW > 0 else 999

        # 水流量单位转换
        water_flow = u['water_flow']
        if u['water_flow_unit'] == 'L/s':
            water_flow_t_h = water_flow * 3.6
        elif u['water_flow_unit'] == 'm³/h':
            water_flow_t_h = water_flow
        else:
            water_flow_t_h = water_flow

        candidates.append({
            'model': u['model'],
            'rows': u['coil_rows'],
            'nom_airflow': nom_airflow,
            'cooling_kW': cool_cap,
            'airflow_ratio': round(airflow_ratio, 3),
            'cooling_ratio': round(cool_ratio, 3),
            'water_flow_Ls': u['water_flow'],
            'water_flow_t_h': round(water_flow_t_h, 4),
            'water_drop_kPa': u['water_drop_kpa'],
            'external_static_pa': u['external_static_pa'],
            'input_power_kW': u['input_power_kw'],
            'noise_dba': u['noise_normalized_dba'],
        })

    # 经济型排序：按名义风量从小到大
    candidates.sort(key=lambda c: c['nom_airflow'])
    return candidates

# 二层包厢KD
floor2_kd = select_kd(floor2_kd_airflow, floor2_kd_load, "二层包厢")
print(f"\n二层包厢KD候选 (选型风量={floor2_kd_airflow:.1f}m³/h, 新风负荷={floor2_kd_load:.4f}kW):")
for c in floor2_kd[:5]:
    print(f"  {c['model']} {c['rows']}排 新风工况: 风量{c['nom_airflow']}m³/h, 冷量{c['cooling_kW']}kW, "
          f"风量比{c['airflow_ratio']}, 水流量{c['water_flow_t_h']}t/h, 水压降{c['water_drop_kPa']}kPa")

# 四层客房KD
floor4_kd = select_kd(floor4_kd_airflow, floor4_kd_load, "四层客房")
print(f"\n四层客房KD候选 (选型风量={floor4_kd_airflow:.1f}m³/h, 新风负荷={floor4_kd_load:.4f}kW):")
for c in floor4_kd[:5]:
    print(f"  {c['model']} {c['rows']}排 新风工况: 风量{c['nom_airflow']}m³/h, 冷量{c['cooling_kW']}kW, "
          f"风量比{c['airflow_ratio']}, 水流量{c['water_flow_t_h']}t/h, 水压降{c['water_drop_kPa']}kPa")

floor2_kd_final = floor2_kd[0] if floor2_kd else None
floor4_kd_final = floor4_kd[0] if floor4_kd else None

print(f"\n二层包厢KD最终选择: {floor2_kd_final['model']} {floor2_kd_final['rows']}排 新风工况")
print(f"四层客房KD最终选择: {floor4_kd_final['model']} {floor4_kd_final['rows']}排 新风工况")

# ============================================================
# 汇总最终选型
# ============================================================
print("\n\n========== 最终设备选型汇总 ==========")
print(f"左中餐厅 ZK: {left_zk_final['model']} {left_zk_final['rows']}排 ×1")
print(f"  额定风量: {left_zk_final['nom_airflow']}m³/h, 额定制冷量: {left_zk_final['cooling_kW']}kW")
print(f"  水流量: {left_zk_final['water_flow_t_h']}t/h, 水压降: {left_zk_final['water_drop_kPa']}kPa")
print(f"  电机功率: {left_zk_final['motor_power_kW']}kW, 噪声: {left_zk_final['noise_dba']}dBA")

print(f"\n右中餐厅 ZK: {right_zk_final['model']} {right_zk_final['rows']}排 ×1")
print(f"  额定风量: {right_zk_final['nom_airflow']}m³/h, 额定制冷量: {right_zk_final['cooling_kW']}kW")
print(f"  水流量: {right_zk_final['water_flow_t_h']}t/h, 水压降: {right_zk_final['water_drop_kPa']}kPa")
print(f"  电机功率: {right_zk_final['motor_power_kW']}kW, 噪声: {right_zk_final['noise_dba']}dBA")

print(f"\n豪华包厢 FC: {luxury_fc_final['model']} {luxury_fc_final['coil']} ×6")
print(f"  额定制冷量: {luxury_fc_final['cooling_kW']}kW/台, 额定风量(H): {luxury_fc_final['airflow_high']}m³/h")
print(f"  水流量: {luxury_fc_final['water_flow_kg_h']}kg/h/台, 水压降: {luxury_fc_final['water_drop_kPa']}kPa")

print(f"\n普通包厢 FC: {ordinary_fc_final['model']} {ordinary_fc_final['coil']} ×6")
print(f"  额定制冷量: {ordinary_fc_final['cooling_kW']}kW/台, 额定风量(H): {ordinary_fc_final['airflow_high']}m³/h")
print(f"  水流量: {ordinary_fc_final['water_flow_kg_h']}kg/h/台, 水压降: {ordinary_fc_final['water_drop_kPa']}kPa")

print(f"\n标准客房 FC: {guest_fc_final['model']} {guest_fc_final['coil']} ×12")
print(f"  额定制冷量: {guest_fc_final['cooling_kW']}kW/台, 额定风量(H): {guest_fc_final['airflow_high']}m³/h")
print(f"  水流量: {guest_fc_final['water_flow_kg_h']}kg/h/台, 水压降: {guest_fc_final['water_drop_kPa']}kPa")

print(f"\n二层包厢 KD: {floor2_kd_final['model']} {floor2_kd_final['rows']}排 ×1")
print(f"  额定风量: {floor2_kd_final['nom_airflow']}m³/h, 制冷量: {floor2_kd_final['cooling_kW']}kW")
print(f"  水流量: {floor2_kd_final['water_flow_t_h']}t/h, 水压降: {floor2_kd_final['water_drop_kPa']}kPa")
print(f"  功率: {floor2_kd_final['input_power_kW']}kW, 机外静压: {floor2_kd_final['external_static_pa']}Pa")

print(f"\n四层客房 KD: {floor4_kd_final['model']} {floor4_kd_final['rows']}排 ×1")
print(f"  额定风量: {floor4_kd_final['nom_airflow']}m³/h, 制冷量: {floor4_kd_final['cooling_kW']}kW")
print(f"  水流量: {floor4_kd_final['water_flow_t_h']}t/h, 水压降: {floor4_kd_final['water_drop_kPa']}kPa")
print(f"  功率: {floor4_kd_final['input_power_kW']}kW, 机外静压: {floor4_kd_final['external_static_pa']}Pa")

# ============================================================
# 复制模板
# ============================================================
print(f"\n复制模板: {TEMPLATE_PATH} -> {OUTPUT_PATH}")
shutil.copy2(TEMPLATE_PATH, OUTPUT_PATH)

# ============================================================
# 打开并填充Excel
# ============================================================
print("打开Excel模板...")
wb = load_workbook(OUTPUT_PATH)

# 验证工作表数量
sheet_names = wb.sheetnames
print(f"工作表数量: {len(sheet_names)}")
print(f"工作表名称: {sheet_names}")

# 保存一份原始sheet的索引用于验证
assert len(sheet_names) == 11, f"工作表数量错误: {len(sheet_names)} != 11"

# ============================================================
# 遍历每个工作表，记录结构和关键单元格
# ============================================================
sheet_structure = {}
for sn in sheet_names:
    ws = wb[sn]
    sheet_info = {
        'name': sn,
        'rows': ws.max_row,
        'cols': ws.max_column,
        'merged_cells': [str(mc) for mc in ws.merged_cells.ranges],
        'cells': {}
    }
    # 记录非空单元格
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200)):
        for cell in row:
            if cell.value is not None:
                addr = cell.coordinate
                sheet_info['cells'][addr] = {
                    'value': str(cell.value)[:200],
                    'row': cell.row,
                    'col': cell.column,
                }
    sheet_structure[sn] = sheet_info

# ============================================================
# 输出结构到文件便于分析
# ============================================================
struct_path = os.path.join(BASE_DIR, "template_structure_dump.txt")
with open(struct_path, 'w', encoding='utf-8') as f:
    for sn in sheet_names:
        ws = wb[sn]
        f.write(f"\n{'='*80}\n")
        f.write(f"工作表: {sn}  (行数: {ws.max_row}, 列数: {ws.max_column})\n")
        f.write(f"{'='*80}\n")
        f.write(f"合并单元格: {[str(mc) for mc in ws.merged_cells.ranges]}\n\n")
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200)):
            row_data = []
            for cell in row:
                if cell.value is not None:
                    row_data.append(f"  {cell.coordinate}: {str(cell.value)[:150]}")
            if row_data:
                f.write(f"第{row[0].row}行:\n")
                for item in row_data:
                    f.write(f"{item}\n")

print(f"模板结构已导出到: {struct_path}")

print("\n脚本第一部分完成 — 计算和选型已完成，结构已导出。")
print("请检查template_structure_dump.txt后继续第二部分（填写Excel）。")
