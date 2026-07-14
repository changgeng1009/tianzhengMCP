# Legacy 集成

## 当前状态

`integrations/legacy_p4_adapter.LegacyCadBackendAdapter` 是默认禁用的合同骨架：

```text
backend_kind = LEGACY_ADAPTER
enabled = false
available = false
production_allowed = false
production_d1_allowed = false
real_cad_execution = false
real_dwg_modified = false
```

它不导入 COM、旧 executor、P4 模块或 ActiveDocument。可注入 facade 只是未来合同；当前 `probe()` 明确报告 `facade_called=false`、`real_cad_connection_attempted=false`。

## 当前行为

- capability 列出 open/inspect/create/copy/transform/batch/save/reopen，但全部 `available=false`。
- `list_documents()` 返回空列表。
- open、inspect、close、entity list、execute batch、save、reopen 全部抛出 `BACKEND_UNAVAILABLE`。
- 传入 `enabled=true` 不会启用 adapter。

因此，它不是 Real backend，也不证明 P4.1、COM、CopyObjects、DWG 保存或重开能力已经接入。

## 为什么不直接包装 P4.1

正式 P4.1 是一次受控实验执行器，包含冻结的 DWG 路径、阶段授权和人工验收语义。此前一次实验副本授权不等于长期生产授权。直接包装会带来：

- ActiveDocument 或路径身份漂移
- checkpoint/resume 语义不一致
- 外层 timeout 破坏保存临界区
- 自动依赖误分类
- 将 P4 专用能力伪装为通用 backend

本阶段未运行 P4.1，也未修改旧执行器。

## 未来启用门槛

未来独立阶段至少需要：

1. 明确的受控 facade，不允许自由命令。
2. `ApprovalContext` 绑定 job、完整文档身份、plan hash、allowed operations、expiry、single-use。
3. 工作副本路径 allowlist；SOURCE/REFERENCE/TARGET_ORIGINAL 永久禁止写。
4. batch/task ID 驱动的 checkpoint/resume，不按序号猜测。
5. journal previous-hash 链和原子 checkpoint。
6. 自动依赖分类。
7. save/checkpoint 临界区保护与 `MANUAL_SAVE_REQUIRED`。
8. Mock 与 Legacy/Real capability 强隔离。
9. 完整 Mock 回归、受控 sandbox 验收与人工授权。
10. Manager 明确放行；默认继续 `production_d1_allowed=false`。

## 兼容策略

旧 API、执行器、报告 Schema 和 DWG 路径保持不变。NextGen 通过 adapter 映射 canonical 模型，不删除、重命名或覆盖旧 P2/P3/P4 代码。

当前建议只测试 disabled 行为和 capability truthfulness，不测试真实执行。


