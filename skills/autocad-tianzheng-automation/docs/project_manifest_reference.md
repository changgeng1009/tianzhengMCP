# Project Manifest 参考

## 版本与格式

- 主格式：UTF-8 JSON。
- Canonical version：`1.1.0`。
- Schema：`schemas/project_manifest.schema.json`。
- 旧版 Schema：`schemas/project_manifest_v1_0.schema.json`。
- 未知顶层字段被拒绝；扩展只能放入 `extensions`。

版本常量与策略见 `config/versioning.py:13`、`config/versioning.py:29`。

## Canonical 顶层结构

| 字段 | 用途 | 关键边界 |
|---|---|---|
| `project` | 项目标识、名称、类型、标签 | 不放姓名、学号或真实课程数据 |
| `task` | 任务类型、请求操作、输出 | 只是声明，不执行命令 |
| `runtime` | 5 个 runtime mode 和 fail-closed 策略 | `offline_only` 默认 true |
| `documents` | reference/target/auxiliary 声明 | 身份是声明，不是已验证 |
| `paths` | 路径策略 | 默认 project-relative，外部和 UNC 禁止 |
| `product` | 产品请求、能力要求、禁用产品 | 不能覆盖 Adapter 状态 |
| `backend` | 首选、fallback、Mock 与 Real 请求 | 不能覆盖 Registry availability |
| `workflow` | workflow ID、阶段策略、dry-run | Registry 定义尚待生成 |
| `safety` | 等级、生产、保护区、操作名单 | 只允许收紧 |
| `approval` | 审批需求和引用 | 不是 token，不代表 verified |
| `verification` | 实体、视觉、拓扑、工程、重开复核 | 视觉和工程复核固定为 true |
| `recovery` | checkpoint、journal、resume、manual save | 不执行真实恢复写入 |
| `output` | 计划、证据和报告路径 | 不得与 source 冲突 |
| `metadata` | 来源和备注 | 时间可为 null，避免随机性 |
| `extensions` | 显式扩展 | 唯一允许未知扩展的区域 |

## 文档身份

`identity_policy` 支持 `declared_only`、`synthetic_verified`、`require_runtime_verification`、`unavailable`。本阶段不自动读取或哈希 CAD 文件，因此真实文档只能保持 `DECLARED`、`RUNTIME_VERIFICATION_REQUIRED` 或 `UNAVAILABLE`，不得输出 `VERIFIED`。

## Backend ID

Canonical ID 使用下划线，例如 `original_redraw_adapter`、`nextgen_mock`。WP2 Registry 接受旧连字符 ID 作为输入 alias，但输出统一为 canonical ID；证据见 `adapters/registry.py:300`。

## 安全值

Schema 强制：

```json
{
  "production_allowed": false,
  "production_d1_allowed": false,
  "real_cad_access_allowed": false,
  "source_write_forbidden": true,
  "sandbox_required": true,
  "fail_closed": true
}
```

完整字段和枚举以 Schema 为准。当前模板尚未生成，不要从旧 `examples/*.json` 复制后直接声称其为 canonical 1.1.0。

