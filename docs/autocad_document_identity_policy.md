# AutoCAD Document Identity 与 Ownership 策略

## Document Identity

S5 的 `AutoCadDocumentIdentity` 至少包含：run ID、canonical full path、Document 名称、Document COM 引用标识、Application 版本、创建时间、synthetic 标记、`source_document=null`、`user_document=false`、job ID、plan hash、readonly 状态和 ownership 状态。

identity 不是只比较文件名。写前、保存前、关闭前和重开后均须与登记 identity 对比；不一致时必须停止，不得按 `ActiveDocument` 继续。

## 路径策略

- 路径必须 resolve/canonicalize 后位于当前 `artifacts/s5_real_autocad_backend/<run_id>/sandbox/`；
- 运行前目标文件不得存在；
- `.dwg` 仅可作为当前 run 标记为 synthetic 的输出；
- 禁止路径逃逸、相对路径、重解析点或指向用户目录的替换；
- 不允许使用 `D:\CodexWork\天正\图纸`、课程目录、历史 output/artifacts 候选图作为输入或源。

## 写前检查

Document Manager 在每次写入前必须验证：预期路径、COM Document 引用、job ID、plan hash、synthetic ownership、readonly、批准 operation 和当前 session。失败统一进入 `AUTOCAD_DOCUMENT_IDENTITY_MISMATCH` 或 `REAL_CAD_ACCESS_SCOPE_VIOLATION`。

## 重开与持久化

重开只能使用证据中记录的 exact canonical path，并重新建立 Document COM 引用。随后按 Handle/ObjectName/Layer/Geometry/fingerprint/operation key 验证三个允许实体。不得用对象总数作为唯一持久化或幂等性依据。
