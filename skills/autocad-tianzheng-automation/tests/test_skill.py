import json
import re
from pathlib import Path

import jsonschema
import pytest

from adapters.generic_autocad import GenericAutoCadAdapter
from adapters.legacy_backend import LegacyComBackend
from adapters.mcp_nextgen import NextGenMcpBackendPlaceholder, NextGenMcpMockBackend
from adapters.original_skill import OriginalRedrawSkillAdapter
from adapters.tianzheng_hvac import TianzhengHvacAdapter
from adapters.tianzheng_water import TianzhengWaterAdapter
from runtime.errors import ProductInstanceConflict, RuntimeModeConflict, UnsafeOperation
from runtime.file_guard import assert_offline_read_allowed
from runtime.planner import build_offline_plan
from runtime.selector import select_runtime
from safety.approval import ApprovalContext, validate_approval

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/project_manifest.schema.json").read_text(encoding="utf-8"))
V1_SCHEMA = json.loads((ROOT / "schemas/project_manifest_v1_0.schema.json").read_text(encoding="utf-8"))


def load_example(name="plain_autocad_redraw.json"):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def frontmatter(path):
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    assert match
    return match.group(1)


def test_01_original_skill_locatable(): assert OriginalRedrawSkillAdapter().locate().is_dir()
def test_02_original_frontmatter_parseable(): assert "name:" in frontmatter(OriginalRedrawSkillAdapter().locate() / "SKILL.md")
def test_03_new_frontmatter_parseable(): assert "name: autocad-tianzheng-automation" in frontmatter(ROOT / "SKILL.md")
def test_04_required_skill_sections():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert all(x in text for x in ["核心边界", "标准流程", "离线入口", "模式与适配器", "必须停止"])
def test_05_plain_mode(): assert select_runtime(load_example()).mode.value == "plain_autocad"
def test_06_water_mode(): assert select_runtime(load_example("tianzheng_water_completion.json")).mode.value == "tianzheng_water"
def test_07_hvac_mode(): assert select_runtime(load_example("tianzheng_hvac_inspection.json")).mode.value == "tianzheng_hvac"
def test_08_auto_detect_conflict():
    manifest = load_example(); manifest["runtime_mode"] = "auto_detect"; manifest["product"] = "auto"
    with pytest.raises(RuntimeModeConflict): select_runtime(manifest)
def test_09_offline_analysis(): assert select_runtime(load_example("offline_pdf_to_cad_plan.json")).product == "offline"
@pytest.mark.parametrize("name", ["plain_autocad_redraw.json", "plain_autocad_compare.json", "tianzheng_water_completion.json", "tianzheng_hvac_inspection.json", "offline_pdf_to_cad_plan.json"])
def test_10_manifest_schema(name):
    manifest = load_example(name)
    schema = V1_SCHEMA if manifest["schema_version"] in {"1.0", "1.0.0"} else SCHEMA
    jsonschema.validate(manifest, schema)
def test_11_no_project_paths_hardcoded():
    for file in (ROOT / "examples").glob("*.json"):
        text = file.read_text(encoding="utf-8")
        assert "D:\\ExampleWorkspace" not in text and "学号" not in text and "姓名" not in text
def test_12_production_default_false(): assert load_example()["production_allowed"] is False
@pytest.mark.parametrize("level", ["L0_READ_ONLY", "L1_DRY_RUN"])
def test_13_l0_l1_need_no_approval(level): validate_approval(level, None)
@pytest.mark.parametrize("level", ["L2_SANDBOX_PREP", "L3_SANDBOX_WRITE", "L4_CONTROLLED_PRODUCTION"])
def test_13_l2_l4_require_approval(level):
    with pytest.raises(UnsafeOperation): validate_approval(level, None)
