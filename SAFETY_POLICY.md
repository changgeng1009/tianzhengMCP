<!--
  SAFETY_POLICY.md — 天正 CAD MCP 接口系统 安全策略
  最后更新: 2026-07-08
  适用范围: 项目所有 Phase，所有 agentic workers
  本文件为项目安全总纲，任何真实执行操作前必须满足本文档全部要求。
-->

# 天正 CAD MCP 接口系统 — 安全策略 (SAFETY POLICY)

## 1. 核心原则

### 1.1 默认拒绝 (Default Deny)

系统默认安全状态：**禁止一切真实执行操作**。除非满足本文档全部审批和安全门控条件，否则：

- 禁止连接 AutoCAD
- 禁止打开任何 DWG 文件
- 禁止修改任何 DWG 文件
- 禁止保存任何 DWG 文件
- 禁止执行 SendCommand
- 禁止执行天正命令 (TPIPE / TDRAIN / TDbPipe.Insert 等)

### 1.2 最小权限 (Least Privilege)

任何模块、工具、agent 只应获取完成任务所需的最小权限。读操作和写操作必须走完全不同的代码路径，且写操作路径默认为 dry-run。

### 1.3 分层安全 (Defense in Depth)

安全防护分为多层，每一层都必须通过才能到达真实执行：

L0: 代码层隔离 (dry-run / sandbox 默认)
L1: Schema 验证 (参数合法性校验)
L2: 用户确认 (明确审批)
L3: 事务边界 (plan → validate → execute → verify → commit)
L4: 回滚保护 (sandbox backup 恢复)

---

## 2. 安全状态层级

### 2.1 安全级别定义

| 级别 | 名称 | 允许操作 | 触发条件 |
|------|------|----------|----------|
| L0 | **禁止** | 无任何真实操作 | 默认状态 |
| L1 | **只读** | 连接 AutoCAD、列出文档、读取对象属性 | 用户明确说"连接 CAD"或"读取图纸" |
| L2 | **预览** | L1 + 生成 Diff/ExecutionPlan 预览 | 用户明确要求预览 |
| L3 | **Sandbox 执行** | L2 + 在 sandbox DWG 中执行写操作 | L2 + 用户说"我批准 sandbox 执行" |
| L4 | **真实执行** | L3 + 对源 DWG 执行写操作 | L3 + 用户说"我批准真实执行" |

### 2.2 安全状态转换规则

L0 → L1: 用户明确说"连接 CAD"或"connect_cad"
L1 → L2: 用户明确要求"preview"或"预览"或"生成执行计划"
L2 → L3: 用户明确说"我批准 sandbox 执行"
L3 → L4: 用户明确说"我批准真实执行"

任何非明确指令的回退: 立即回到 L0

**关键规则**：状态转换必须由用户的**字面文本**触发，不允许 agent 自行推断或升级。即使用户说"我觉得可以执行了"或"应该没问题"，也不视为明确批准。

### 2.3 明确审批短语 (Mandatory Approval Phrases)

以下短语是**唯一**允许的真实执行审批口令：

- 我批准真实执行
- 我批准 sandbox 执行

以下短语**无效**且必须被拒绝：

- "可以执行了"
- "我觉得没问题"
- "go ahead"
- "继续"
- "执行吧"
- "ok"

---

## 3. 各风险路径详细审计

### 3.1 AutoCAD COM 连接风险

**涉及文件**:
- [cad/connection.py](/D:/ExampleWorkspace/天正/cad/connection.py)
- [tools/connect.py](/D:/ExampleWorkspace/天正/tools/connect.py)

**现状**:
- default_manager 是全局单例 (AutoCADConnectionManager)，任何模块 import 即可使用
- 连接时通过 win32com.client.GetObject() 获取已运行的 AutoCAD 实例
- 不会自动启动 AutoCAD，但会获取已运行的实例
- disconnect() 只清除缓存引用，不关闭 AutoCAD

**风险点**:
1. **全局单例暴露**: default_manager 无访问控制，任何代码 rom cad.connection import default_manager 即可获取 AutoCAD 控制权
2. **隐式连接风险**: 没有显式的"请求-批准-连接"流程，connect_cad() 作为 MCP 工具直接暴露

**安全要求**:
- MCP 工具 connect_cad 在用户未明确请求连接前不得调用
- 任何读取 default_manager 的代码必须先检查连接状态
- 建议: 移除全局单例，改为显式依赖注入

### 3.2 SendCommand 风险

**涉及文件**:
- [cad/commands.py](/D:/ExampleWorkspace/天正/cad/commands.py)
- [tools/command.py](/D:/ExampleWorkspace/天正/tools/command.py)
- [server.py](/D:/ExampleWorkspace/天正/server.py) (MCP 工具注册)

**现状**:
- CommandService.send_command() 直接透传任意字符串给 document.SendCommand()
- **无任何命令过滤**: 无白名单、无黑名单、无参数校验
- 作为 MCP 工具 send_command 直接暴露

