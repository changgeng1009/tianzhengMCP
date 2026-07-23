# S6 普通 AutoCAD 结构化能力

S6 在 S5 的 `real_autocad_com` synthetic sandbox 边界上建立了后端中立的
操作 DTO、确定性计划、Mock 后端、S4 Mock Control Plane 适配及受限 Real COM
Gateway。真实验收仅使用本轮新建的 synthetic DWG，不读取或修改用户图纸。

## 支持范围

- 创建：Line、Circle、Polyline、Arc、Rectangle、Text、MText、普通 BlockDefinition 和 BlockReference；
- 查询和修改：按 handle/operation/layer/type 的受限查询，以及 Move、Copy、Rotate、Scale、Delete；
- 资源：`CADAGENT_S6_MVP` 专用图层、基础 TextStyle 与 DimensionStyle ensure；同名冲突返回结构化 `CONFLICT`，不覆盖未知资源；
- 计划：版本化 DTO、几何/数值验证、`dry_run`、能力预期、顺序依赖、S4 Mock 作业审批；
- 持久化：Save、Close、精确路径 Reopen、ModelSpace/Blocks 实际查询、append-only job journal 幂等重放。

几何模型包含 Point2/Point3、Vector3、BoundingBox、Transformation、GeometryTolerance；所有值均是可序列化纯数据，不包含 COM 对象。旋转统一使用弧度，默认平面工程单位为毫米。

## Backend 状态

| Backend | 状态 | 写入范围 |
| --- | --- | --- |
| `SyntheticCadBackend` | `SUPPORTED_FOR_TEST` | 纯内存 Mock，支持 `best_effort` 与 `all_or_nothing` 模拟。 |
| `RealAutoCadComBackend` | `AVAILABLE_SANDBOX_MVP` | 仅当前 job 新建的 L3 synthetic sandbox，显式 opt-in。 |
| AutoCAD .NET/ObjectARX | `NOT_IMPLEMENTED` | 不属于 S6。 |
| Tianzheng / Legacy Real / NextGen Real | `NOT_AVAILABLE` | 不属于 S6。 |

真实 COM batch 仅允许可解释的 `best_effort`；`all_or_nothing` 会明确拒绝，不能虚报数据库级事务或回滚。

## 测试和真实集成

默认测试使用 `D:\PythonEnvs\tianzheng-dev\Scripts\python.exe -m pytest -q`，不会启动 AutoCAD、连接 COM、访问 DWG/DXF 或连接天正。真实验收必须使用 S5 指定环境、显式 `CAD_S5_AUTOCAD_INTEGRATION=1`，并通过 job-owned COM activation、L3 approval 和 synthetic document identity。

最终 S6 真实验证创建 9 类实体、3 类样式资源、执行 18 项计划操作，完成保存、关闭、精确路径重开、持久化查询、journal 重放和正常 Quit；最终 `acad.exe=0`。证据见 `artifacts/s6_cad_capabilities/20260724T012510+0800_s6_final_journal_acceptance/`。

## 不变的边界

- 仅允许当前 job 新建的 synthetic sandbox；
- 用户 DWG/DXF、天正、L4、Production D1、Legacy Real、NextGen Real、.NET/ObjectARX 均不可用；
- 不使用 SendCommand、LISP、NETLOAD、ActiveDocument 回退或强制结束进程；
- S6 不是生产能力，也不代表任意用户图纸可安全处理。