def test_14_plain_does_not_call_tianzheng(): assert GenericAutoCadAdapter.TIANZHENG_CALLS_ALLOWED is False
def test_15_water_does_not_call_hvac(): assert TianzhengWaterAdapter.HVAC_CALLS_ALLOWED is False
def test_16_hvac_does_not_call_water(): assert TianzhengHvacAdapter.WATER_CALLS_ALLOWED is False
def test_17_product_conflict_stops():
    manifest = load_example(); manifest["product"] = "tianzheng_water"
    with pytest.raises(ProductInstanceConflict): select_runtime(manifest)
def test_18_original_adapter_is_mapping_only():
    adapter = OriginalRedrawSkillAdapter(); patch = adapter.to_manifest_patch("visual_review")
    assert patch["preferred_backend"] == "offline"
    assert patch["product"] == "generic_autocad"
    with pytest.raises(UnsafeOperation): adapter.execute_script({})
def test_19_legacy_backend_disabled():
    with pytest.raises(UnsafeOperation): LegacyComBackend().execute({})
def test_20_mcp_placeholder_not_real(): assert NextGenMcpBackendPlaceholder.real_cad_capability is False
def test_20_mcp_mock_baseline_only(): assert NextGenMcpMockBackend.support_level == "IMPLEMENTED_BASELINE"
def test_21_capability_support_levels():
    text = (ROOT / "capabilities/tianzheng_hvac.json").read_text(encoding="utf-8")
    assert '"INTERFACE_ONLY"' in text and '"write_supported":false' in text
def test_22_checkpoint_fields():
    text = (ROOT / "schemas/checkpoint.schema.json").read_text(encoding="utf-8")
    assert all(x in text for x in ["last_completed_batch_id", "completed_batch_count", "completed_task_count"])
def test_23_no_hardcoded_completed_batch():
    for file in ROOT.rglob("*.py"):
        assert not re.search(r"last_completed_batch_id\s*=\s*['\"](?:batch)?\d+", file.read_text(encoding="utf-8"))
def test_24_manual_save_status(): assert "MANUAL_SAVE_REQUIRED" in (ROOT / "schemas/checkpoint.schema.json").read_text(encoding="utf-8")
def test_25_protected_region(): assert "protected_regions" in SCHEMA["$defs"]["safety"]["properties"]
def test_26_original_file_write_forbidden(): assert "禁止写入源 DWG" in (ROOT / "safety/document_guard.py").read_text(encoding="utf-8")
def test_27_visual_review_required(): assert all(load_example(p.name)["visual_review_required"] for p in (ROOT / "examples").glob("*.json"))
def test_28_engineering_semantic_status(): assert "MANUAL_REVIEW_REQUIRED" in (ROOT / "capabilities/tianzheng_water.json").read_text(encoding="utf-8")
def test_29_sync_defaults_dry_run():
    text = (ROOT / "scripts/sync_skill_installation.ps1").read_text(encoding="utf-8")
    assert "if (-not $Apply)" in text and "DeletesUnknownFiles=$false" in text
def test_30_no_autocad_connection_imports():
    for file in ROOT.rglob("*.py"):
        if file == Path(__file__):
            continue
        assert "win32" + "com" not in file.read_text(encoding="utf-8").lower()
def test_31_file_guard_blocks_dwg():
    with pytest.raises(UnsafeOperation): assert_offline_read_allowed("synthetic.dwg")
def test_31_file_guard_blocks_mcp_lab():
    with pytest.raises(UnsafeOperation): assert_offline_read_allowed("D:/ExampleWorkspace/天正-mcp-lab/config.json")
def test_32_existing_project_tests_not_modified():
    assert not any("existing project" in p.name.lower() for p in ROOT.rglob("*.bak"))
