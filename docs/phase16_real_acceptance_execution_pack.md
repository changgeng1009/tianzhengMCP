# Phase 16 真实验收执行包说明

Phase 16 将 Phase 15 的验收能力整理为可复制执行包，默认只做 dry-run，不真实写 CAD。

## 执行包位置

`acceptance_pack/`

包含：

- `README.md`
- `scenario_template.json`
- `manual_confirmation_template.example.json`
- `run_probe.bat`
- `run_dry_acceptance.bat`
- `run_real_sandbox_acceptance.bat`
- `checklist.md`

## 推荐顺序

1. 复制 `scenario_template.json`，填入真实 reference 与 target DWG。
2. 在真实 AutoCAD + 天正给排水 T30 V1.0 环境中运行 `run_probe.bat`。
3. 根据 probe 输出填写 `manual_confirmation.json`。
4. 运行 `run_dry_acceptance.bat`，检查 dry-run 报告。
5. 按 `checklist.md` 完成逐项确认。
6. 只有用户主动确认后，才运行 `run_real_sandbox_acceptance.bat`。

## 安全原则

- 默认命令不真实写 CAD。
- 原始 DWG 不直接修改。
- 真实写回必须进入 sandbox。
- 没有 confirmed schema 不允许真实写回。
- 没有 re-read verification 不允许声明真实补图成功。
- fake acceptance 不能当作真实成功。

## 结果处理

可以使用 `mcp.acceptance_pack.result_collector.collect_acceptance_results()` 收集 artifacts。

可以使用 `mcp.acceptance_pack.failure_diagnoser.diagnose_acceptance_failure()` 诊断失败原因。

可以使用 `mcp.acceptance_pack.review_list.generate_manual_review_list()` 生成人工审核清单。