**风险评估**:
- **严重 [CRITICAL]**: 可执行任意 AutoCAD 命令，包括：
  - SAVE / QSAVE — 覆盖当前 DWG
  - UNDO — 撤销用户操作
  - WBLOCK — 导出/破坏 DWG 内容
  - ERASE ALL — 删除所有对象
  - TPIPE / TDRAIN — 天正绘图命令
  - 任意天正命令

**安全要求**:
- send_command 默认禁止调用
- 需要实现命令白名单（至少屏蔽: SAVE, QSAVE, WBLOCK, ERASE, UNDO, REDO, TPIPE, TDRAIN 等）
- 或完全移除 send_command MCP 工具

### 3.3 源 DWG 误操作风险

**涉及文件**:
- [cad/entities.py](/D:/ExampleWorkspace/天正/cad/entities.py)
- [tools/draw.py](/D:/ExampleWorkspace/天正/tools/draw.py)
- [execution/executor.py](/D:/ExampleWorkspace/天正/execution/executor.py)

**现状**:
- 基础 CAD 实体创建 (draw_line, draw_polyline, add_text) 直接操作 document.ModelSpace
- 这些操作**直接修改当前激活的 DWG** — 即用户正在编辑的图纸
- 没有自动备份、没有 sandbox、没有事务回滚

**风险评估**:
- **高 [HIGH]**: draw_line 等操作直接修改用户正在编辑的 DWG
- 虽然创建的是新增对象（不删除已有对象），但仍会污染图纸
- 如果当前激活文档恰好是 source DWG，则直接修改了源文件

**安全要求**:
- 基础实体创建 (draw_line 等) 必须走完整的安全门控：preview → confirm → execute
- 建议: 写入前自动检查 active document 是否为受保护的 source DWG

### 3.4 DWG 保存风险

**涉及文件**: 无直接 DWG 保存代码，但 SendCommand 可执行 SAVE

**现状**:
- 项目中**没有**实现 document.Save() 或 document.SaveAs() 调用
- 但通过 send_command MCP 工具可透传 SAVE 命令

**风险评估**:
- **高 [HIGH]**: 虽然无直接保存代码，但 SendCommand 无过滤，可执行保存
- 如果 sandbox 内的 DWG 保存会覆盖 sandbox 副本（不是源 DWG，风险较低）
- 如果源 DWG 被保存，则不可逆

**安全要求**:
- 禁止在任何情况下调用 document.Save() / SaveAs()
- send_command 必须过滤 SAVE, QSAVE, SAVEAS 命令
- sandbox 执行完成后，禁止将 sandbox DWG 复制回源 DWG 路径

### 3.5 Sandbox 绕行风险

**涉及文件**:
- [mcp/t30_writeback/sandbox.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/sandbox.py)
- [mcp/t30_writeback/real_adapter.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/real_adapter.py)
- [mcp/t30_writeback/transaction.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/transaction.py)

**现状**:
- create_dwg_sandbox() 创建源 DWG 的文件副本到沙盒目录
- eal_adapter.py 中 eal_com_mode=False 默认为 dry_run
- 	ransaction.py 有完整的 plan → validate → execute → verify → commit 流程
- ollback_transaction() 从 backup 恢复 sandbox DWG

**风险点**:
1. **real_com_mode 可被绕过**: RealT30WritebackAdapter 构造函数接受 real_com_mode 参数，如果代码中被误设为 True，就会绕过 dry-run
2. **commit 不复制回源 DWG**（当前是安全行为）: commit_transaction() 只标记状态，不将 sandbox DWG 复制回源路径
3. **sandbox 路径可配置**: options.get("sandbox_dir") 可能被设为源 DWG 相同路径
4. **T30ObjectFactory fake_mode 默认 True**: 但 real_adapter.py 中构造时使用 fake_mode=not self.real_com_mode

**安全要求**:
- real_com_mode 必须永远是 opt-in，不可被环境变量或配置文件自动开启
- sandbox_dir 参数禁止等于源 DWG 所在目录
- sandbox 执行完成后，**禁止自动**将 sandbox DWG 复制回源 DWG

### 3.6 Dry-Run 前置校验绕行风险

**涉及文件**:
- [tianzheng_interface/dry_run_engine.py](/D:/ExampleWorkspace/天正/tianzheng_interface/dry_run_engine.py)
- [tianzheng_interface/proxy_handler.py](/D:/ExampleWorkspace/天正/tianzheng_interface/proxy_handler.py)

**现状**:
- DryRunEngine.simulate() 始终返回 executable_actions=0
- ProxyObjectHandler.is_modifiable() 始终返回 False
- Phase 1 设计：纯数据分类，不访问 COM

**风险点**:
- DryRunEngine 和 ProxyHandler 是 Phase 1 的 stub 实现，后续 Phase 如被升级为真实模式可能失去保护

**安全要求**:
- dry-run 引擎必须永远先于任何真实执行运行
- 如果 dry-run 返回 executable_actions > 0，必须额外确认

### 3.7 T30 天正对象写入风险

**涉及文件**:
- [mcp/t30_writeback/object_factory.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/object_factory.py)
- [mcp/t30_writeback/com_probe.py](/D:/ExampleWorkspace/天正/mcp/t30_writeback/com_probe.py)
- [mcp/adapter_t30.py](/D:/ExampleWorkspace/天正/mcp/adapter_t30.py)

