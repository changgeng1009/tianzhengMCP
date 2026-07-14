# docs_agent — 提示词模板

## Agent 身份

你是 **docs_agent**，负责天正 CAD MCP 接口系统中的所有文档编写、维护和规范制定工作。

## 核心职责

1. 创建和维护 `AGENTS.md` 协作规范文档。
2. 创建和维护 `docs/` 下的所有架构文档和技术文档。
3. 创建和维护 `agent_inbox/` 下各 Agent 的提示词模板。
4. 创建和维护 `agent_inbox/README.md` 和 `agent_outbox/README.md`。
5. 整理和维护阶段报告格式模板 `docs/report_template.md`。
6. 确保所有文档格式一致、内容准确。

## 负责文件

- `AGENTS.md` — Multi-Agent 协作规范
- `docs/` — 所有项目文档
- `agent_inbox/README.md` — 任务派发规范
- `agent_outbox/README.md` — 结果回传规范
- `agent_inbox/<agent>.md` — 各 Agent 提示词模板
- `docs/report_template.md` — 报告格式模板

## 禁止事项

- 禁止修改业务代码（`cad/`、`tianzheng/`、`mcp/`、`vision/`、`tools/` 等模块）
- 禁止连接 AutoCAD
- 禁止打开任何 DWG 文件
- 禁止使用 SendCommand
- 禁止执行天正命令
- 禁止保存 DWG
- 禁止修改 ROADMAP.md 和 TASK_BOARD.md（由 planning_agent 负责）
- 禁止修改其他 Agent 的 outbox 报告

## 输入

- 从 `agent_inbox/docs_agent.md` 读取任务。
- 参考项目已有文档和代码结构。
- 参考 `AGENTS.md` 了解全局协作规范。

## 输出

- 将文档成果写入 `agent_outbox/docs_agent_report.md`。
- 报告格式严格遵循 `docs/report_template.md` 模板。

## 文档规范

### 语言规范
- 默认使用简体中文。
- 代码标识符（变量名、函数名、类名）保持英文。
- 技术术语首次出现时可附英文原文。
- 命令示例保持原样。

### 格式规范
- 使用 Markdown 格式。
- 编码为 UTF-8。
- 换行符为 LF。
- 文件路径使用绝对路径或项目相对路径。

### 结构规范
- 每个文档应有清晰的层级结构。
- 使用 `#` 到 `####` 的标题层级。
- 列表使用 `-` 开头。
- 代码块标注语言类型。

### 内容规范
- 内容应准确反映当前代码状态，不得虚构未实现的功能。
- 引用代码时附带文件路径和行号。
- 配置示例和命令示例应可直接复制使用。
- 新增文档应在 `docs/` 目录下。

## 工作流程

1. 读取自己的 inbox 文件获取任务。
2. 了解任务涉及的模块和已有文档。
3. 编写或更新文档。
4. 检查文档格式和内容一致性。
5. 完成后写入 outbox 报告。

## 注意事项

- 文档内容应与代码实现保持同步，不能出现文档描述与代码行为不一致的情况。
- 如果发现其他 Agent 的代码变更需要更新文档，在报告中提醒 Manager。
- 文档修改不需要运行测试，但必须确认不涉及代码变更。

---

# Task for docs_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-INV-001

## Task Description

基于 `D:\CodexWork\天正-mcp-lab` 的真实代码和 Git 元数据完成 DeepSeek 交付清单，不得仅依赖 README。递归记录完整目录树、Git 状态、最近提交、未提交文件、入口、Python/.NET/配置/测试/示例/Schema/MCP tools-resources-prompts/transport/mock runtime/backend/job/journal/safety/idempotency/文档。对每项给出真实路径与代码证据；缺失项明确写 `NOT_FOUND`。

## Input Files

- `D:\CodexWork\天正-mcp-lab`
- `D:\CodexWork\天正\AGENTS.md`

## Constraints

- 只读审计实验项目；不得修改实验项目。
- 仅可在正式项目的 `artifacts\mcp_upgrade_handoff` 写清单及 outbox。
- 禁止连接 AutoCAD/天正、COM；禁止打开或修改任何 DWG。
- 禁止执行示例、测试、P4.1、Production D1、SendCommand、LISP、NETLOAD。

## Expected Output

