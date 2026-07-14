# Phase 15 真实 T30 首张图纸验收规范

Phase 15 用于把真实 T30 写回从安全执行层推进到人工可验收流程。默认不真实写 CAD。

## 安全默认值

- `enable_real_writeback=false`
- `real_com_mode=false`
- `dry_run_only=true`
- `verification_mode=manual_review`
- 原始 DWG 永远不直接写入
- 所有写回必须进入 sandbox DWG
- 没有 `probe_result` 不允许真实写回
- 没有 `manual_confirmation` 不允许 confirmed schema
- 没有 re-read verification 不允许声明真实补图成功

## 推荐流程

1. 运行只读 probe：

```powershell
python -m mcp.t30_writeback.manual_probe_runner
```

2. 生成人工确认模板：

```python
from mcp.acceptance.confirmation_template import generate_manual_confirmation_template
```

3. 人工确认 `manual_confirmation.json`。

4. 运行 acceptance：

```powershell
python -m mcp.acceptance.acceptance_runner `
  --scenario path\to\scenario.json `
  --probe-result artifacts\t30_probe_result.json `
  --manual-confirmation artifacts\manual_confirmation.json `
  --sandbox-dir artifacts\acceptance_sandbox `
  --output-dir artifacts\acceptance_reports `
  --enable-real-writeback false `
  --real-com-mode false `
  --dry-run-only true `
  --verification-mode manual_review
```

5. 真实 sandbox 写回必须显式开启：

```powershell
python -m mcp.acceptance.acceptance_runner `
  --scenario path\to\scenario.json `
  --probe-result artifacts\t30_probe_result.json `
  --manual-confirmation artifacts\manual_confirmation.json `
  --sandbox-dir artifacts\acceptance_sandbox `
  --output-dir artifacts\acceptance_reports `
  --enable-real-writeback true `
  --real-com-mode true `
  --dry-run-only false `
  --verification-mode reread_dwg
```

## 成功判定

只有同时满足以下条件，报告才允许声明“真实补图成功”：

- writeback status 为 `committed`
- writeback mode 为 `real`
- reread verification status 为 `verified`
- 原始 DWG 未被修改
- sandbox 中的写回实体可追踪

否则报告必须明确写明：“不能声明真实补图成功”。
