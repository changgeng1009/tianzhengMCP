# Task for test_agent
## Assigned by: Manager
## Phase: CAD-SAFETY-S2.1
## Task ID: CAD-SAFETY-S2.1-GUARD

## Task Description

建立项目级默认启用的真实 CAD 文件访问守卫、子进程审计、pytest marker 注册、纯 synthetic fixtures 及守卫自身测试，为关闭 `SEC-FINAL-019` 提供可重复的零访问安全基线。

## Input Files

- `pytest.ini`
- `tests/conftest.py`
- `tests/**`
- `mcp_nextgen/**`
- `skills/autocad-tianzheng-automation/**`

## Constraints

- 禁止连接或启动 AutoCAD、天正、COM。
- 禁止打开、读取、扫描、哈希、修改、移动或删除任何现存 DWG/DXF。
- 禁止运行 P4.1、真实后端、外部集成测试及默认全量回归。
- 不修改 P2、P3、P4.1 业务执行逻辑。
- 当前只允许运行守卫专项自测；NextGen、Skill 和默认回归等待 Manager 放行。
- synthetic CAD 扩展测试文件只能在 pytest 临时目录动态生成随机内容并显式注册。
- 所有文本读写显式使用 UTF-8。

## Expected Output

- `tests/safety/real_cad_access_guard.py`
- 项目级 pytest guard 插件与 marker 政策
- `tests/safety/test_real_cad_access_guard.py`
- `tests/fixtures/synthetic_cad_identity/**`（仅非 CAD 扩展）
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/file_access_guard_implementation.json`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/file_access_guard_test_results.json`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/subprocess_guard_test_results.json`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/default_test_file_access_log.jsonl`
- `artifacts/sec_final_019_closure/20260714T193554+0800_s2_1/default_test_file_access_summary.json`

## Dependency / Stop Rule

守卫专项自测完成后停止并向 Manager 汇报，不自行运行 NextGen、Skill、旧失败测试或默认安全回归。
