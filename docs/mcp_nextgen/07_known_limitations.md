# 已知限制

## 控制面与 Transport

- FastMCP 对象不会自动启动，当前无可运行 NextGen 服务入口。
- `TokenAuthenticator` 和 `LocalTransportPolicy` 尚未接到 FastMCP 入口；任何 listener 实现前必须关闭 `SEC-POST-002`。
- transport 仅含 policy、auth、codec 和进程内 replay guard；无 socket、HTTP、stdio runner、Named Pipe 或跨进程 replay。
- dispatcher 未接 Layer D、Mock runtime/backend。9 tools 中仅 3 个安全查询返回 Mock 结果，其余 6 个返回 `MOCK_BACKEND_NOT_IMPLEMENTED`。

## Job / Journal / Checkpoint / Safety

- single-use 审批没有持久、原子消费账本（`SEC-POST-001`）。
- 幂等存储没有 job_id 唯一占用，idempotency 落盘与 `JOB_CREATED` journal 之间存在 crash window（`SEC-POST-003`）。
- checkpoint 与 journal 尚未完成 state、head hash、document identity、plan hash、pending/failed/manual/approval 全字段互校验（`SEC-D-010`）。
- 多进程 writer lease/fencing 未实现；rollback 为 `NotImplementedError`。
- timeout/cancellation 只覆盖 Mock safe-boundary，不是实际保存/checkpoint 临界区证明。

## Mock、Legacy 与 Real

- Mock backend 只操作内存；save/reopen 是内存快照，scheduler 不等于 AutoCAD 主线程或 DocumentContextQueue。
- Legacy adapter 为 disabled contract，所有执行方法阻断。
- Real backend、AutoCAD .NET plugin、COM adapter、天正接口和真实 save/reopen 均未实现。
- `production_d1_allowed=false`；P4.1 本阶段未运行，旧 P4 能力未暴露为 NextGen tool。

## 测试边界

- DeepSeek 原交付：69/75，通过数不能用于声明 NextGen 通过。
- NextGen 定向复测：47/47，通过且未读取 DWG。
- 全量回归：1554/1561，7 failures、1 warning。一次 acceptance preflight 测试间接读取 3 个真实 DWG 的字节用于 SHA-256，违反本阶段 DWG 读取边界；没有修改或保存 DWG。
- `SEC-FINAL-019` 关闭前禁止再次直接运行全量 `pytest -q`。必须先隔离该测试，建立跨模块 helper 调用预检，并用 `tmp_path`/monkeypatch 替代真实 DWG。
- 另有 5 个 acceptance 测试因 Windows GBK 解码 UTF-8 源文件失败；需单独最小修复。
- 正式 P4.1 checkpoint 仍不是原子写，三计数字段和 automatic dependency 尚未接入冻结代码；NextGen 回归不等于正式 P4.1 修复。

## 协议与功能缺口

- 当前仅支持协议 `1.0.0`。
- resources/prompts 未实现。
- progress/job/runtime 尚未端到端接入控制面。
- 真实插件、Real backend、Legacy enablement、生产审批和 Production D1 均延期。

## 非目标

本阶段不处理天正管道显示环境差异，不重新运行 P4.1，不修改候选图、Reference 或 Target 原图。
