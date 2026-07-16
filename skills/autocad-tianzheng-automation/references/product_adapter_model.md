# 产品适配器模型

S3 以 `ProductProfile` 表示“要处理什么”，以 `execution_runtime` 表示“在哪里运行”。产品适配器不得把运行时、Backend 可用性或审批权限混入产品身份；Manifest 也不得覆盖注册表中的产品真值。

统一 `ProductAdapter` 合同提供四个纯数据入口：

- `inspect()`：说明可检查的离线合同与限制；不读取真实 DWG/DXF。
- `plan()`：生成确定性离线/Mock 计划；不创建 CAD 实体。
- `validate()`：核对 Manifest、产品、运行时、Backend 与安全边界；冲突时 fail-closed。
- `execute()`：当前只能返回离线/Mock 结果或拒绝真实执行；绝不连接 AutoCAD、天正或 COM。

| 产品档案 | 适配器 | 当前状态 | 可用执行运行时 | 真实能力边界 |
| --- | --- | --- | --- | --- |
| `generic_autocad` | `GenericAutoCadAdapter` | `OFFLINE_PLANNING_IMPLEMENTED` | `offline`、`mock` | 普通对象工作流仅离线规划；Real AutoCAD/COM/ObjectARX 未实现。 |
| `tianzheng_water` | `TianzhengWaterAdapter` | `OFFLINE_PLANNING_IMPLEMENTED` | `offline`、`mock` | 给排水识别、缺失检测和补全只产生计划；原生拓扑/工程语义未验证，Water Real backend 未实现。 |
| `tianzheng_hvac` | `TianzhengHvacAdapter` | `INTERFACE_ONLY` | `offline`、`mock` | 房间、风管、水管、设备、风口和标注为独立接口；暖通写入不可执行。通用几何回退不等于天正暖通能力。 |
| `offline_analysis` | `OfflineAnalysisAdapter` | `IMPLEMENTED` | `offline`、`mock` | 仅 JSON、报告、Schema、图片/PDF 计划、代码与 Mock；不读取真实 CAD。 |

`OriginalRedrawSkillAdapter` 是兼容层，不是一个产品档案：它只把原始 GitHub 重绘任务映射为 `generic_autocad` 的离线规划，并保留安全门。它不修改原 Skill，也不调用真实 CAD 执行。

暖通不得套用给排水名称或规则。所有对象声明必须区分 `IMPLEMENTED`、`PARTIALLY_IMPLEMENTED`、`INTERFACE_ONLY`、`NOT_IMPLEMENTED`、`UNSAFE`；不得把接口、合同、Mock 或几何回退描述为天正真实对象支持。
