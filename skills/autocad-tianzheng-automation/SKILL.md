---
name: autocad-tianzheng-automation
description: 统一、安全地编排普通 AutoCAD、天正给排水、天正暖通与离线 CAD 分析任务。用于重画参考图、比较或检查 DWG、依据 PDF/图片制定补图计划、天正给排水补全、天正暖通只读检查、Sandbox 候选图规划、视觉复核以及 checkpoint 恢复；支持 plain_autocad、tianzheng_water、tianzheng_hvac、auto_detect 和 offline_analysis，并在产品、文档或实例不明确时 fail-closed。
---

# AutoCAD & Tianzheng Automation

## 核心边界

先生成并验证项目 Manifest，再选择产品、执行运行时、工作流、产品适配器和后端。产品回答“要处理哪类 CAD/专业任务”，`execution_runtime` 回答“计划在哪种受控环境中运行”；二者不是同一字段，也不得相互提升能力。默认使用 `offline` 后端及 `production_allowed=false`。没有绑定当前 job、文档身份、哈希、计划哈希和单次授权时，不得写 DWG。

不得根据 DWG 文件名猜产品，不得随意选择 `ActiveDocument`，不得将几何重合等同于工程语义完整。模式、产品或文档身份冲突时立即停止并返回标准错误码。

本 Skill 已提供 `NextGenMcpMockBackend=IMPLEMENTED_BASELINE` 的离线/Mock 门面，`NextGenControlPlane=PARTIALLY_IMPLEMENTED`；两者都不代表真实 CAD 能力。NextGen 真实写入后端仍为 `NOT_IMPLEMENTED`，`NextGenMcpBackendPlaceholder` 只描述该未实现边界。天正暖通写入保持 `INTERFACE_ONLY`。

`SEC-FINAL-019` 已由当前安全基线 `current_safe_baseline_id=CAD-SAFE-20260714T220937+0800` 关闭，权威最终 SHA256 为 `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`。该基线因 `intentional AGENTS.md update` 从父基线 `20260714T193554+0800_s2_1` 重新冻结；默认受守卫测试的 `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`，真实 DWG 成功读写、CAD 进程、COM 与天正连接均为 0。`13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9` 仅是 freeze-time provenance SHA，不是当前 S2 预检或验收应使用的基线 SHA。项目相对证据目录为 `artifacts/cad_safe_test_baseline/20260714T220937+0800`，明确路径为 `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`。从项目根复核：

```powershell
python -m scripts.verify_safe_test_baseline --baseline "artifacts/cad_safe_test_baseline/20260714T220937+0800" --project-root "."
```

该关闭只证明冻结的默认 pytest 基线零访问，不启用任何真实后端，也不放宽 DWG、产品或审批边界。

## 产品、运行时与后端

S3 统一产品档案使用 `generic_autocad`、`tianzheng_water`、`tianzheng_hvac` 和 `offline_analysis`。可声明的执行运行时为 `offline`、`mock`、`com`、`objectarx`；当前只有前两者可用于离线/Mock 计划。`com` 与 `objectarx` 都是未来接口，当前为 `NOT_AVAILABLE`，不能因 Manifest 声明而启用。

- `generic_autocad`：`OFFLINE_PLANNING_IMPLEMENTED`；普通 CAD 检查、参考分析、重绘和比对仅生成离线计划。
- `tianzheng_water`：`OFFLINE_PLANNING_IMPLEMENTED`；给排水扫描、缺失检测和补全仅生成离线计划，天正真实后端未实现。
- `tianzheng_hvac`：`INTERFACE_ONLY`；对象/扫描/写入合同不等于天正暖通真实能力。若提供通用几何回退，其状态独立于天正对象、样式、拓扑和工程语义。
- `offline_analysis`：`IMPLEMENTED`；只处理 JSON、代码、报告、Schema、图片/PDF 的离线规划和 Mock 证据，不读取真实 CAD 文件。

`OriginalRedrawSkillAdapter` 仅把原始 GitHub Skill 的任务映射为安全的离线规划合同；它不调用原 Skill 的真实执行入口。`NextGenMcpMockBackend=IMPLEMENTED_BASELINE`，`NextGenControlPlane=PARTIALLY_IMPLEMENTED`，均不代表真实 CAD。`LegacyAdapter=DISABLED_CONTRACT_ONLY`；`NextGenRealBackend`、`Legacy COM`、`AutoCAD .NET / ObjectARX`、`Tianzheng Water/HVAC Real` 均为 `NOT_IMPLEMENTED`。

## 标准流程

