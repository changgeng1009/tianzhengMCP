---
name: autocad-tianzheng-automation
description: 统一、安全地编排普通 AutoCAD、天正给排水、天正暖通与离线 CAD 分析任务。用于重画参考图、比较或检查 DWG、依据 PDF/图片制定补图计划、天正给排水补全、天正暖通只读检查、Sandbox 候选图规划、视觉复核以及 checkpoint 恢复；支持 plain_autocad、tianzheng_water、tianzheng_hvac、auto_detect 和 offline_analysis，并在产品、文档或实例不明确时 fail-closed。
---

# AutoCAD & Tianzheng Automation

## 核心边界

先生成并验证项目 Manifest，再选择运行模式、工作流、产品适配器和后端。默认使用 `offline` 后端及 `production_allowed=false`。没有绑定当前 job、文档身份、哈希、计划哈希和单次授权时，不得写 DWG。

不得根据 DWG 文件名猜产品，不得随意选择 `ActiveDocument`，不得将几何重合等同于工程语义完整。模式、产品或文档身份冲突时立即停止并返回标准错误码。

本 Skill 已提供 `NextGenMcpMockBackend=IMPLEMENTED_BASELINE` 的离线/Mock 门面，`NextGenControlPlane=PARTIALLY_IMPLEMENTED`；两者都不代表真实 CAD 能力。NextGen 真实写入后端仍为 `NOT_IMPLEMENTED`，`NextGenMcpBackendPlaceholder` 只描述该未实现边界。天正暖通写入保持 `INTERFACE_ONLY`。

`SEC-FINAL-019` 已由当前安全基线 `current_safe_baseline_id=20260714T220937+0800` 关闭，基线 SHA256 为 `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9`。该基线因 `intentional AGENTS.md update` 从父基线 `20260714T193554+0800_s2_1` 重新冻结；默认受守卫测试的 `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`，真实 DWG 成功读写、CAD 进程、COM 与天正连接均为 0。项目相对证据目录为 `artifacts/cad_safe_test_baseline/20260714T220937+0800`，明确路径为 `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`。从项目根复核：

```powershell
python -m scripts.verify_safe_test_baseline --baseline "artifacts/cad_safe_test_baseline/20260714T220937+0800" --project-root "."
```

该关闭只证明冻结的默认 pytest 基线零访问，不启用任何真实后端，也不放宽 DWG、产品或审批边界。

## 标准流程

1. 读取或创建符合 [schemas/project_manifest.schema.json](schemas/project_manifest.schema.json) 的 Manifest。
2. 运行 `python -m scripts.skill_cli validate-manifest <manifest>`。
3. 按“用户明确指定 → Manifest → 明确上下文 → 安全只读检测”选择模式。无法唯一确定则停止询问。
4. 从 [references/runtime_modes.md](references/runtime_modes.md) 选择产品适配器，从 [references/backend_model.md](references/backend_model.md) 选择后端。
5. 按 [references/safety_model.md](references/safety_model.md) 评估 L0–L4。L4 必须取得单独、明确、单次授权。
6. 读取对应 [workflows](workflows/00_select_runtime.md)；先 dry-run，后执行允许的步骤。
7. 分别报告几何、对象类型、属性、显示环境、原生拓扑、工程语义完整性和视觉复核状态。
8. 输出证据清单、停止条件、人工复核点和已知限制。

## 离线入口

```powershell
python -m scripts.skill_cli inspect-manifest <manifest>
python -m scripts.skill_cli validate-manifest <manifest>
python -m scripts.skill_cli select-runtime <manifest>
python -m scripts.skill_cli build-plan <manifest> --dry-run
python -m scripts.skill_cli capabilities --mode plain_autocad
```

这些入口不连接 AutoCAD，不打开或读取 DWG。显式请求未来后端也必须先通过审批门；当前 `nextgen-mcp` 会安全拒绝真实执行。

## 模式与适配器

- `plain_autocad`：只使用通用对象和工作流，绝不调用天正。
- `tianzheng_water`：仅在确认天正给排水产品实例后启用。
- `tianzheng_hvac`：当前提供检测、注册表和只读扫描接口；写入为 `INTERFACE_ONLY`。
- `auto_detect`：证据唯一时选择，否则返回冲突。
- `offline_analysis`：只处理 Manifest、JSON、报告、图片/PDF计划、测试和代码。

兼容原始重绘 Skill 时使用 `OriginalRedrawSkillAdapter`，只映射任务和隔离必要脚本，不修改原 Skill，也不绕过新安全门。调用当前项目执行器时使用 Legacy Backend 合约；不要大规模改写原执行器。

## 必须停止

- `RUNTIME_MODE_CONFLICT`：模式证据冲突。
- `PRODUCT_INSTANCE_CONFLICT`：目标产品与已确认实例冲突。
- `DOCUMENT_IDENTITY_AMBIGUOUS`：当前文档身份无法唯一验证。
- 请求写源 DWG、授权过期/复用、计划哈希或文档哈希变化。
- `ActiveDocument` 与批准身份不一致，或出现计划外/重复对象。
- 无法验证保存持久化时，输出 `MANUAL_SAVE_REQUIRED`，不得声称完成。

详细架构、能力等级、产品边界、升级路线和限制见 [references](references/architecture.md)。
