Geometry cleanup: redacted / not_rerun. Original drawing-derived coordinates were removed; remaining historical outcomes are not current acceptance evidence.

> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

# Stage 6-P2 正确样本快速多区域坐标系重建报告

**Run ID:** `stage6_p2_coordinate_reconstruction_20260713_101528`
**Created:** 2026-07-13T02:59:27.426076+00:00

## 输入身份
- Reference：`D:\ExampleWorkspace\天正\图纸\reference_sample_t8_t8_t8.dwg`
  - SHA256：`redacted_input_sha256`
  - 实体数：10606
- Target：`D:\ExampleWorkspace\天正\图纸\target_sample_t8.dwg`
  - SHA256：`redacted_input_sha256`
  - 实体数：6481

## 区域检测
- Reference 区域数：7
- Target 逻辑区域数：8
- 人工确认绑定数：7
- 映射冲突数：0

## 坐标变换
- VERIFIED: 4
- LOW_CONFIDENCE: 2
- REJECTED: 1

| Pair | Model | Status | Anchors (total/inlier) | Types | DirCov | RMS | Scale | Confidence |
|------|-------|--------|------------------------|-------|--------|-----|-------|------------|
[redacted: drawing-derived numeric geometry/evidence removed; not_rerun]
[redacted: drawing-derived numeric geometry/evidence removed; not_rerun]
[redacted: drawing-derived numeric geometry/evidence removed; not_rerun]
| transform_pair_04_roof | translation_only | **VERIFIED** | 764/753 | 6 | 0.83 | 190.304 | (1.000, 1.000) | 0.986 |
| transform_pair_05_tank | translation_only | **VERIFIED** | 82/78 | 4 | 0.83 | 282.5902 | (1.000, 1.000) | 0.951 |
| transform_pair_06_water_drain_sys | translation_only | **VERIFIED** | 243/243 | 4 | 0.83 | 0.0 | (1.000, 1.000) | 1.000 |
| transform_pair_07_fire_sys | translation_only | **VERIFIED** | 263/257 | 4 | 0.83 | 413.4074 | (1.000, 1.000) | 0.977 |

## 保护区域
- **target_protected_pump_room_detail_0001**：泵房大样 图幅A0 比例1:50
  - 策略：`PROTECTED_COMPLETE_REGION`
  - 实体数：395
  - 原因：NO_REFERENCE_MATCH

## 安全门
- `old_plan_reused`: False
- `target_write`: False
- `target_save`: False
- `reference_hash_unchanged`: True
- `target_hash_unchanged`: True
- `ready_for_missing_detection`: **False**

## 阻断原因
- 3/7 region transforms are not VERIFIED

Input file fingerprints were redacted; historical checks were not rerun.