1. 读取或创建符合 [schemas/project_manifest.schema.json](schemas/project_manifest.schema.json) 的 Manifest。
2. 运行 `python -m scripts.skill_cli validate-manifest <manifest>`。
3. 按“用户明确指定 → Manifest → 明确上下文 → 安全只读检测”选择兼容运行模式；无法唯一确定则停止询问。
4. 将运行模式映射为独立的 ProductProfile 和 `execution_runtime`；验证二者与工作流、适配器和后端的静态兼容性。
5. 从 [references/product_adapter_model.md](references/product_adapter_model.md) 选择产品适配器，从 [references/backend_model.md](references/backend_model.md) 选择后端。
6. 按 [references/safety_model.md](references/safety_model.md) 评估 L0–L4。L4 必须取得单独、明确、单次授权。
7. 读取对应 [workflows](workflows/00_select_runtime.md)；先 dry-run，后执行允许的步骤。
8. 分别报告几何、对象类型、属性、显示环境、原生拓扑、工程语义完整性和视觉复核状态。
9. 输出证据清单、停止条件、人工复核点和已知限制。

## 离线入口

```powershell
python -m scripts.skill_cli inspect-manifest <manifest>
python -m scripts.skill_cli validate-manifest <manifest>
python -m scripts.skill_cli select-runtime <manifest>
python -m scripts.skill_cli build-plan <manifest> --dry-run
python -m scripts.skill_cli capabilities --mode plain_autocad
```

这些入口不连接 AutoCAD，不打开或读取 DWG。显式请求未来后端也必须先通过审批门；当前 `nextgen-mcp` 会安全拒绝真实执行。

## S2 配置驱动离线 CLI

S2 CLI 仅处理 JSON Manifest、确定性 Plan 和 Mock 模拟；它不授予审批、不读取 CAD，也不改变 Registry 的后端真值。可用分组入口为：

```powershell
python -m scripts.skill_cli manifest validate|normalize|explain|migrate <manifest>
python -m scripts.skill_cli config resolve <manifest>
python -m scripts.skill_cli runtime select <manifest>
python -m scripts.skill_cli product select <manifest>
python -m scripts.skill_cli backend select <manifest>
python -m scripts.skill_cli workflow select <manifest>
python -m scripts.skill_cli plan build <manifest>
python -m scripts.skill_cli plan verify|hash <plan.json>
python -m scripts.skill_cli simulate <manifest> --backend offline|nextgen_mock
python -m scripts.skill_cli templates list
python -m scripts.skill_cli templates create <template_id> --output <relative-directory>
```

Manifest 只能声明意图、默认值和审批引用；它不能创建或继承有效审批，不能将引用视为已验证审批，也不能把 `production_allowed`、`production_d1_allowed`、`real_cad_access_allowed`、Backend availability/support level/execution capability 或 L3/L4 权限提升为可用。发生这类配置覆盖时必须 fail-closed；`offline`、`nextgen_mock` 和 `original_redraw_adapter` 均不代表真实 CAD 执行。

## 兼容运行模式与产品适配器（模式与适配器）

- `plain_autocad`：只使用通用对象和工作流，绝不调用天正。
- `tianzheng_water`：仅在确认天正给排水产品实例后启用。
- `tianzheng_hvac`：当前提供检测、注册表和只读扫描接口；写入为 `INTERFACE_ONLY`。
- `auto_detect`：证据唯一时选择，否则返回冲突。
- `offline_analysis`：只处理 Manifest、JSON、报告、图片/PDF计划、测试和代码。

兼容原始重绘 Skill 时使用 `OriginalRedrawSkillAdapter`，只映射任务和隔离必要脚本，不修改原 Skill，也不绕过新安全门。`ProductAdapter` 的 `inspect()`、`plan()`、`validate()` 与 `execute()` 均返回可审计的纯数据合同；当前 `execute()` 只能拒绝真实执行或产生 Mock/离线结果，不能连接 CAD。Legacy Backend 仅保留禁用合同，不得作为执行器。

## 必须停止

- `RUNTIME_MODE_CONFLICT`：模式证据冲突。
- `PRODUCT_INSTANCE_CONFLICT`：目标产品与已确认实例冲突。
- `DOCUMENT_IDENTITY_AMBIGUOUS`：当前文档身份无法唯一验证。
- 请求写源 DWG、授权过期/复用、计划哈希或文档哈希变化。
- `ActiveDocument` 与批准身份不一致，或出现计划外/重复对象。
- 无法验证保存持久化时，输出 `MANUAL_SAVE_REQUIRED`，不得声称完成。

详细架构、能力等级、产品边界、升级路线和限制见 [references](references/architecture.md)。