def test_plan_is_non_executing(): assert build_offline_plan(load_example())["execution_allowed"] is False
def test_security_finding_closed_with_frozen_baseline():
    matrix = json.loads((ROOT / "capabilities/backend_matrix.json").read_text(encoding="utf-8"))
    finding = matrix["security_findings"][0]
    assert finding["id"] == "SEC-FINAL-019"
    assert finding["status"] == "CLOSED"
    assert finding["closure_claim_allowed"] is True
    assert finding["baseline_id"] == "20260714T220937+0800"
    assert finding["baseline_sha256"] == "87b995aa5e1178df71a2c54b503537346151f8e5ac50a8dc7be778be0d69faff"
    assert finding["parent_baseline_id"] == "20260714T193554+0800_s2_1"
    assert finding["triggering_change"] == "intentional AGENTS.md update"
    assert finding["default_test_real_dwg_access_count"] == 0


def approval_context():
    return ApprovalContext(
        job_id="job-synthetic",
        document_identity="sandbox-doc",
        document_sha256="a" * 64,
        plan_hash="b" * 64,
        allowed_operations=("inspect", "prepare_copy"),
        runtime_mode="plain_autocad",
        product="autocad",
    )


def approval_ticket(**overrides):
    ticket = {
        "job_id": "job-synthetic",
        "document_identity": "sandbox-doc",
        "document_sha256": "a" * 64,
        "plan_hash": "b" * 64,
        "allowed_operations": ["inspect", "prepare_copy"],
        "runtime_mode": "plain_autocad",
        "product": "autocad",
        "single_use": True,
        "expires_at": "2999-01-01T00:00:00Z",
        "consumed": False,
        "production_allowed": False,
    }
    ticket.update(overrides)
    return ticket


@pytest.mark.parametrize("level", ["L0_READ_ONLY", "L1_DRY_RUN", "L2_SANDBOX_PREP", "L3_SANDBOX_WRITE"])
def test_approval_context_positive_nonproduction(level):
    validate_approval(level, approval_ticket(), approval_context(), production_allowed=False)


@pytest.mark.parametrize("claim,bad", [
    ("job_id", "other-job"),
    ("document_identity", "other-doc"),
    ("document_sha256", "c" * 64),
    ("plan_hash", "d" * 64),
    ("allowed_operations", ["erase"]),
    ("runtime_mode", "tianzheng_water"),
    ("product", "tianzheng_water"),
])
def test_approval_context_rejects_claim_mismatch(claim, bad):
    with pytest.raises(UnsafeOperation, match=claim):
        validate_approval("L3_SANDBOX_WRITE", approval_ticket(**{claim: bad}), approval_context())


def test_approval_rejects_reuse():
    with pytest.raises(UnsafeOperation, match="不得复用"):
        validate_approval("L3_SANDBOX_WRITE", approval_ticket(consumed=True), approval_context())


def test_approval_rejects_expired_ticket():
    with pytest.raises(UnsafeOperation, match="已过期"):
        validate_approval("L3_SANDBOX_WRITE", approval_ticket(expires_at="2000-01-01T00:00:00Z"), approval_context())


def test_l4_rejected_while_production_default_false():
    with pytest.raises(UnsafeOperation, match="L4"):
        validate_approval("L4_CONTROLLED_PRODUCTION", approval_ticket(), approval_context())


@pytest.mark.parametrize("filename", ["generic_autocad.json", "tianzheng_water.json", "tianzheng_hvac.json", "backend_matrix.json"])
def test_capability_files_match_schema(filename):
    schema = json.loads((ROOT / "schemas/capability.schema.json").read_text(encoding="utf-8"))
    payload = json.loads((ROOT / "capabilities" / filename).read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def test_architecture_has_no_project_absolute_path():
    text = (ROOT / "references/architecture.md").read_text(encoding="utf-8")
    assert "D:/ExampleWorkspace" not in text and "D:\\ExampleWorkspace" not in text


def test_windows_validator_forces_utf8():
    text = (ROOT / "scripts/validate_skill.ps1").read_text(encoding="utf-8")
    assert "$env:PYTHONUTF8 = '1'" in text
