# 安全模型

- L0：只读扫描与报告。
- L1：只生成计划，不写 DWG。
- L2：创建副本、备份、预览，不写实体。
- L3：仅写当前 job 创建的 Sandbox/实验副本。
- L4：受控生产写入；未来必须单独、明确、单次授权。

审批绑定 `job_id`、`document_identity`、`document_sha256`、`plan_hash`、`allowed_operations`、`runtime_mode`、`product`、`single_use`、`expires_at`。默认 `production_allowed=false` 与 `production_d1_allowed=false`。源 DWG 永不写入。

## 默认测试真实 CAD 零访问基线

`SEC-FINAL-019` 已关闭，冻结基线：

- `current_safe_baseline_id=CAD-SAFE-20260714T220937+0800`
- `baseline_sha256=87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`
- `freeze_time_provenance_sha256=13dc72b6bb08de250f14450d9a941766fc0a6cc474e02ae2ec6bcbe6c74d54c9`（仅保留来源记录，不可作为当前 S2 基线 SHA）
- `parent_baseline_id=20260714T193554+0800_s2_1`
- `parent_baseline_sha256=226281f3a2bb29e72fe9978d6cffcd0fe84c83be1d7f7091ee95df5361f3bcf1`
- `triggering_change=intentional AGENTS.md update`
- `DEFAULT_TEST_REAL_DWG_ACCESS_COUNT=0`
- 项目相对路径：`artifacts/cad_safe_test_baseline/20260714T220937+0800`
- 明确路径：`D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`
- 正式复核：

```powershell
python -m scripts.verify_safe_test_baseline --baseline "artifacts/cad_safe_test_baseline/20260714T220937+0800" --project-root "."
```

该结论仅适用于冻结的默认 pytest 命令和守卫策略。它不授权 external/real CAD 测试，不启用 Legacy、Real backend 或 Production D1；非 pytest 入口仍须独立安全门。
