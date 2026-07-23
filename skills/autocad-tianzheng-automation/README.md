# AutoCAD & Tianzheng Automation

普通 AutoCAD、天正给排水、天正暖通和离线分析的统一安全编排 Skill。默认 `offline`、`production_allowed=false`、`production_d1_allowed=false`。

快速验证：

```powershell
$env:PYTHONUTF8='1'
$dev='D:\PythonEnvs\tianzheng-dev\Scripts\python.exe'
& $dev -m scripts.skill_cli validate-manifest examples/plain_autocad_redraw.json
& $dev -m scripts.skill_cli build-plan examples/plain_autocad_redraw.json --dry-run
& $dev -m pytest --collect-only -q
& $dev -m pytest -q
& $dev -m scripts.verify_safe_test_baseline --baseline "artifacts/cad_safe_test_baseline/20260714T220937+0800" --project-root "."
./scripts/validate_skill.ps1
```

离线入口不连接 AutoCAD，不读取 DWG/DXF 内容。真实 Legacy COM、NextGen MCP、.NET 插件及天正真实后端均不可用。

默认 pytest 会自动排除真实/外部 CAD marker；S5 真实 synthetic 集成必须同时使用显式环境变量和 `real_autocad`、`integration`、`requires_autocad` marker，且不属于默认回归。

## 安全测试基线

`SEC-FINAL-019` 已关闭，`current_safe_baseline_id=CAD-SAFE-20260714T220937+0800`，权威最终 SHA256 为 `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`，父基线为 `20260714T193554+0800_s2_1`，触发原因为 `intentional AGENTS.md update`。`13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9` 只保留为 freeze-time provenance，不是当前 S2 基线 SHA。`DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`。冻结证据位于项目相对路径 `artifacts/cad_safe_test_baseline/20260714T220937+0800`（明确路径 `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`）。这不改变任何 runtime mode、后端能力或生产授权状态。

## S2 配置驱动入口

S2 CLI 支持 `manifest validate|normalize|explain|migrate|diff`、`config resolve`、`runtime/product/backend/workflow select`、`plan build|verify|hash`、`simulate --backend offline|nextgen_mock` 和 `templates list|create`。它只处理 JSON、路径词法解析、确定性 Plan 与 Mock 模拟。Manifest 不能创建或继承审批，不能把 Backend 能力、真实 CAD 权限、L3/L4 或生产权限提升为可用；所有这类尝试均应安全拒绝。
