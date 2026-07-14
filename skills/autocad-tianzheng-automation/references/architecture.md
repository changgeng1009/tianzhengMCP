# 统一架构

`User Request → Intent Router → Project Manifest → Runtime Selection → Safety/Approval Gate → Workflow → Product Adapter → Backend Adapter → Dry Run/Execution → Verification → Evidence Report`

接口位于 `runtime/contracts.py`：`ICadWorkflow`、`ICadProductAdapter`、`ICadBackend`、`ICapabilityRegistry`、`IDocumentGuard`、`IApprovalGate`、`IJobRunner`、`IVerificationProvider`。产品与后端分层，避免给排水规则泄漏到暖通。

本阶段执行边界为离线：不连接 CAD，不读取 DWG，不复用历史授权。现有项目相对目录 `mcp_nextgen/` 仅可被未来适配层引用，不覆盖；实验项目路径只能由 Manifest 显式配置，且本阶段文件访问守卫拒绝读取或迁移该实验项目。
