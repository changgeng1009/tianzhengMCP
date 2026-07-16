# 统一架构

`User Request → Intent Router → Project Manifest → Product Router → Execution Runtime Router → Safety/Approval Gate → Workflow Registry → Product Adapter → Backend Interface → Offline/Mock Result → Verification → Evidence Report`

S3 的关键分层如下：

1. **ProductProfile**：`generic_autocad`、`tianzheng_water`、`tianzheng_hvac`、`offline_analysis`，说明产品平台、专业领域、能力、所需 Backend 和支持状态。
2. **Execution Runtime**：`offline`、`mock`、`com`、`objectarx`，说明计划在哪种环境运行。当前仅 `offline`/`mock` 可选择；`com`/`objectarx` 为 `NOT_AVAILABLE`。
3. **Workflow Registry**：把工作流绑定到产品，而不是把产品名称编码为 Backend 或运行时。历史 `runtime_mode` 仅作输入兼容映射。
4. **ProductAdapter**：对每类产品提供 `inspect()`、`plan()`、`validate()`、`execute()` 的纯数据合同，避免给排水规则泄漏到暖通。
5. **Backend Interface**：`offline`、`original_redraw_adapter` 和 `nextgen_mock` 仅提供离线/Mock 能力；所有 Real、COM、ObjectARX 与天正 Real 后端均未实现。

核心接口位于 `runtime/contracts.py`：`ICadWorkflow`、`ICadProductAdapter`、`ICadBackend`、`ICapabilityRegistry`、`IDocumentGuard`、`IApprovalGate`、`IJobRunner`、`IVerificationProvider`。产品与后端分层，审批与文档保护独立于两者。

本阶段执行边界为离线：不连接 CAD，不读取 DWG，不复用历史授权。现有项目相对目录 `mcp_nextgen/` 只提供 Mock-only 安全基线，不覆盖；实验项目路径只能由 Manifest 显式配置，且文件访问守卫拒绝读取或迁移该实验项目。
