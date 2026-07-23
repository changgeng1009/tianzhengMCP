# S5 AutoCAD COM 失败与恢复策略

## 不承诺事务回滚

COM 不提供本阶段可验证的数据库事务语义，因此不得声明 `transactional_rollback=true`。S5 依赖写前身份校验、审批、append-only journal、原子阶段状态和可废弃的 synthetic Sandbox，而非修改用户文件后的回滚。

## 错误处理

| 错误代码 | 必须动作 |
|---|---|
| `AUTOCAD_NOT_AVAILABLE` / `AUTOCAD_COM_CONNECTION_FAILED` | 不重试到未知实例；保存预检证据并停止。 |
| `AUTOCAD_SESSION_UNSAFE` / `AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED` | 不触碰已有文档；停止并等待人工处理。 |
| `AUTOCAD_DOCUMENT_IDENTITY_MISMATCH` / `REAL_CAD_ACCESS_SCOPE_VIOLATION` | 立即停止当前写入；不使用 ActiveDocument 回退。 |
| `AUTOCAD_ENTITY_VALIDATION_FAILED` / `AUTOCAD_ENTITY_CREATION_FAILED` | 记录 DTO、批准操作和已创建 synthetic 实体证据；不扩大写入范围。 |
| `AUTOCAD_SAVE_FAILED` / `AUTOCAD_REOPEN_FAILED` / `AUTOCAD_PERSISTENCE_VERIFICATION_FAILED` | 保留 journal 与当前 synthetic 状态；不得虚报持久化成功。 |
| `AUTOCAD_IDEMPOTENCY_FAILED` | 停止重复执行；记录 operation key 与 fingerprint 冲突。 |
| `AUTOCAD_TIMEOUT` / `AUTOCAD_MANUAL_SAVE_REQUIRED` | 标记失败或人工复核；不 taskkill、不强制关闭 AutoCAD。 |

## 收敛原则

异常时只处理当前由 registry 所有的 synthetic Document。尚未批准或未验证的更改不得保存；已经保存的 synthetic 状态可作为证据保留或由后续独立 run 废弃重建。不得关闭、保存或修改任何用户 Document，不得迁移失败状态到 Production D1。
