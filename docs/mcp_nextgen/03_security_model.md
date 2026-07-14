# MCP NextGen 安全模型

## 默认拒绝

当前基线固定：

```text
backend_kind = MOCK
production_allowed = false
production_d1_allowed = false
real_backend_available = false
```

没有配置开关可以把 Mock 升格为 Real。Legacy adapter 即使传入 facade 或 `enabled=true`，仍保持 unavailable 且不调用 facade。

## 审批绑定

写类或计划类请求必须绑定：

- `request_id`
- `job_id`
- `idempotency_key`
- 完整 `DocumentIdentity`
- `plan_hash`
- `allowed_operations`
- `approval_level`
- `expires_at`
- `single_use=true`

dispatcher 会拒绝 request/job/document/plan/operation 不匹配、过期、已使用或生产授权请求。内部 safety 层默认使用 `ApprovalPolicy(production_d1_allowed=false)`。

## 文档保护

`DocumentIdentity` 使用 canonical full path、64 位 SHA-256、document role 和 backend kind。写目标不能由 ActiveDocument 推断。

当前只允许 Mock 文档身份。源图、Reference、Target 原图及正式 DWG 路径继续受旧主线规则保护；NextGen 本阶段不打开、读取、保存或修改任何 DWG。

持久化 ID 使用 allowlist；journal、checkpoint、job、idempotency 路径在 resolve 后必须位于指定根目录，防止路径穿越。

## Transport 安全边界

当前 transport 只有合同组件：

- bind policy 只允许精确 `127.0.0.1`
- 外部注入至少 32 字符 token
- 仅存 token SHA-256，constant-time compare
- frame 在 JSON 解码前检查字节上限
- 严格 UTF-8、单 frame 单换行、JSON-RPC 2.0
- 非空有界 request_id、idempotency key 和 method 白名单
- replay guard 有 TTL 和容量上限

没有 socket/listen/connect，因此当前不能公开暴露端口。也没有 HTTP、Cloudflare Tunnel 或外部 URL callback。

## 禁止接口

NextGen 工具面不包含：

- 任意 Python 执行
- 任意 C# 编译或执行
- shell 命令工具
- `send_code_to_autocad`
- `execute_code`
- `SendCommand`
- 任意文件访问
- 自动保存未知 ActiveDocument
- 自动关闭 AutoCAD

## Mock/Real 隔离

Mock capability 和结果必须声明：

- `BackendKind.MOCK`
- `real_cad_execution=false`
- `real_dwg_modified=false`
- `production_allowed=false`

Mock save/reopen 是内存快照，不是 DWG 持久化证据。Mock scheduler 是单线程约束模拟，不是 AutoCAD `DocumentContextQueue`。

## 保存与取消

保存运行在 persistence critical section 中。外层 timeout/cancel 在临界区内不抛出，离开安全边界后生效。

保存失败进入 `MANUAL_SAVE_REQUIRED`；runtime 禁止自动关闭、停止或释放仍处于该状态的文档上下文。

## 尚存安全限制

- Layer D 的写锁仅覆盖单进程线程，未实现多进程 fencing。
- single-use 审批能校验，但尚无独立持久化消费账本。
- replay guard 是进程内 transport 防重放；跨进程恢复依赖持久 job/journal/idempotency。
- 正式回归待 test_agent 最终验证。


