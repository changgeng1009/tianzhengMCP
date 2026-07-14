# 天正 CAD MCP 接口系统 - 任务看板

> 最后更新：2026-07-14
> 当前阶段：**MCP-UPGRADE-HANDOFF PARTIAL** | 安全闭环与合规全量回归阻塞 | `production_d1_allowed=false` | 不推进下一阶段

---

## 状态图例

| 图标 | 含义 |
|------|------|
| `OK` | 已完成 |
| `>>` | 进行中 |
| `--` | 待开始 |
| `XX` | 阻塞 |
| `!!` | 禁止（当前阶段不可执行） |

---

## Phase M0：项目规划与状态审计

**状态：OK 已完成**
**负责人：planning_agent**
**开始：2026-07-08 | 完成：2026-07-08**

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| M0.1 | 读取 ROADMAP.md、server.py、mcp/、tests/、reports/ | OK | 全面了解项目状态 |
| M0.2 | 判断当前项目阶段 | OK | ROADMAP写至6.4，实际代码达Phase 17 |
| M0.3 | 定义 Phase M0 验收标准 | OK | 已在报告中定义 |
| M0.4 | 拆分 M1-M4 + D1-E2 任务 | OK | 共 28 个任务项 |
| M0.5 | 更新 ROADMAP.md | OK | 追加 M0-M4 + D1-E2 规划 |
| M0.6 | 创建 TASK_BOARD.md | OK | 本文档 |
| M0.7 | 创建 reports/planning_agent_report.md | OK | 已在前期完成 |
| M0.8 | 创建 agent_outbox/planning_agent_report.md | OK | 已在前期完成 |

---

## Phase M1：天正给排水接口层完整化（只读） **OK 已完成**

**状态：OK 已完成**
**前置：Phase M0 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| M1.1 | 实现 scanner.py | OK | tianzheng_interface/scanner.py | 一键扫描器 |
| M1.2 | 实现 report_builder.py | OK | tianzheng_interface/report_builder.py | 双格式报告 |
| M1.3 | 新增系统类型配置 | OK | config/tianzheng_system_types.json | |
| M1.4 | 新增 Action 模板配置 | OK | config/tianzheng_action_templates.json | |
| M1.5 | 新增扫描报告样例 | OK | examples/tianzheng_dwg_scan_report.md | |
| M1.6 | 编译检查新模块 | OK | python -m py_compile | |
| M1.7 | 运行 pytest | OK | pytest -q | |

---

## Phase M2：Action Schema 验证与 Dry-run 完善

**状态：OK 已完成**
**前置：Phase M1 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| M2.1 | 完善 action_schema | OK | tianzheng_interface/action_schema.py | 6 种 action type |
| M2.2 | 完善 dry_run_engine | OK | tianzheng_interface/dry_run_engine.py | 冲突检测+变更预估 |
| M2.3 | 完善 proxy_handler | OK | tianzheng_interface/proxy_handler.py | 自动发现未知识别 |
| M2.4 | scanner 扩展测试 | OK | tests/test_tianzheng_interface_scanner.py | |
| M2.5 | report_builder 扩展测试 | OK | tests/test_tianzheng_interface_report_builder.py | |
| M2.6 | dry_run 扩展测试 | OK | tests/test_tianzheng_interface_dry_run_engine.py | |
| M2.7 | 运行 pytest | OK | pytest -q | |

---

## Phase M3：MCP 集成与手动验证

**状态：OK 已完成**
**前置：Phase M2 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| M3.1 | MCP tools 骨架 + schema + 7 个工具 | OK | server.py | 3 个新工具 |
| M3.2 | intent mapper + 安全模块 | OK | scripts/manual_tianzheng_scan.py | |
| M3.3 | 48 个 M3 测试 | OK | scripts/manual_dry_run_report.py | |
| M3.4 | target.dwg 验证 | -- | !! 禁止 |
| M3.5 | manual validation protocol | OK | examples/water_supply_semantic_model_sample.json | |
| M3.6 | 593 passed + 7 预存 | OK | pytest -q | |

---

## Phase M4：文档化与工程基础设施

**状态：OK 已完成**
**前置：Phase M3 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| M4.1 | 更新 README.md | OK | README.md | |
| M4.2 | 创建 API 文档 | OK | docs/tianzheng_interface_api.md | |
| M4.3 | 创建架构总览 | OK | docs/architecture_overview.md | |
| M4.4 | 确认依赖完整 | OK | requirements.txt | |
| M4.5 | 全部编译通过 | OK | 全量 | |

---