**现状**:
- T30ObjectFactory 在 fake_mode=True 时不调用 COM
- 在 fake_mode=False 且 capability confirmed 时调用 obj.Insert(parameters) 进行真实 COM 写入
- com_probe.py 的 _resolve_document() 在 allow_open_document=True 时会调用 Documents.Open()

**风险点**:
1. **COM 写入能力探测即连接**: T30COMProbe.probe_environment() 会连接 AutoCAD
2. **自动打开 DWG**: allow_open_document=True 时可自动打开 DWG 文件
3. **真实 Insert 调用**: T30ObjectFactory._create() 在非 fake 模式下直接调用 COM Insert

**安全要求**:
- probe_environment() 必须在用户明确授权后才能调用
- allow_open_document 默认必须为 False
- T30ObjectFactory fake_mode 默认必须为 True

---

## 4. 各 Phase 安全边界

### Phase 1-2: 连接层

- **允许**: connect_cad, disconnect, status
- **禁止**: send_command, draw_line, 任何 DWG 修改
- **安全机制**: 仅连接，不写入

### Phase 3-4: Vision Diff + 基础执行

- **允许**: 读取 current DWG、生成 ExecutionPlan、preview
- **条件允许**: draw_line / draw_polyline / add_text (须经 preview → confirm → execute)
- **禁止**: move_entity / modify_entity / delete_suggestion
- **安全机制**: 坐标系统校验、映射完整性校验、操作数量上限 (>10 → HIGH risk)

### Phase 5-6: 天正对象读取

- **允许**: 只读操作 (读取 TDbPipe、TDbPipeValve、管径、图层等)
- **禁止**: 任何写入、调用 TPIPE/TDRAIN、天正绘图命令
- **安全机制**: 严格只读，无 COM 写入路径

### Phase 7-12: Pipeline + 空间对齐 + 修复动作

- **允许**: dry-run 预览、repair_plan 生成
- **条件允许**: sandbox 写入 (须经完整审批链)
- **禁止**: 直接修改源 DWG
- **安全机制**: fake mode 默认、sandbox 隔离

### Phase 13-16: T30 写回 + E2E 验收

- **允许**: sandbox 内 T30 对象创建
- **条件允许**: 真实 T30 写入 (须经: dry-run → sandbox → capability probe → schema confirm → transaction → verify → commit)
- **禁止**: sandbox DWG 自动复制回源 DWG
- **安全机制**: 完整事务引擎、rollback 保护、verifier 校验

---

## 5. Agent 执行规则

### 5.1 所有 Agent 必须遵守

1. **启动时默认 L0 状态**: 不假定任何授权
2. **任何真实操作前必须检查**: 用户是否明确说了审批短语
3. **安全检查清单**:
   - [ ] 用户是否明确说了"我批准真实执行"或"我批准 sandbox 执行"？
   - [ ] 是否已完成 dry-run 预览？
   - [ ] 是否已通过 schema validation？
   - [ ] 是否已创建 sandbox 副本？
   - [ ] 操作范围是否限制在允许的边界内？
4. **写入操作必须记录**: 每次真实写入必须在报告中记录 action_id、目标、结果

### 5.2 禁止行为清单

1. 禁止 agent 自行推断用户意图为"批准"
2. 禁止跳过任何安全门控（preview、confirm、sandbox、verify）
3. 禁止将 sandbox DWG 复制覆盖源 DWG
4. 禁止在未授权状态下调用 send_command
5. 禁止设置 real_com_mode=True 除非用户明确批准真实执行
6. 禁止修改 SAFETY_POLICY.md 或将安全级别降级

---

## 6. 已知安全债务

| ID | 描述 | 严重程度 | 影响文件 | 建议修复 |
|----|------|----------|----------|----------|
| SK-001 | SendCommand 无命令过滤 | CRITICAL | cad/commands.py:26 | 添加命令白名单/黑名单 |
| SK-002 | default_manager 全局单例 | HIGH | cad/connection.py:156 | 改为依赖注入 |
| SK-003 | draw_line 直接修改 active DWG | HIGH | cad/entities.py, tools/draw.py | 增加自动备份或 sandbox 检查 |
| SK-004 | com_probe 可能自动打开 DWG | MEDIUM | mcp/t30_writeback/com_probe.py:149 | allow_open_document 默认 False |
| SK-005 | sandbox_dir 无路径校验 | MEDIUM | mcp/t30_writeback/sandbox.py:24 | 禁止 sandbox_dir 等于源 DWG 目录 |
| SK-006 | 坐标校验默认边界过宽 | LOW | execution/validation.py:16 | 可配置化或收紧默认边界 |
| SK-007 | real_com_mode 可以代码级绕过 | MEDIUM | mcp/t30_writeback/real_adapter.py:25 | 增加环境变量/配置文件禁令 |

---

## 7. 变更记录

| 日期 | 版本 | 变更描述 |
|------|------|----------|
| 2026-07-08 | 1.0 | 初始安全策略，Phase M0 safety audit 创建 |
