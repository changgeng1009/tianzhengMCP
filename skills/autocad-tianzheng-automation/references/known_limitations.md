# 已知限制

- 本阶段不连接 AutoCAD/天正，不读取、打开、保存或修改 DWG。
- `generic_autocad` 与 `tianzheng_water` 仅为 `OFFLINE_PLANNING_IMPLEMENTED`；不得将计划、检查合同或 Mock 输出描述为实际打开、扫描或修改 CAD。
- `tianzheng_hvac` 为 `INTERFACE_ONLY`，暖通写入不可执行；若存在通用几何回退，只是普通几何离线规划，不验证任何天正暖通对象、样式、显示环境、拓扑或工程语义。
- NextGen Mock 与 S4 Mock-only Control Plane 均为 `IMPLEMENTED_BASELINE`；控制面仅运行确定性 Mock job，不启动 listener。NextGen 真实后端、Legacy COM、AutoCAD .NET / ObjectARX 插件和天正真实后端均为 `NOT_IMPLEMENTED`。
- `LegacyAdapter=DISABLED_CONTRACT_ONLY`；原始重绘适配器只进行离线任务映射，不调用原 Skill 的真实执行路径。
- `execution_runtime=com` 与 `execution_runtime=objectarx` 是未来接口且为 `NOT_AVAILABLE`；不能由配置、审批引用或工作流覆盖变为可用。
- 给排水原生拓扑为 `NOT_VERIFIED`，工程语义完整性为 `MANUAL_REVIEW_REQUIRED`。
- 普通 AutoCAD 对象范围是合同上限；逐对象真实支持需后端测试证据。
- 显示环境、天正样式、字典、专业配置和代理显示必须单独验证。
- `SEC-FINAL-019` 已由 `current_safe_baseline_id=CAD-SAFE-20260714T220937+0800` 关闭，权威最终 SHA256 为 `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`；该基线因 `intentional AGENTS.md update` 从父基线 `20260714T193554+0800_s2_1` 重新冻结。`13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9` 仅为 freeze-time provenance。冻结默认测试的 `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`；证据位于 `artifacts/cad_safe_test_baseline/20260714T220937+0800`。
- 文件访问守卫只作用于冻结的 pytest 会话；非 pytest 直接执行、external/real CAD 测试和未来真实后端仍不在该关闭结论内。
- 关闭安全测试问题不代表真实 CAD 能力已实现，也不改变 Legacy disabled、Real backend `NOT_IMPLEMENTED`、`production_allowed=false` 或 `production_d1_allowed=false`。