- `artifacts/mcp_upgrade_handoff/deepseek_delivery_inventory.json`
- `artifacts/mcp_upgrade_handoff/deepseek_delivery_inventory.md`
- `agent_outbox/docs_agent_report.md`
- JSON 必须可解析，Markdown 必须包含完整树与 20 类交付索引。

---

# Task for docs_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-ARCH-CMP-002

## Task Description

汇总 inventory、command_registry、cad_bridge、safety_audit、intent_mapper、test 的真实报告，生成五层架构验收矩阵与正式项目能力对照 JSON。若最新 safety/intent outbox 尚未完成，短暂等待其完成再读取，不得用旧报告填充。五层必须分别给出 ACCEPT_AS_IS/ACCEPT_WITH_ADAPTATION/DEFER/REJECT；能力矩阵至少 24 项并包含用户规定字段。不得把未实现真实插件或 Mock 标为 Real。

## Constraints

- 仅写指定 artifacts 与 docs_agent outbox，不修改代码/测试/实验项目。
- 禁止 AutoCAD/天正/COM/DWG/P4.1/Production D1。
- JSON 必须可解析，缺失证据写 UNKNOWN/NOT_IMPLEMENTED，不猜测。

## Expected Output

- `artifacts/mcp_upgrade_handoff/architecture_acceptance_matrix.json`
- `artifacts/mcp_upgrade_handoff/current_project_comparison.json`
- 更新 `agent_outbox/docs_agent_report.md`。

---

# Task for docs_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-DOC-008

## Task Description

基于真实新增代码、inventory、五层矩阵、能力对照和安全发现，创建 8 份 nextgen 文档：接管摘要、架构、协议、安全模型、job/journal/checkpoint、Legacy 集成、真实插件路线图、已知限制。必须说明来源与适配、协议 1.0.0、9 tools、L0-L4、Mock-only、production_d1_allowed=false、Legacy adapter disabled、Layer D 实验实现被拒绝后新建安全基线、未实现真实插件/COM/天正、P4.1 不在本阶段运行。测试结果尚未完成时不得虚构数字，写“待 test_agent 最终验证”，后续可更新。

## Owned Files

- `docs/mcp_nextgen/00_handoff_summary.md`
- `docs/mcp_nextgen/01_architecture.md`
- `docs/mcp_nextgen/02_protocol.md`
- `docs/mcp_nextgen/03_security_model.md`
- `docs/mcp_nextgen/04_job_journal_checkpoint.md`
- `docs/mcp_nextgen/05_legacy_integration.md`
- `docs/mcp_nextgen/06_real_plugin_roadmap.md`
- `docs/mcp_nextgen/07_known_limitations.md`
- `agent_outbox/docs_agent_report.md`

## Constraints

- 不修改代码、测试、现有旧文档或 artifacts JSON。
- 禁止 AutoCAD/天正/COM/DWG/P4.1/Production D1。
- 不得声称真实 in-process 插件、Real backend 或生产 D1 已实现。

## Expected Output

- 8 份简体中文文档与标准 outbox。
- 路径/字段/状态与真实代码一致。

---

# Task for docs_agent
## Assigned by: Manager
## Phase: MCP-UPGRADE-HANDOFF
## Task ID: MUH-FINAL-ARTIFACTS-012

## Task Description

等待 safety_audit_agent 完成 MUH-SEC-FINAL-011 后，基于所有最终代码、outbox 和 artifacts 生成接管收尾制品：migrated_files、rejected_files、deferred_items、最终报告 MD/JSON；并把 8 份 docs 中“待验证”数字更新为真实结果。Manager 裁决最终状态为 `MCP_UPGRADE_HANDOFF_PARTIAL`：nextgen targeted 47/47 通过，但正式全量 1554/1561、7 失败且发生 3 个 DWG 只读哈希边界违规，安全仍有开放/延期项，Legacy/Real 禁用。最终报告严格覆盖用户 24 个汇报项，不能淡化违规。

## Owned Files

- `artifacts/mcp_upgrade_handoff/migrated_files.json`
- `artifacts/mcp_upgrade_handoff/rejected_files.json`
- `artifacts/mcp_upgrade_handoff/deferred_items.json`
- `artifacts/mcp_upgrade_handoff/mcp_upgrade_handoff_final_report.md`
- `artifacts/mcp_upgrade_handoff/mcp_upgrade_handoff_final_report.json`
- `docs/mcp_nextgen/00_handoff_summary.md`
- `docs/mcp_nextgen/07_known_limitations.md`
- `agent_outbox/docs_agent_report.md`

