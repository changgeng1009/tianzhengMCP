# 天正 CAD MCP 接口系统

基于 MCP (Model Context Protocol) + Python COM 的天正给排水 / 暖通 CAD 软件接口系统。

> **公开分发样例说明**：真实课程/工程图纸及参考 PDF/图片已从当前版本移除。内置命令注册表现为禁用执行的原创合成测试数据，不再提供原第三方命令汇编。接口架构保留，实际使用需自行提供有权使用的数据并另行授权执行。历史报告不是当前版本真机验收。参见 [公开样例与授权边界](docs/public_sample_distribution.md)。

## 当前阶段

**Phase M4** — 文档化与工程基础设施（已完成 M0/M1/M2/M3-prep）

| 阶段 | 状态 | 说明 |
|------|------|------|
| M0 | ✅ | Multi-Agent 协作基础设施 |
| M1 | ✅ | DWGScanner + ReportBuilder |
| M2 | ✅ | ActionBatch + ConflictDetector + ProxyDiscovery |
| M3-prep | ✅ | MCP 7 工具骨架 + 安全门控 + 意图映射 |
| M4 | ✅ | 本文档化阶段 |
| Production D1 | ❌ BLOCKED | d1_allowed=false |

> **安全状态**: d1_allowed=false, production_d1_allowed=false, source_modification_allowed=false。所有操作限制在 dry-run / preparation 阶段。真实执行需要用户明确批准。

## 目录结构
```
tianzheng_interface/       # 天正接口层 (M1-M2)
├── model.py               # 10 个富数据类型
├── action_schema.py       # Action + ActionBatch + ConflictType
├── proxy_handler.py       # 实体分类器 + ProxyDiscovery
├── dry_run_engine.py      # ConflictDetector + 增强引擎
├── scanner.py             # DWGScanner 一键扫描器
├── report_builder.py      # Markdown+JSON 双格式报告

mcp/
├── bridge/                # MCP 工具层 (M3-prep)
│   └── mcp_tools.py       # 7 个 MCP 工具
├── safety/                # 安全模块 (M3-prep)
│   ├── mcp_errors.py      # 15 个错误码
│   └── mcp_safety.py      # 安全门控
├── intent/                # 意图映射 (M3-prep)
│   └── intent_mapper.py   # 12 种意图模板
└── ...

cad/                       # AutoCAD COM 通信层
tianzheng/                 # 天正核心模块
config/                    # 系统类型 + Action 模板配置
tests/                     # 48 (M3) + 21 (M2) + 18 (M1) 新测试
docs/                      # API + 架构 + 验证协议
reports/                   # 阶段报告
```

## 测试状态
```
全量: 593 passed / 600 total (7 预存失败)
M3: 48 tests | M2: 21 tests | M1: 18 tests
```

## 安全
所有操作默认禁用。d1_allowed=false, source_modification_allowed=false。
14 个安全字段全部 false。禁止标志自动检测。详见 SAFETY_POLICY.md

## 许可证

MIT 许可仅覆盖 [原创源码清单](LICENSED_SOURCE_FILES.txt) 中逐项列明的文件，版权人为
Copyright (c) 2026 Yi Wei。完整标准正文见 [LICENSE](LICENSE)，适用范围与排除材料见
[LICENSE_SCOPE.md](LICENSE_SCOPE.md)。仓库整体、独立文档/提示词/报告、配置与样例数据
以及第三方材料不自动纳入该许可；已有第三方声明与各依赖的许可继续适用。
