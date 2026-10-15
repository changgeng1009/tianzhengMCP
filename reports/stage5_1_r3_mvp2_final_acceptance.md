> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

# Stage 5.1-R3 MVP2 最终验收报告

## 最终状态

**FAILED_PERSISTENCE_QA**

- run_id: `stage5_1_r3_20260711_153559`
- MVP2 completed: NO
- MVP3 allowed: NO
- Stage 6 run created: NO
- Production D1 allowed: NO

## 核心 331

- ordinary CAD: 16/16 创建并持久化
- core TDb: 331/331 创建并持久化
- work packages: 103/103
- Valve 保存重开关系包: 88/88
- existing modified/deleted: 0/0
- unexpected/duplicate: 0/0
- 保存、关闭、重开: PASS

## Dimension2

- 原生克隆及独立保存重开: 6/6
- 人工视觉/功能验收: 6/6
- manual_dimension2_acceptance: true
- dimension2_automated_observability: false
- full_automated_semantic_verification: false
- 只读桥: 未使用
- contact sheet: `D:\ExampleWorkspace\天正\artifacts\stage5_1_r3\stage5_1_r3_20260711_153559\previews\dimension2_manual_acceptance_contact_sheet.png`

## 最终 16 + 337 重建

- 最终 DWG: `D:\ExampleWorkspace\天正\artifacts\stage5_1_r3\stage5_1_r3_20260711_153559\copies\target_mvp2_final_reconstruction.dwg`
- 当前已持久化: 16 ordinary + 331 core TDb
- 最终图 Dimension2 持久化: 0/6
- 失败原因: 在已验证核心文件中追加首个 `TDbDimension2` 后，天正返回 `保存文档时出错`。
- 批量保存和逐项保存重开两条路径均复现同一错误。
- 失败编辑通过 `Close(False)` 丢弃，未留下部分 Dimension2 写入。

## QA 与停止门

- 核心类型/属性/拓扑 QA: PASS
- 全量 337 QA: NOT RUN
- 收敛: NOT RUN
- 幂等性: NOT RUN
- 制图表达变体: NOT CREATED
- Stage 6: NOT CREATED

## Source Safety

- reference SHA256 unchanged: `true`
- target SHA256 unchanged: `true`
- source opened/saved/modified: `false/false/false`
- SendCommand/LISP/NETLOAD/external DLL/fallback: `false`
- new AutoCAD instance: `false`
- production_d1_allowed: `false`

## 测试

- targeted: 16 passed
- acceptance group: 207 passed
- full suite: 1248 passed, 1 PyPDF2 deprecation warning

## 下一门槛

必须解决 `TDbDimension2` 与 331 核心 TDb 共存时的天正文档保存错误，并重新完成最终保存重开、收敛和幂等性；此前 MVP2 与 Stage 6 保持阻断。