## Phase C1：命令注册表种子导入 **OK 已完成**
**新增**: 119 命令 (88 plumbing + 31 hvac)
| C1.1 | Seed 导入 + 拆分 | OK |
| C1.2 | command_resolver.py | OK |
| C1.3 | validate_registry.py | OK |
| C1.4 | 24 个 C1 测试 | OK |
---

Phase D1：交付文档

**状态：OK 已完成**
**前置：Phase M4 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| D1.1 | 用户使用指南 | -- | docs/user_guide.md | |
| D1.2 | 部署指南 | -- | docs/deployment_guide.md | |

---

## Phase D2：变更日志与版本管理

**状态：OK 已完成**
**前置：Phase D1 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| D2.1 | 创建 CHANGELOG | -- | CHANGELOG.md | |
| D2.2 | 版本号确定 | -- | -- | |

---

## Phase E1：示例数据与演示

**状态：OK 已完成**
**前置：Phase D2 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| E1.1 | 整理 examples | -- | examples/ | |
| E1.2 | 演示脚本 | -- | examples/demo_workflow.py | |
| E1.3 | 演示输出 | -- | examples/demo_output.md | |

---

## Phase E2：最终验收

**状态：OK 已完成**
**前置：Phase E1 完成**

| # | 任务 | 状态 | 文件 | 备注 |
|---|------|------|------|------|
| E2.1 | 全量 pytest | -- | pytest -q | |
| E2.2 | 代码检查 | -- | python -m py_compile | |
| E2.3 | 安全审计 | -- | 全量 | |
| E2.4 | 最终验收报告 | -- | reports/final_acceptance_report.md | |

---

## 任务统计

| 阶段 | 总任务 | 已完成 | 进行中 | 待开始 | 阻塞 |
|------|--------|--------|--------|--------|------|
| M0 | 8 | 5 | 1 | 2 | 0 |
| M1 | 7 | 7 | 0 | 0 | 0 |
| M2 | 7 | 7 | 0 | 0 | 0 |
| M3 | 6 | 5 | 0 | 1 | 0 |
| M4 | 5 | 5 | 0 | 0 | 0 |
| D1 | 2 | 0 | 0 | 2 | 0 |
| D2 | 2 | 0 | 0 | 2 | 0 |
| E1 | 3 | 0 | 0 | 3 | 0 |
| E2 | 4 | 0 | 0 | 4 | 0 |
| 总计 | 52 | 40 | 0 | 11 | 1 |`n`n**R1**: AutoCAD 25.1s 连接成功，天正给排水 T30 V1.0 已加载`n`n**C1-C3.1 总计**: 67 tests passed`n`n**C3 发现**: 23 命令 (6P+17H) 从本地安装目录匹配

---

## 并发 Agent 任务分配（建议）

| Agent | 负责文件 | 阶段 |
|-------|----------|------|
| command_registry_agent | 已有文件 | 其他 |
| cad_bridge_agent | 已有文件 | 其他 |
| safety_audit_agent | 已有文件 | 其他 |
| test_agent | 已有文件 | 其他 |
| docs_agent | 已有文件 | 其他 |
| planning_agent | ROADMAP.md / TASK_BOARD.md / reports/ | M0 |
| M1 开发 agent | scanner.py / report_builder.py / config / examples | M1 |
| M2 开发 agent | action_schema / dry_run_engine / proxy_handler / tests | M2 |
| M3 集成 agent | server.py / scripts / examples | M3 |
| M4 文档 agent | README / API docs / architecture | M4 |
| E2 验收 agent | pytest / 安全审计 / 验收报告 | E2 |

---

## Phase MCP-UPGRADE-HANDOFF：DeepSeek 升级版 MCP 接口接管验收与受控主线吸收

**状态：XX `MCP_UPGRADE_HANDOFF_PARTIAL`（Mock-only 基线已交付，阶段未完全完成）**  
**负责人：Manager 统一调度；各子 Agent 按文件边界执行**  
**开始：2026-07-14 | 完成：未完成，不得提前推进后续阶段**

### 全阶段硬边界

| 项目 | 当前值 |
|---|---|
| `production_d1_allowed` | `false` |
| AutoCAD/天正/COM | `!! 禁止连接、启动或调用` |
| DWG | `!! 禁止打开、读取、修改、保存` |
| P4.1 / Production D1 | `!! 禁止执行` |
| 允许测试 | Python/.NET 编译、单元/集成/Mock、local loopback |
| 主线吸收方式 | 接口、adapter、兼容层；禁止整体覆盖 |

