# Phase 14 真实图纸端到端验证说明

Phase 14 用于把现有自动审图与补图系统推进到真实项目图纸验证闭环，但默认不真实写 CAD。

## 默认安全策略

- `dry_run_only=true`
- `enable_real_writeback=false`
- `real_com_mode=false`
- 原始 DWG 不直接修改
- 写回只允许进入 sandbox DWG 副本
- 未确认 capability 不允许真实执行
- 未确认 parameter schema 不允许真实执行
- manual probe 只读，不插入对象

## 输入

Scenario JSON 示例：

```json
{
  "scenarios": [
    {
      "scenario_id": "demo",
      "name": "样例验证",
      "reference_sources": [
        {
          "type": "png",
          "path": "reference.png"
        }
      ],
      "target_dwg_path": "target.dwg",
      "expected_missing": [],
      "manual_anchor_pairs": [],
      "options": {}
    }
  ]
}
```

## 手动运行

安全 dry-run：

```powershell
python -m mcp.e2e.manual_e2e_runner --scenario path\to\scenario.json
```

启用 fake sandbox writeback：

```powershell
python -m mcp.e2e.manual_e2e_runner `
  --scenario path\to\scenario.json `
  --dry-run-only false `
  --enable-real-writeback true `
  --real-com-mode false `
  --verification-mode fake
```

真实 COM 验证必须先运行 Phase 13 只读 probe，并提供人工确认 schema：

```powershell
python -m mcp.t30_writeback.manual_probe_runner
python -m mcp.e2e.manual_e2e_runner `
  --scenario path\to\scenario.json `
  --probe-result artifacts\t30_probe_result.json `
  --manual-confirmation path\to\manual_confirmation.json `
  --dry-run-only false `
  --enable-real-writeback true `
  --real-com-mode true `
  --verification-mode reread_dwg
```

## 输出

- JSON 报告
- Markdown 报告
- metrics
- warnings
- errors
- manual review list

没有 re-read verification 通过时，不得声明真实补图成功。
