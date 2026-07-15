# 配置合并优先级

## 六层顺序

从低到高：

1. `system_default`
2. `skill_default`
3. `product_default`
4. `workflow_default`
5. `project_manifest`
6. `run_override`

`DefaultResolver.resolve()` 实现该顺序并返回 `source_trace` 与 `merge_trace`，见 `config/default_registry.py:65`。普通字段按高优先级覆盖；安全字段不遵循“高优先级必胜”。

## 安全合并

| 字段类别 | 策略 |
|---|---|
| `production_allowed`、D1、real access、外部/UNC 权限 | AND；false 不能被 true 放宽 |
| source write 禁止、sandbox、fail-closed、dry-run、simulate-only、视觉/工程复核、manual save | OR；true 不能关闭 |
| `requested_level` | L0/L1/L2 仅声明离线计划；L3/L4 直接阻断 |
| denylist、protected regions、prohibited products、required capabilities | 确定性并集 |
| operation allowlist | fail-closed 交集 |
| backend capability/availability 字段 | 禁止由配置出现 |
| approval | 只允许 project manifest 声明；不得从 defaults/workflow/run override 继承 |

实现见 `config/merge.py:69` 与 `config/merge.py:116`。

## Trace

`DefaultSourceTrace` 记录字段、值、来源、动作和原因。安全强制后的来源标为 `security_forced`。发生降级时抛出结构化错误，不返回看似成功的宽松结果。

## 当前限制

- Workflow defaults 尚无机器可读定义，因此当前第三、第四层中的 workflow 部分尚未形成完整端到端验证。
- Allowlist 从系统空 trust root 开始时保持空；未来需要由权威 Workflow Registry 提供基础 allowlist，Manifest 只能继续收紧。
- 合并 API 已通过 WP1 轻量自检，但未完成正式 pytest 矩阵。

