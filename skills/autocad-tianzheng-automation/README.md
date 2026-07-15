# AutoCAD & Tianzheng Automation

普通 AutoCAD、天正给排水、天正暖通和离线分析的统一安全编排 Skill。默认 `offline`、`production_allowed=false`、`production_d1_allowed=false`。

快速验证：

```powershell
$env:PYTHONUTF8='1'
python -m scripts.skill_cli validate-manifest examples/plain_autocad_redraw.json
python -m scripts.skill_cli build-plan examples/plain_autocad_redraw.json --dry-run
pytest -q -m "not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only"
python -m scripts.verify_safe_test_baseline --baseline "artifacts/cad_safe_test_baseline/20260714T220937+0800" --project-root "."
./scripts/validate_skill.ps1
```

离线入口不连接 AutoCAD，不读取 DWG/DXF 内容。真实 Legacy COM、NextGen MCP、.NET 插件及天正真实后端均不可用。

## 安全测试基线

`SEC-FINAL-019` 已关闭，`current_safe_baseline_id=20260714T220937+0800`，SHA256 为 `13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9`，父基线为 `20260714T193554+0800_s2_1`，触发原因为 `intentional AGENTS.md update`。`DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`。冻结证据位于项目相对路径 `artifacts/cad_safe_test_baseline/20260714T220937+0800`（明确路径 `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`）。这不改变任何 runtime mode、后端能力或生产授权状态。
