# Task for safety_audit_agent
## Assigned by: Manager
## Phase: CAD-BASELINE-REFREEZE
## Task ID: CAD-BASELINE-REFREEZE-SAFETY-AUDIT
## Run ID: 20260714T220937+0800

## Task Description
审计当前 `AGENTS.md` 相对旧安全基线与 Git HEAD 的语义差异，判断是否存在安全降级，并只读复核旧基线完整性与源码漂移范围。

## Input Files
- `AGENTS.md` 当前工作区版本与 Git 历史对象
- `artifacts/cad_safe_test_baseline/20260714T193554+0800_s2_1` 中 JSON、Markdown、校验清单
- 正式安全基线 verifier

## Constraints
- 仅允许读取文本、Git 对象和基线 JSON/Markdown。
- 严禁读取、解析、扫描或哈希任何 DWG/DXF。
- 不修改 `AGENTS.md`、旧基线或业务源码。
- 不运行 pytest，不连接 AutoCAD、天正或 COM。
- 旧基线 `AGENTS.md` 必须通过 Git 历史 blob 的 SHA256 精确匹配，不得猜测。

## Expected Output
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/git_state.json`
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/agents_md_old_new_hashes.json`
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/agents_md_semantic_diff.md`
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/agents_md_security_review.json`
- `artifacts/baseline_refreeze_after_agents_update/20260714T220937+0800/explained_source_drift.json`
- `agent_outbox/safety_audit_agent_report.md`
# Task for safety_audit_agent
## Assigned by: Manager
## Phase: CAD-CONFIG-S2
## Task ID: CAD-CONFIG-S2-PRECHECK-001

## Task Description
对 CAD-CONFIG-S2 开始前的 Git 工作区进行只读预存变更审计。阶段 run_id 为 `20260715T113724+0800_s2`。权威安全基线为 `CAD-SAFE-20260714T220937+0800`，最终 SHA256 为 `87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff`，正式 verifier 已由 Manager 运行并返回 exit 0、source/checksum/closure PASS。

必须捕获并保存：
- `git status --porcelain=v1 --untracked-files=all` 原始记录；
- tracked 文件清单；
- untracked 文件清单；
- 每个预存变更的路径、状态、解释分类和证据；
- `s2_preexisting_worktree_changes.json`；
- `baseline_precheck.json`；
- 对现有 Manifest/Schema/CLI 的只读审计摘要 `existing_manifest_audit.json`。

允许的预存变更仅限：
1. 本阶段开始前的 Agent 协作记录；
2. 统一 Skill 安全基线引用更新；
3. 当前 `AGENTS.md` 安全治理扩展；
4. 已完成安全基线重新冻结阶段产生并在用户说明中明确保留的合法报告/基线产物。

若发现其他路径，必须列入 `unexplained_changes`，不得自行修复或删除。最终裁决仅可为 `APPROVE_S2_IMPLEMENTATION` 或 `CAD_CONFIG_S2_BLOCKED_BY_UNEXPLAINED_PREEXISTING_CHANGE`。

## Input Files
- `D:\CodexWork\天正\AGENTS.md`
- `D:\CodexWork\天正\artifacts\baseline_refreeze_after_agents_update\20260714T220937+0800`
- `D:\CodexWork\天正\artifacts\cad_safe_test_baseline\20260714T220937+0800`
- Git index/worktree metadata

## Constraints
- 只读 Git 审计；不得恢复、覆盖、删除或清理任何现有变更。
- 不得读取、解析、扫描或哈希任何 DWG/DXF。
- 不得连接 AutoCAD、天正或 COM；不得启动任何外部集成。
- 不得实施 S2 代码。
- 文本读取显式 UTF-8。

## Expected Output
- `D:\CodexWork\天正\artifacts\cad_config_driven_s2\20260715T113724+0800_s2\baseline_precheck.json`
- `D:\CodexWork\天正\artifacts\cad_config_driven_s2\20260715T113724+0800_s2\s2_preexisting_worktree_changes.json`
- `D:\CodexWork\天正\artifacts\cad_config_driven_s2\20260715T113724+0800_s2\existing_manifest_audit.json`
- `D:\CodexWork\天正\agent_outbox\safety_audit_agent_report.md`

## User Resolution Addendum

用户已明确确认 `D:\CodexWork\天正\暖通课程设计\**` 下 199 条 tracked 删除均为 S2 开始前的合法预存变化。请仅基于已有 Git 元数据更新证据，不重新扫描或读取被删除文件内容。

对每条记录设置：
- `git_status = "D"`
- `classification = "INTENTIONAL_PREEXISTING_DELETION"`
- `existed_before_s2 = true`
- `excluded_from_s2_changes = true`
- `user_confirmed = true`

重新生成：
- `s2_preexisting_worktree_changes.json`
- `s2_preexisting_change_resolution.json`

新裁决必须反映：总计 214、原已解释 15、新确认合法删除 199、未解释 0、`preexisting_change_gate = "PASS"`。不得恢复文件、扩大删除、提交或推送，不得访问其中任何 DWG/DXF 内容。

## S2 Start Snapshot Task

### Task ID: CAD-CONFIG-S2-SNAPSHOT-002

在任何 S2 实现修改开始前，生成 `source_change_manifest.json` 的 before snapshot。只纳入允许的源码、测试、Schema、JSON、Markdown 和配置文件；排除 DWG/DXF、`output`、CAD 二进制、cache、`.git`、临时文件、安装目录、冻结基线和所有已登记预存变化。可以对允许的非 CAD 文本/源码文件计算 SHA256，严禁对任何 DWG/DXF 计算哈希。

同时生成 `configuration_layer_matrix.json`，记录六层配置优先级及不可放宽安全字段。输出中标记 `snapshot_complete=true`、`s2_implementation_gate=PASS`，否则列出 blocker。
