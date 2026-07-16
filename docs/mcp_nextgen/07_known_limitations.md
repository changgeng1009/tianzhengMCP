# 已知限制

## 控制面与 Transport

- FastMCP 对象不会自动启动；当前没有可运行 NextGen listener 或任何 network/stdio/HTTP/TCP/Named Pipe 服务入口。
- `TokenAuthenticator` 和 `LocalTransportPolicy` 尚未接到 FastMCP 入口；任何 listener 实现前必须关闭 `SEC-POST-002`。
- transport 仅含 policy、auth、codec 和进程内 replay guard；无 socket、HTTP、stdio runner、Named Pipe 或跨进程 replay。
- S4 的 13 tools / 3 resources / 2 prompts 只接入 `ControlPlaneService` 和确定性 Mock job。实体查询与 clone/transform 仍为 `NOT_IMPLEMENTED`；没有 CAD runtime 或真实 backend。

## Job / Journal / Checkpoint / Safety

- single-use 审批绑定在 Mock job 内；跨进程持久、原子消费账本仍未实现（`SEC-POST-001`）。
- 幂等存储没有 job_id 唯一占用，idempotency 落盘与 `JOB_CREATED` journal 之间存在 crash window（`SEC-POST-003`）。
- checkpoint 与 journal 已用于 Mock job 的恢复与 hash anchor 核验；state、head hash、document identity、plan hash、pending/failed/manual/approval 的全字段跨组件互校验仍未完成（`SEC-D-010`）。
- 多进程 writer lease/fencing 未实现；rollback 为 `NotImplementedError`。
- timeout/cancellation 只覆盖 Mock safe-boundary，不是实际保存/checkpoint 临界区证明。

## Mock、Legacy 与 Real

- Mock backend 只操作内存；Mock job 的 journal/checkpoint 落盘只是控制面证据，不能等同于 DWG save/reopen 或 CAD 主线程/DocumentContextQueue。
- Legacy adapter 为 disabled contract，所有执行方法阻断。
- Real backend、AutoCAD .NET plugin、COM adapter、天正接口和真实 save/reopen 均未实现。
- `production_d1_allowed=false`；P4.1 本阶段未运行，旧 P4 能力未暴露为 NextGen tool。

## 测试边界

- DeepSeek 原交付结果不能用于声明当前 NextGen 通过；S4 必须以本仓库受文件访问守卫保护的定向测试和默认安全回归为准。
- `SEC-FINAL-019` 的关闭结论仅适用于受守卫默认 pytest 基线；任何 real DWG/external integration/CAD/COM 测试都必须显式隔离。
- Mock job 的 checkpoint/resume、三计数和 automatic dependency 不等于正式 P4.1 修复，也不能作为真实保存、重开或工程语义验证的证据。

## 协议与功能缺口

- 当前仅支持协议 `1.0.0`。
- resources/prompts 已作为发现和安全提示实现，但不具备外部传输、订阅或真实执行能力。
- progress/job/runtime 只端到端接入 Mock-only 控制面；真实 CAD runtime 仍未接入。
- 真实插件、Real backend、Legacy enablement、生产审批和 Production D1 均延期。

## 非目标

本阶段不处理天正管道显示环境差异，不重新运行 P4.1，不修改候选图、Reference 或 Target 原图。
