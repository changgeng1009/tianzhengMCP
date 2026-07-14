# Agent Report

## Agent Name

cad_bridge_agent

## Assigned Task

- Phase: `MCP-UPGRADE-HANDOFF`
- Task ID: `MUH-FIX-MOCK-009`
- 目标：最小修复 Mock `DocumentIdentity.created_at` 不确定问题，并允许显式注入时钟。

## Files Read

- `agent_inbox/cad_bridge_agent.md`
- `mcp_nextgen/backends/models.py`
- `mcp_nextgen/backends/mock.py`

## Files Modified

- `mcp_nextgen/backends/models.py`
- `mcp_nextgen/backends/mock.py`
- `agent_outbox/cad_bridge_agent_report.md`

未修改 tests、runtime、Legacy adapter、旧代码或其他目录。

## Work Completed

- 新增默认 Mock 时间常量：`2000-01-01T00:00:00+00:00`。
- `MockCadBackend` 新增可选 `clock: Callable[[], str]` 构造参数。
- 未提供 `clock` 时，所有等价新建 Mock backend 使用相同默认创建时间。
- 显式提供 `clock` 时，文档创建时调用一次并冻结到 `_MockDocument.created_at`。
- `_MockDocument.identity()` 重复生成 identity 时沿用冻结时间，不使用协议模型的实时时钟默认值。
- `mock_document_identity()` 改为必须显式接收 `created_at`，避免后续调用意外回退到实时微秒值。
- 未改变 Real/Legacy 语义；未修改 document state SHA-256 计算。

## Deterministic Clock Strategy

```text
默认：MockCadBackend(clock=None)
  -> 固定 2000-01-01T00:00:00+00:00

可注入：MockCadBackend(clock=lambda: "2030-01-02T03:04:05+00:00")
  -> 创建文档时冻结该时间
```

该策略保证两个等价默认 Mock backend 的 `DocumentIdentity` 完全相等，同时允许调用方在时间相关场景中提供确定性测试时钟。

## Tests Run

按约束未运行 pytest，仅执行 compile 与内存自检：

```powershell
python -m compileall -q mcp_nextgen\backends
```

结果：PASS。

内存自检验证：

- 两个默认 `MockCadBackend().list_documents()` 完全相等；
- 默认 `created_at` 为固定值；
- 注入 clock 后 `created_at` 等于注入值。

结果：`MOCK_CLOCK_SELF_CHECK_OK`。

## Test Result

- compile：PASS
- 默认 Mock identity 确定性：PASS
- 显式 clock 注入：PASS
- pytest：NOT RUN（由 test_agent 验证）

## Safety Check

* Connected to AutoCAD: NO
* Connected to Tianzheng: NO
* Imported or used COM: NO
* Opened DWG: NO
* Used CopyObjects: NO
* Used SendCommand: NO
* Started P4.1: NO
* Saved or modified DWG: NO
* Production D1 attempted: NO

## Risks Found

- 注入 clock 的格式目前只要求非空字符串；协议层未对 `DocumentIdentity.created_at` 做 ISO-8601 强校验。该项不影响当前确定性修复。

## Remaining Work

- 由 test_agent 运行 `tests/nextgen/test_nextgen_handoff.py::test_mock_backend_is_deterministic`。

## Recommendation

- 接受该最小修复；保持 Mock 默认固定时钟，真实系统时间只允许通过显式注入进入 Mock。