### A. 规划与交付盘点

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-PLAN-001 | 固化阶段目标、依赖、安全门和验收条件 | planning_agent | 无 | OK | `ROADMAP.md`、`TASK_BOARD.md` |
| MUH-INV-001 | 递归盘点实验项目目录树、Git、入口、包、.NET、配置和文档 | docs_agent | MUH-PLAN-001 | OK | inventory JSON/Markdown 已生成 |
| MUH-INV-002 | 识别 MCP tools/resources/prompts、transport、runtime、backend、job/journal/safety/idempotency | docs_agent | MUH-INV-001 | OK | 已按真实代码盘点 |
| MUH-INV-003 | 列出未提交文件、最近提交、示例、Schema 与测试分类 | docs_agent | MUH-INV-001 | OK | 实验目录非 Git 仓库；未修改实验项目 |

### B. 原样测试复现

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-TEST-001 | 记录 Python/.NET/依赖/OS 环境 | test_agent | MUH-INV-001 | OK | `original_test_results.json` |
| MUH-TEST-002 | 修改前运行 Python 编译、静态导入、Schema 解析 | test_agent | MUH-INV-003 | OK | 原始证据已固化 |
| MUH-TEST-003 | 修改前运行项目自带全部测试及示例 | test_agent | MUH-INV-003 | OK | 75 collected / 69 passed / 6 failed |
| MUH-TEST-004 | 单列 mock transport/backend 与 job/journal/safety 原始结果 | test_agent | MUH-TEST-003 | OK | 原始失败已留证 |

### C. 五层验收与安全审计

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-ARCH-A | Layer A 控制服务器、Schema、生命周期、job/progress/capability 审计 | command_registry_agent | MUH-TEST-002 | OK | ACCEPT_WITH_ADAPTATION |
| MUH-ARCH-B | Layer B loopback、鉴权、版本、framing、大小、并发、replay、shutdown 审计 | cad_bridge_agent | MUH-TEST-004 | OK | ACCEPT_WITH_ADAPTATION |
| MUH-ARCH-C | Layer C Mock 生命周期、上下文、调度、取消、进度、失败模拟审计 | cad_bridge_agent | MUH-TEST-004 | OK | ACCEPT_WITH_ADAPTATION；仅 Mock |
| MUH-ARCH-D | Layer D 状态机、journal、checkpoint/resume、approval、crash recovery 审计 | safety_audit_agent | MUH-TEST-004 | OK | REJECT 原样迁移；仅隔离重写基线 |
| MUH-ARCH-E | Layer E backend 抽象、identity/hash/protected region/failure injection 审计 | cad_bridge_agent | MUH-TEST-004 | OK | ACCEPT_WITH_ADAPTATION；不替换真实执行器 |
| MUH-SEC-001 | 扫描 16 类安全硬阻断项并逐项给出 file/line/remediation | safety_audit_agent | MUH-INV-002 | OK | 19 项发现已记录 |
| MUH-SEC-002 | 对迁移候选作准入裁决 | safety_audit_agent | MUH-ARCH-A 至 E、MUH-SEC-001 | OK | CONDITIONAL_NEXTGEN_BASELINE_ONLY / HIGH |

### D. 正式项目对照与接入决策

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-CMP-001 | 对照 server/transport/schema/job/journal/checkpoint/safety/backend 等能力 | 各域 Agent，Manager 汇总 | MUH-ARCH-A 至 E | OK | `current_project_comparison.json` |
| MUH-CMP-002 | 逐模块确定直接接受、适配、延期、拒绝 | Manager | MUH-CMP-001、MUH-SEC-002 | OK | ACCEPT_AS_IS 源文件为 0 |
| MUH-CMP-003 | 固化 migrated/rejected/deferred 文件清单 | Manager | MUH-CMP-002 | OK | 53 基线、22 拒绝条目、19 延期/开放项 |

### E. 协议、安全基线与受控迁移

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-PROTO-001 | 统一 12 类核心结构及 `schema_version` | command_registry_agent | MUH-CMP-002 | OK | 协议 `1.0.0` |
| MUH-PROTO-002 | 定义 L0-L4 审批及 job/identity/plan/operations/expiry 绑定 | safety_audit_agent | MUH-PROTO-001 | OK | L4/Production D1 禁止；持久消费仍开放 |
| MUH-JOB-001 | 接纳或适配 job/journal/checkpoint 原子与可核验机制 | cad_bridge_agent | MUH-PROTO-002、MUH-SEC-002 | XX | NextGen 定向覆盖通过；全字段互校验/跨进程安全未关闭 |
| MUH-MIG-001 | 迁移已接受模块并保留来源、版本和兼容说明 | 对应域 Agent | MUH-SEC-002、MUH-CMP-003 | OK | 53 个受控基线文件，无原样复制 |
| MUH-ADAPT-001 | 实现 `LegacyCadBackendAdapter` 或等价兼容层 | cad_bridge_agent | MUH-PROTO-001、MUH-MIG-001 | OK | DISABLED_CONTRACT_ONLY；执行禁用 |
| MUH-MIG-002 | 隔离拒绝模块并建立明确延期 TODO | 对应域 Agent | MUH-CMP-003 | OK | 拒绝与延期清单已固化 |

