# 已知限制

- 本阶段不连接 AutoCAD/天正，不读取、打开、保存或修改 DWG。
- NextGen 真实后端、Legacy COM、AutoCAD .NET 插件和天正真实后端不可用。
- 暖通写入为 `INTERFACE_ONLY`，对象注册表需真实只读样本验证。
- 给排水原生拓扑为 `NOT_VERIFIED`，工程语义完整性为 `MANUAL_REVIEW_REQUIRED`。
- 普通 AutoCAD 对象范围是合同上限；逐对象真实支持需后端测试证据。
- 显示环境、天正样式、字典、专业配置和代理显示必须单独验证。
- `SEC-FINAL-019` 已由 `current_safe_baseline_id=20260714T220937+0800` 关闭，基线 SHA256 为 `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9`；该基线因 `intentional AGENTS.md update` 从父基线 `20260714T193554+0800_s2_1` 重新冻结。冻结默认测试的 `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`；证据位于 `artifacts/cad_safe_test_baseline/20260714T220937+0800`。
- 文件访问守卫只作用于冻结的 pytest 会话；非 pytest 直接执行、external/real CAD 测试和未来真实后端仍不在该关闭结论内。
- 关闭安全测试问题不代表真实 CAD 能力已实现，也不改变 Legacy disabled、Real backend `NOT_IMPLEMENTED` 或 `production_d1_allowed=false`。
