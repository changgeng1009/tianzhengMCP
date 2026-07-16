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

## Mid-Implementation Safety Audit

### Task ID: CAD-CONFIG-S2-SAFETY-MID-003

只读审计 WP1/WP2/WP3 当前实现，确认：
- 无 COM/CAD/Tianzheng/Real backend 连接或启动路径；
- path resolver 不对 CAD 路径执行 open/read/stat/exists/hash/strict resolve；
- Manifest/override 无法提升 production、L3/L4、approval 或 backend availability；
- Mock/Contract/Interface/Placeholder 状态准确；
- 写入 Workflow 只产生 blocked plan；
- 214 条预存变化未被触碰，199 条删除仍排除于 S2 changes。

不得修改实现；输出中间审计结果到 `agent_outbox/safety_audit_agent_report.md` 的追加章节，并列出 BLOCKER 或 PASS。不得读取 CAD 文件内容。

## Unexpected Git State Incident

### Task ID: CAD-CONFIG-S2-GIT-INCIDENT-004

S2 期间检测到未经 Manager 授权的 Git 状态变化：分支由起始 `main` 切换为 `codex/cadskill`，HEAD 由 `854eb0f4f2c155c662ff8e346390216c64003903` 经 `ea7dea21c3a1e71efa3bbfe0350984c61bc1f90b` 变为 `b989d0a1ed227e145060859c7609416c980924b3`。后一个 commit 包含 WP3/docs/tests，前一个 commit 同时包含 S2 WP1/WP2 和用户确认但明确禁止在 S2 提交的 199 条预存删除。三名执行 Agent 均书面声明未执行 git add/commit/push/checkout/switch/merge/rebase。

仅基于 Git 元数据生成：
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/unexpected_git_state_incident.json`
- `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/unexpected_git_state_incident.md`

记录 branch、HEAD、reflog 时间、commit metadata、name-status 分类计数、是否含199条预存删除、upstream/remote-tracking本地可见状态、Agent归因声明、未执行恢复/清理/历史改写、对 S2 source snapshot 的影响。不得读取 commit 中任何 DWG/DXF blob，不得修改 Git、实现或删除状态。最终裁决为 `CAD_CONFIG_DRIVEN_S2_BLOCKED_UNAUTHORIZED_GIT_STATE_CHANGE`。

## User Authorization Revision

### Task ID: CAD-CONFIG-S2-GIT-AUTH-005

用户已明确追认当前分支 `codex/cadskill`、HEAD `b989d0a1ed227e145060859c7609416c980924b3`、提交 `ea7dea21c3a1e71efa3bbfe0350984c61bc1f90b` 与 `b989d0a1ed227e145060859c7609416c980924b3`，以及 `暖通课程设计/**` 下 199 条删除。撤销先前阻断，将状态修订为 `USER_AUTHORIZED_GIT_STATE_CHANGE`。

不得删除原事故记录；向以下文件追加修订：
- `unexpected_git_state_incident.json`
- `unexpected_git_state_incident.md`
- `safety_audit_agent_report.md`
- `s2_preexisting_worktree_changes.json`

生成 `artifacts/cad_config_driven_s2/20260715T113724+0800_s2/user_authorized_git_state_confirmation.json`。199 条删除分类改为 `USER_CONFIRMED_INTENTIONAL_DELETION`，并标记 `authorized_by_user=true`、`occurred_before_current_s2_continuation=true`、`accepted_as_current_repository_state=true`、排除于后续 S2 change manifest。

复核正式 verifier 当前 10 个 source drift 记录，只读取 verifier 输出与非 CAD 路径元数据，不读取任何 DWG/DXF blob。准确记录：verifier overall FAIL、source manifest false、checksum/closure true；若全部漂移仅由用户确认提交和本阶段获批 S2 源变化造成，输出 `authorized_source_drift_only=true`、`git_state_gate=PASS`、`continue_s2=true`。不得把 verifier 本身伪报为 PASS。

## Post-S2 Git and Source Freeze Audit

### Task ID: CAD-POST-S2-FREEZE-GIT-001

冻结目录：`artifacts/post_s2_baseline_freeze/20260716T170858+0800_post_s2`。

仅审计并生成：`git_state_snapshot.json` 与 `source_manifest.json`。记录 branch、HEAD、commit_time、git status、log -1、remote、diff/diff-stat、working tree、authorized changes、uncommitted changes。当前 `codex/cadskill`/`b989d0a...`、两提交及 `暖通课程设计/**` 199 删除均为用户确认状态，不得重新判为事故。

source manifest 仅纳入源码、Schema、测试、Skill、文档、配置和脚本；排除 `.git`、cache、logs、artifacts、临时文件、用户数据、DWG/DXF。每项记录 path/type/SHA256/size/mtime；仅能计算非CAD文件哈希。明确 `real_cad_file_count=0`、`dwg_read_count=0`、`dxf_read_count=0`。

若发现本次冻结开始后新增未解释的源码路径，列出为 blocker；不得修改任何业务源码、Git或CAD文件。更新 safety outbox。
