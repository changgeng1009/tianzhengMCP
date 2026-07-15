# 项目模板指南（源码已生成，待验证）

## 当前状态

当前 `templates/` 已包含 10 个 `project_manifest.json`、`template_catalog.json` 和 `template_capability_matrix.json`。Catalog 声明 8 个离线/Mock 计划模板和 2 个 blocked 模板；Schema、plan build、determinism 与 CLI 创建流程仍待 test_agent，不能标为已验证。

## 计划模板

1. `plain_autocad_redraw`
2. `plain_autocad_clone`
3. `tianzheng_water_scan`
4. `tianzheng_water_completion`
5. `tianzheng_hvac_scan`
6. `tianzheng_hvac_write_placeholder`
7. `pdf_to_dwg_plan`
8. `image_parametric_redraw`
9. `offline_analysis`
10. `nextgen_mock_simulation`

当前源码数量为 10。`tianzheng_water_completion` 与 `tianzheng_hvac_write_placeholder` 的预期状态为 `BLOCKED`；`nextgen_mock_simulation` 仅为 Mock baseline。

## 每个模板必须满足

- 使用 canonical `schema_version=1.1.0`。
- 只使用虚构 project/task/document identity。
- 使用 project-relative 路径，不含姓名、学号、真实哈希或绝对课程路径。
- `production_allowed=false`、`production_d1_allowed=false`、`real_cad_access_allowed=false`。
- Backend 仅为 `offline` 或 `nextgen_mock`。
- 不嵌入 approval token。
- 通过 canonical Schema。
- 能生成离线计划；真实写入模板必须生成 blocked plan。

## 待回填

- Schema、plan build、determinism 和安全阻断测试结果。
- `templates list/create` 的安装态 CLI 示例。