### F. 测试、文档与最终验收

| ID | 任务 | 负责人 | 前置 | 状态 | 交付物/备注 |
|---|---|---|---|---|---|
| MUH-REG-001 | 新增 30 项 nextgen/安全/恢复/Mock/adapter 测试 | test_agent | MUH-JOB-001、MUH-ADAPT-001 | OK | NextGen 47/47，通过且未读取 DWG |
| MUH-REG-002 | 新增 P4.1 checkpoint 硬编码问题回归测试 | test_agent | MUH-JOB-001 | OK | NextGen 已覆盖；正式 P4.1 冻结、未修复 |
| MUH-REG-003 | 运行正式项目原有测试、新增测试和全量回归 | test_agent | MUH-REG-001、MUH-REG-002 | XX | 1554/1561、7 失败；发生 3 个 DWG 只读读取违规 |
| MUH-DOC-001 | 生成 `docs/mcp_nextgen/00` 至 `07` 文档 | docs_agent | MUH-CMP-003、MUH-MIG-001 | OK | 8 份文档已生成，Real plugin 标为未实现 |
| MUH-FINAL-001 | 汇总全部 artifacts 和 24 项最终汇报 | Manager | MUH-REG-003、MUH-DOC-001、所有 outbox | OK | 最终报告 JSON/Markdown 已生成 |
| MUH-FINAL-002 | 按四种允许状态作最终裁决 | Manager | Safety 放行、全量测试、文档完成 | OK | 裁决为 MCP_UPGRADE_HANDOFF_PARTIAL，不代表阶段完成 |

### 当前阶段统计

| 总任务 | 已完成 | 进行中 | 待开始 | 阻塞 |
|---:|---:|---:|---:|---:|
| 30 | 28 | 0 | 0 | 2 |

### 阶段门状态

| 阶段门 | 状态 | 放行条件 |
|---|---|---|
| 原始证据门 | OK | 原始 69/75，失败证据完整 |
| 安全门 | XX | CONDITIONAL_NEXTGEN_BASELINE_ONLY / HIGH；3 Open、5 Deferred |
| 迁移门 | OK | 53 个受控基线文件；原样复制 0 |
| 恢复门 | XX | NextGen 覆盖通过，但审批消费、跨进程幂等/锁、全字段互校验未关闭 |
| 全量回归门 | XX | 1554/1561、7 失败；SEC-FINAL-019 边界违规 |
| 最终状态门 | XX | 已裁决 PARTIAL；阶段未完全完成，不推进下一阶段 |

### 安全开放、延期与回归待办

| 项目 | 状态 | 证据/要求 |
|---|---|---|
| SEC-FINAL-019 | XX HIGH / OPEN | 全量测试只读 SHA-256 读取 3 个真实 DWG；先用假文件/依赖注入隔离，再重跑 |
| FastMCP 鉴权/loopback/replay 强制接线 | XX OPEN | 禁止绕过 dispatcher，禁止启用实际 listener |
| single-use approval 持久原子消费 | XX OPEN | 当前只有合同/校验，不得启用真实执行 |
| idempotency crash window / 跨进程锁 | XX OPEN/DEFERRED | 需持久占用与 fencing |
| checkpoint/journal 全字段互校验 | XX OPEN | 不得以 NextGen 47/47 代替安全闭环 |
| 5 个 GBK/UTF-8 旧测试失败 | -- 待办 | 修复后才可形成合规全量回归候选 |
| 正式 P4.1 checkpoint/resume 适配 | -- 延期 | P4.1 未运行、冻结、未宣告修复 |
| Real/plugin/COM/Legacy enablement/Production D1 | -- 延期 | 未实现；Legacy 保持 disabled，`production_d1_allowed=false` |

### 收口测试与安全记录

| 项目 | 结果 |
|---|---|
| DeepSeek 原始测试 | 69/75，6 失败 |
| NextGen 定向测试 | 47/47，通过；仅 Mock-only |
| 全量回归 | 1554/1561，7 失败、1 warning；不合规 |
| DWG 边界 | 先前全量测试只读读取 3 个 DWG；未修改/保存，但已违规 |
| AutoCAD/天正/COM/P4.1 | 本阶段均未连接或运行 |
| Legacy adapter | DISABLED_CONTRACT_ONLY |
| Real/plugin/Production D1 | 未实现、未授权 |
| 最终状态 | `MCP_UPGRADE_HANDOFF_PARTIAL` |
