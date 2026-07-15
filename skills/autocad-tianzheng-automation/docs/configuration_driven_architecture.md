# 配置驱动架构

## 当前状态

本文记录 CAD-CONFIG-S2 的实现草稿状态，不代表阶段验收完成。

| 层 | 当前证据 | 状态 |
|---|---|---|
| Manifest、版本、默认值、合并、路径 | `config/` 与两个 Manifest Schema | WP1 已完成离线自检，待正式测试 |
| Product/Backend 合同 | `adapters/registry.py` 与 capability matrices | WP2 已完成离线自检，待正式测试 |
| Runtime/Workflow/Plan/Simulation | `runtime/routing.py`、`workflow_registry.py`、`execution_plan.py`、`simulation.py` | 源码已出现，WP3 最终验证待回填 |
| Workflow 定义 | `config/workflows/*.json` | 11 个源码定义已生成，待 WP3/test_agent 验证 |
| Templates | `templates/` | 10 个 Manifest + catalog/matrix 已生成，待 Schema/plan 测试 |
| 新 CLI | `scripts/skill_cli.py` | 尚未接入 S2 分组命令 |

## 数据流

计划采用以下纯离线链路：

```text
Project Manifest
→ ManifestLoader
→ Schema Validation
→ ManifestMigrator
→ DefaultResolver / ConfigMerger
→ ManifestPathResolver
→ RuntimeRouter
→ ProductCapabilityResolver
→ BackendSelector
→ WorkflowRegistry
→ ExecutionPlanBuilder
→ Plan Hash
→ Offline / NextGen Mock Simulation
→ Evidence
```

WP1 已实现到 `ManifestPathResolver`；WP2 提供静态 Product/Backend 真值；WP3 已生成后半链路源码、11 个 workflow 和 10 个模板，但尚未完成正式测试。实现入口见 `config/manifest_loader.py:13`、`config/default_registry.py:65`、`runtime/routing.py:80`、`runtime/execution_plan.py:84`。

## 设计边界

- 所有配置解析默认离线，不读取 CAD 文档内容。
- Manifest 只声明意图，不构成审批或 Backend 能力来源。
- Registry 是 Product/Backend 能力真值，Manifest 不得覆盖其 availability。
- 输出 Plan 的 `executable` 只表示离线合同判断；当前不存在真实 CAD 执行后端。
- `offline` 与 `nextgen_mock` 不能被描述为真实 CAD 完成结果。
- `production_allowed=false`、`production_d1_allowed=false` 保持不变。

## 兼容策略

旧扁平 1.0/1.0.0 Manifest 先验证再迁移到 canonical 1.1.0。旧 `select_runtime`、`build_offline_plan` 与 CLI 应通过 wrapper 兼容，不应直接删除。当前 CLI 尚未完成该接入，不能据本文推断 CLI 已兼容。
