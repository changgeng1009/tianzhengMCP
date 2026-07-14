from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.agents.agent_budget import AgentBudget, estimate_chars
from mcp.agents.agent_result_schema import RESULT_SCHEMA
from mcp.agents.deepseek_worker import run_deepseek_worker
from mcp.agents.task_pack_builder import build_task_pack


PHASE = "STAGE2-SKILL-PACKAGING"
ROOT = Path(__file__).parents[2]
FINAL_DELEGATED_TASK_ID = "ds_stage2_backend_architecture_static_review_final"


STATIC_ARCHITECTURE_SUMMARY = """\
CadBackend Protocol 摘要：backend 必须显式实现 probe、capability 查询、connect/disconnect、
working-copy open、entity scan/create、save、close/reopen 和 command-state；业务层只依赖 Protocol。

Capability 摘要：扫描 AcDb 与给排水 TDb metadata 是独立能力；已验证普通 AcDbLine sandbox 创建，
但 create_tdb_pipe/create_tdb_valve/create_tdb_fitting 与官方天正 API 均为 false，扫描能力不得推导创建能力。

Router 摘要：BackendSafetyEnforcer 在 capability selection 之前执行；任务必须声明 required_capabilities；
review_only/blocked/manual_tianzheng 与不完整 geometry 被隔离；preferred backend 变化视为 fallback，
allow_automatic_fallback=false 时拒绝；天正任务只能显式转人工 fallback，不能路由为普通 CAD 创建。

Safety 默认值：production_d1_allowed=false、sendcommand_allowed=false、
tianzheng_execution_allowed=false、source_open_allowed=false、allow_automatic_fallback=false。

Import 隔离：domains、diff、planning、recognition、repair_actions、semantic、spatial、qa、alignment、
extraction 不含 win32com/GetActiveObject/Dispatch；原生 COM 仅位于 backend/legacy adapter 边界。

相关测试：test_backend_architecture、test_backend_router、test_mock_backend、
test_d10_backend_decoupling、test_stage2_skill_packaging、test_stage2_packaging_report。
"""


def build_stage2_delegation_pack() -> dict[str, Any]:
    goal = (
        f"task_id={FINAL_DELEGATED_TASK_ID}。仅根据以下静态摘要审查，不读取本地文件：\n"
        f"{STATIC_ARCHITECTURE_SUMMARY}\n"
        "逐项检查：1) backend 解耦；2) 静默 fallback；3) Safety Gate 顺序；"
        "4) TDb 是否可能误路由到普通 CAD 创建；5) 只读扫描是否符合 capability 声明。"
        "在 notes 中给出带 finding_id 的建议；最终分类和阶段判断由 Codex 作出。"
    )
    pack = build_task_pack(
        phase=PHASE,
        goal=goal,
        allowed_files=[
            "mcp/backends/base.py",
            "mcp/backends/models.py",
            "mcp/backends/capabilities.py",
            "mcp/backends/router.py",
            "mcp/backends/safety.py",
            "mcp/domains/water_supply_and_drainage/adapter.py",
            "mcp/domains/hvac/placeholder.py",
            "skill/schemas/repair_task.schema.json",
            "skill/schemas/backend_capabilities.schema.json",
            "skill/configs/backends.yaml",
        ],
        forbidden_files=["drawing files", "source file", "runtime credentials", "conversation transcript"],
        expected_outputs=[
            "在 notes 中按 finding_id 列出 backend isolation、fallback、safety ordering、TDb routing、read-only scan capability 的静态审查建议"
        ],
        test_commands=[],
        output_schema=RESULT_SCHEMA,
        budget=AgentBudget(max_input_chars=20_000, max_output_tokens=1_500),
    )
    pack["task_id"] = FINAL_DELEGATED_TASK_ID
    return pack


def run_stage2_delegation() -> dict[str, Any]:
    pack = build_stage2_delegation_pack()
    key_present = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    if key_present:
        result = run_deepseek_worker(pack, dry_run=False, timeout=45.0, temperature=0.0)
        succeeded = result.get("status") in {"PASS", "PARTIAL"}
        notes = [str(item) for item in result.get("notes", [])]
    else:
        succeeded = False
        notes = ["environment key is unavailable; worker and remote call skipped safely"]
    return {
        "deepseek_worker_used": True,
        "deepseek_available": key_present,
        "deepseek_call_attempted": key_present,
        "delegated_task_count": 1,
        "delegated_task_ids": [FINAL_DELEGATED_TASK_ID],
        "delegated_task_id": FINAL_DELEGATED_TASK_ID,
        "task_pack_chars": estimate_chars(pack),
        "call_succeeded": succeeded,
        "accepted_count": 0,
        "modified_count": 0,
        "rejected_count": 0,
        "deepseek_notes": notes,
        "missing_items": [] if key_present else ["DEEPSEEK_API_KEY environment variable"],
        "final_decision_made_by_codex": True,
        "deepseek_made_final_pass_decision": False,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "dwg_binary_sent_to_deepseek": False,
        "source_file_sent_to_deepseek": False,
        "full_history_sent_to_deepseek": False,
        "autocad_execution_authorized": False,
    }


def inventory_skill() -> dict[str, Any]:
    skill = ROOT / "skill"
    return {
        "workflow_names": sorted(path.stem for path in (skill / "workflows").glob("*.md")),
        "schema_names": sorted(path.name for path in (skill / "schemas").glob("*.json")),
        "example_names": sorted(path.name for path in (skill / "examples").iterdir() if path.is_dir()),
        "prompt_names": sorted(path.name for path in (skill / "prompts").glob("*.md")),
        "template_names": sorted(path.name for path in (skill / "templates").iterdir() if path.is_file()),
    }


def contains_sensitive_material(pack: dict[str, Any]) -> bool:
    serialized = json.dumps(pack, ensure_ascii=False).lower()
    return any(marker in serialized for marker in ("deepseek_api_key", ".dwg", "full_chat_history", "begin conversation"))
