# Workflow Registry

## 实现状态

`WorkflowRegistry` 读取 `config/workflows/*.json`，实现见 `runtime/workflow_registry.py:28`。当前已生成 11 个 JSON 定义：9 个 `AVAILABLE_OFFLINE`、2 个 `NOT_EXECUTABLE_CURRENTLY`。这些是源码合同，仍需 WP3 最终自检和 test_agent 端到端验证。

## 定义合同

每个 workflow 计划包含：

- `workflow_id`
- `workflow_type`
- `status`
- `supported_runtime_modes`
- `supported_products`
- `required_capabilities`
- `required_backend_types`
- `minimum_approval_level`
- `real_execution_required`
- `stages`
- `verification_requirements`
- `recovery_requirements`
- `expected_artifacts`
- `unavailable_reason`

数据类见 `runtime/contracts.py:65`。

## 当前源码清单（待验证）

1. `generic_autocad_redraw_offline`
2. `generic_autocad_clone_plan`
3. `pdf_intermediate_dwg_plan`
4. `image_dimension_parametric_redraw_plan`
5. `tianzheng_water_scan_plan`
6. `tianzheng_water_completion_plan`
7. `tianzheng_hvac_scan_plan`
8. `tianzheng_hvac_write_placeholder`
9. `offline_document_comparison`
10. `offline_capability_audit`
11. `nextgen_mock_job_simulation`

其中 `tianzheng_water_completion_plan` 与 `tianzheng_hvac_write_placeholder` 为 `NOT_EXECUTABLE_CURRENTLY` 且要求 Real execution；其余 9 个声明 `AVAILABLE_OFFLINE`。不得把 `AVAILABLE_OFFLINE` 解释为真实 CAD 可执行。

## 选择边界

- Runtime、Product、required capability 和 Backend 必须全部匹配。
- 不允许自动换 Backend。
- `NOT_EXECUTABLE_CURRENTLY`、Real requirement、L3/L4 都必须产生 blocked reasons。
- Registry 只读取 Skill 内 JSON 合同，不连接 CAD。