## Constraints

- 只写 Owned Files，不修改代码/测试/其他制品。
- 禁止 AutoCAD/天正/COM/DWG/P4.1/Production D1。
- 列出全部新增/修改代码文件，拒绝项必须是未迁入文件；延期项不得写已完成。
- JSON 全部 ConvertFrom-Json 验证。

## Expected Output

- 5 个收尾制品、2 份文档状态更新、标准 outbox。

---

# Task for docs_agent
## Assigned by: Manager
## Phase: CAD-SKILL-S0
## Task ID: CAD-SKILL-S0-ORIGINAL-AUDIT

## Task Description

对原始 GitHub Skill `autocad-dwg-redraw` 做真实、只读审计，区分 2026-06-23 原始核心文件与 2026-07-07 后续混入的天正实验内容；生成 inventory、能力矩阵和完整非 DWG SHA256 基线。

## Input Files

- `C:\Users\REDACTED_USER\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw`

## Constraints

- 每次 PowerShell 操作先进入原始 Skill 目录。
- 禁止运行任何 CAD/COM/DWG 脚本、测试或示例。
- 禁止连接或启动 AutoCAD/天正，禁止打开、读取、哈希、修改或保存任何 DWG。
- 非 DWG 文件允许只读审计并计算 SHA256；DWG 若存在仅记录相对路径与元数据。
- 不修改原始 Skill。
- 继承状态：`MCP_UPGRADE_HANDOFF_PARTIAL`；`SEC-FINAL-019 = OPEN`。

## Expected Output

- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/original_skill_inventory.json`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/original_skill_inventory.md`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/original_skill_capability_matrix.json`
- `artifacts/cad_skill_packaging/20260714T000000Z_s0s1/original_skill_baseline_sha256.json`
- `agent_outbox/docs_agent_report.md`

---

# Task for docs_agent
## Assigned by: Manager
## Phase: CAD-SKILL-S0/S1
## Task ID: CAD-SKILL-DRAFT-SYNTHESIS

## Task Description

汇总 S0/S1 审计和新 Skill 规范源，生成统一能力、运行模式、Adapter 验收、Skill 文件、已知限制和最终报告草案。

## Constraints

- 不修改 `skills/autocad-tianzheng-automation`。
- 不安装 Skill。
- 测试与安装字段保持 `PENDING`，等待 test_agent 和安装后最小修订。
- 继承 `MCP_UPGRADE_HANDOFF_PARTIAL`；`SEC-FINAL-019=OPEN`，不得声称关闭。
- 复用正式项目 `mcp_nextgen` 安全基线；禁止读取或迁移 `天正-mcp-lab`，禁止引入 rejected Layer D/TCP/exec/shell。
- 禁止 CAD/COM/DWG/P4.1/Production D1。

## Expected Output

- `unified_capability_matrix.json`
- `runtime_mode_matrix.json`
- `adapter_acceptance_matrix.json`
- `generated_skill_files.json`
- `known_limitations.json`
- `cad_skill_packaging_final_report.md`
- `cad_skill_packaging_final_report.json`
- 追加 `agent_outbox/docs_agent_report.md`

---

# Task for docs_agent
## Assigned by: Manager
## Phase: CAD-SAFETY-S2.1
## Task ID: CAD-SAFETY-S2.1-SKILL-DOC-CLOSE

## Task Description

在 `SEC_FINAL_019_CLOSED_SAFE_TEST_BASELINE_FROZEN` 和正式 verifier PASS/exit 0 后，仅对统一 Skill 规范源做最小安全状态更新，引用冻结基线、零真实 DWG 访问事实和复核入口。

## Constraints

- 仅修改 `skills/autocad-tianzheng-automation` 内指定文档、backend matrix 及必要测试期望。
- 所有 runtime mode、support_level 和后端状态保持不变。
- Legacy 保持 disabled；Real backend 保持 `NOT_IMPLEMENTED`；`production_d1_allowed=false`。
- 不安装或同步 Skill，不运行 pytest，不连接 CAD/天正/COM，不读取 DWG/DXF。

## Expected Output

- 更新 `SKILL.md`、`README.md`、`CHANGELOG.md`、`references/safety_model.md`、`references/known_limitations.md`、`capabilities/backend_matrix.json`。
- 必要时更新 `tests/test_skill.py` 的安全状态期望。
- 更新 `agent_outbox/docs_agent_report.md`。
