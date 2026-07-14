# ????? T30 ?????? Acceptance Pack

## 使用前提

- 必须在真实 AutoCAD + 天正给排水 T30 V1.0 环境运行。
- 第一步运行 `run_probe.bat`，该步骤只读，不写 CAD。
- 第二步根据 probe 结果填写 `manual_confirmation.json`。
- 第三步运行 `run_dry_acceptance.bat`。
- 第四步按 `checklist.md` 完成人工确认。
- 第五步才允许运行 `run_real_sandbox_acceptance.bat`。

原始 DWG 不会被修改。所有真实写回必须进入 sandbox DWG。

只有 sandbox writeback + re-read verification 通过后，才可声明真实补图成功。
