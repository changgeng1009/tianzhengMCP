# 天正 CAD MCP 接口系统 — 架构总览

> Phase M4 | 最后更新：2026-07-08

## 系统分层

```
┌──────────────────────────────────────────────┐
│                 MCP Client (Codex)           │
├──────────────────────────────────────────────┤
│              server.py (MCP Server)          │
├──────────────┬───────────────┬───────────────┤
│ mcp/bridge   │ mcp/safety    │ mcp/intent    │  ← M3-prep
│ 7 MCP tools  │ gate + errors │ intent mapper │
├──────────────┴───────────────┴───────────────┤
│         tianzheng_interface/                  │  ← M1-M2
│  model | scanner | report | dry_run | proxy  │
├──────────────────────────────────────────────┤
│  tianzheng/  │  cad/  │  pipe_network/       │  ← 核心层
│  environment │  COM   │  graph_builder       │
│  semantic    │  conn  │                       │
├──────────────────────────────────────────────┤
│           AutoCAD COM (disabled)             │  ← Phase M4 禁止
│           天正 T30 V1.0 (disabled)           │
└──────────────────────────────────────────────┘
```

## 数据流

```
用户输入 (NL) → IntentMapper → MCP Tool → ActionDefinition
                                              ↓
                                    EnhancedDryRunEngine
                                              ↓
                              DryRunResult + Conflicts
                                              ↓
                               ReportBuilder → Markdown/JSON
```

## 安全分层

```
L0: 代码层隔离 — dry_run / sandbox 默认
L1: Schema 验证 — action_schema.py 校验
L2: MCP Gate — mcp_safety.py 禁止标志检测
L3: Safety Policy — SAFETY_POLICY.md 全局规则
L4: 用户确认 — 审批短语 "我批准真实执行"
```

## 模块依赖

```
mcp_tools.py
├── tianzheng_interface.model
├── tianzheng_interface.action_schema
├── tianzheng_interface.dry_run_engine
├── tianzheng_interface.scanner
├── tianzheng_interface.report_builder
├── mcp.safety.mcp_errors
└── mcp.safety.mcp_safety

scanner.py
├── tianzheng_interface.model
└── tianzheng_interface.proxy_handler

dry_run_engine.py
└── tianzheng_interface.action_schema

proxy_handler.py (M2)
└── standalone classifier + discovery
```

## 测试覆盖

| 层级 | 测试文件 | 数量 |
|------|----------|------|
| M3 MCP tools | test_m3_mcp_tools.py | 18 |
| M3 safety | test_m3_mcp_safety.py | 11 |
| M3 intent | test_m3_intent_mapper.py | 12 |
| M3 no-real | test_m3_no_real_execution.py | 10 |
| M2 extended | test_phase_m2_extended.py | 21 |
| M1 scanner | test_tianzheng_interface_scanner.py | 8 |
| M1 report | test_tianzheng_interface_report_builder.py | 10 |
| 接口层 | test_tianzheng_interface_*.py | 67 |
| 其他 | 100+ | 436+ |
| **总计** | | **593 passed** |

## 阶段完成度

| 阶段 | 任务 | 完成 |
|------|------|------|
| M0 | Multi-Agent 基础设施 | 8/8 ✅ |
| M1 | 接口层完整化 | 7/7 ✅ |
| M2 | Action/Dry-run 增强 | 7/7 ✅ |
| M3-prep | MCP 骨架 | 5/6 ✅ |
| M4 | 文档化 | 5/5 ✅ |
| **总计** | | **32/44 (73%)** |
