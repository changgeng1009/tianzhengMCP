# 本机安装目录命令来源发现计划

> Phase C2 — 仅设计，不执行扫描 | Production D1 blocked

## 概述

基于 Phase C1 导入的 119 条 public snippet seed 命令，制定从用户本机天正安装目录发现真实命令来源的安全计划。C2 只生成计划，不执行任何扫描操作。

## 当前状态

- **Seed 命令数**: 119 (88 plumbing + 31 hvac)
- **命令来源**: 全部为 public_snippet / seed
- **已确认命令**: 0
- **本机扫描**: 未执行 (local_installation_scanned=false)

## 目标文件类型

### 允许只读发现的文件

| 文件类型 | 位置模式 | 提取方法 | 风险 |
|----------|----------|----------|------|
| `acad.pgp` | `{tianzheng}/sys/acad.pgp` | 纯文本解析 `别名=命令` | 低 |
| `*.tmn` | `{tianzheng}/sys/tch.tmn` 等 | 文本提取菜单命令 | 低 |
| `*.mnu/*.cuix/*.cui` | `{tianzheng}/sys/*.mnu` | XML/文本解析菜单宏 | 低 |
| `help/*.chm/*.html` | `{tianzheng}/help/` | 文本提取命令名 | 低 |
| `*.lsp` (仅 grep) | `{tianzheng}/lisp/` 等 | grep `defun c:xxx` | 中 |
| `*.fas/*.vlx` (仅记名) | `{tianzheng}/sys/` | 仅记录文件名 | 中 |

### 严格禁止的操作

- 执行任何文件 (LISP/FAS/VLX/EXE/DLL/SCR)
- 加载 CUIX/MNU/CUI 菜单
- NETLOAD DLL
- SendCommand 探测
- 启动或连接 AutoCAD
- 打开任何 DWG

## 命令状态模型

```
public_snippet → seed → local_discovered → local_verified → sandbox_verified → confirmed_for_sandbox

任何状态都禁止: production_confirmed, production_allowed
```

| 状态 | 含义 | 可确认 | 可 production |
|------|------|--------|-------------|
| public_snippet | 公开网页片段 | 否 | 否 |
| seed | 结构化注册表 | 否 | 否 |
| local_discovered | 本机匹配到 | 否 | 否 |
| local_verified | 静态签名一致 | 否 | 否 |
| sandbox_verified | Sandbox 测试通过 | 否 | 否 |
| confirmed_for_sandbox | Sandbox 可用 | 是 | 否 |
| production_forbidden | 永久禁止 | 否 | 否 |

## Phase C3 前置条件

进入 C3 之前必须满足:
1. 用户明确批准: "我批准 Phase C3 只读扫描天正安装目录，不连接 AutoCAD，不打开 DWG，不执行命令。"
2. 用户提供天正安装根目录路径
3. 所有 C1/C2 测试通过
4. 安全审计通过

## 安全约束

- `local_installation_scanned=false`
- `d1_allowed=false`
- `production_d1_allowed=false`
- 所有命令 `allow_production=false`
