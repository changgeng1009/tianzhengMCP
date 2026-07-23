# S5 Real AutoCAD COM Backend MVP 架构

## 定位

S5 引入的目标组件为 `RealAutoCadComBackend`。它只允许在显式 S5 外部集成测试中操作本阶段新建、受登记的合成 Sandbox DWG；能力等级只能是 `REAL_AUTOCAD_COM_MVP_SANDBOX_ONLY`。它不是完整 Real Backend，不是生产后端，也不提供天正能力。

S5 已完成人工验收的真实 synthetic 集成证据、审批和文档身份验证；`real_autocad_com` 可声明为 `AVAILABLE_SANDBOX_MVP`。默认 Skill 路由仍为 `offline`，S4 的 `nextgen_mock` 仍是独立的 Mock-only 后端。

## 依赖方向

```text
S4 MCP Control Plane
  -> Execution Plan / Approval Gate
  -> RealAutoCadComBackend
  -> AutoCadComTransport
  -> AutoCadSessionManager / AutoCadDocumentManager
  -> AutoCadEntityGateway / AutoCadSaveReopenVerifier
  -> AutoCAD COM
```

业务层只依赖 Backend Protocol 和版本化 DTO；只有 COM transport 层可以导入 `win32com`。控制面、产品适配器、工作流和 DTO 不得直接调用 COM，也不得以 `ActiveDocument` 作为未验证回退。

## MVP 合同

S5 最小合同限定为以下能力：

- `capabilities()`、`connect()`、`disconnect()`；
- `create_synthetic_document()`、`open_owned_document()`、`verify_document_identity()`；
- `create_line()`、`create_circle()`、`create_polyline()`；
- `query_entities()`、`inspect_entity()`；
- `save_document()`、`close_document()`、`reopen_document()`、`verify_persistence()`；
- `check_idempotency()`。

不实现任意用户文件打开、删除、通用变换、Block、Layout、Xref、Dimension、Text、天正对象或批量生产写入。

## 受支持实体

实体 DTO 必须包含 `operation_key`、几何、图层、文档身份和验证状态。允许的实体只有：

| 实体 | 合成约束 | 支持状态 |
|---|---|---|
| Line | 有限坐标，起终点不同 | S5 Sandbox MVP |
| Circle | 有限坐标，半径大于 0 | S5 Sandbox MVP |
| Polyline | 有限坐标，满足最少有效顶点 | S5 Sandbox MVP |

所有数值必须拒绝 `NaN`、`Infinity` 与超出合成坐标边界的值。实体仅可写入 `CADAGENT_S5_MVP` 专用图层，且固定测试几何不得从任何真实图纸派生。

## 后端状态真值

在 S5 验收通过后，能力矩阵只能表达下列范围：

```text
real_autocad_com = AVAILABLE_SANDBOX_MVP
generic_autocad_real_write = LIMITED_SYNTHETIC_GEOMETRY_ONLY
user_dwg_access = FORBIDDEN
production_write = FORBIDDEN
tianzheng_support = NOT_IMPLEMENTED
transactional_rollback = NOT_AVAILABLE
```

`LegacyAdapter` 继续是 `DISABLED_CONTRACT_ONLY`；`NextGenRealBackend`、ObjectARX、AutoCAD .NET 插件与天正 Real Backend 继续为 `NOT_IMPLEMENTED`。任何未满足验收的运行均不得提升以上状态。

## S5 启动架构修订（静态/Mock 已验证）

Real COM 仅允许 `COM_ACTIVATION`：受控宿主在锁内暂时设置安全外部运行上下文后调用 `DispatchEx`，并在 `finally` 恢复 cwd 与环境。它不使用 `Popen`，也不得以 Popen PID 作为 COM 实例所有权依据。

COM 探针以激活前后 `acad.exe` 快照计算唯一新增 PID，并要求 Application 的 HWND 映射到该 PID；不是唯一新增、PID 不匹配或发现既有实例时均 fail-closed。

`PROCESS_LAUNCH` 仅是 UI-only / 非 COM 进程健康检查合同。它必须显式传入安全 cwd 和规范化环境，不能连接 COM、不能成为 Real COM Backend 默认路径。安全 cwd 固定为 `D:\CadAgentRuntime\s5\launch`；相关环境由独立合同验证后显式传递。

该架构已完成一次 synthetic sandbox 真实集成人工验收。AutoCAD 在关闭最后一个 synthetic 文档后可能自动创建默认空白文档；实现不依赖关闭该默认文档判定核心闭环成功。只要 synthetic 文档持久化与幂等验证完成、没有用户文件操作且最终 `acad.exe=0`，该行为作为 `ALLOWED_DIFFERENCE_AUTOCAD_AUTO_CREATED_DEFAULT_DOCUMENT` 记录。
