from pathlib import Path

from mcp.orchestration.stage6_p1 import _payload_sha256
from mcp.orchestration.stage6_p1_execution import _chunks, _validate_frozen_evidence


def test_chunks_preserve_frozen_order_and_scope() -> None:
    values = [f"H{index}" for index in range(7)]
    assert _chunks(values, 3) == [["H0", "H1", "H2"], ["H3", "H4", "H5"], ["H6"]]


def test_execution_preflight_rejects_tampered_plan_before_cad(tmp_path: Path, synthetic_cad_factory) -> None:
    evidence = tmp_path / "alignment.json"
    evidence.write_text("{}\n", encoding="utf-8")
    component = tmp_path / "components.json"
    component.write_text("{}\n", encoding="utf-8")
    source = tmp_path / "source.dwg"
    target = tmp_path / "target.dwg"
    backup = tmp_path / "backup.dwg"
    for path in (source, target, backup):
        synthetic_cad_factory(path, payload=b"dwg")
    import hashlib

    digest = hashlib.sha256(b"dwg").hexdigest()
    evidence_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    component_digest = hashlib.sha256(component.read_bytes()).hexdigest()
    plan = {
        "status": "FROZEN_PREWRITE",
        "target_write_allowed": True,
        "protected_region_intersection": 0,
        "repair_task_count": 1,
        "tasks": [{"task_id": "T1", "execution_allowed": True}],
        "alignment_evidence": [{"report_path": str(evidence), "report_sha256": evidence_digest}],
        "region_diff_evidence": [],
        "core_component_dependency_plan": {"path": str(component), "sha256": component_digest},
        "frozen_inputs": {
            role: {"path": str(path), "sha256": digest}
            for role, path in (("reference", source), ("target", target), ("prewrite_backup", backup))
        },
    }
    plan["plan_sha256"] = _payload_sha256(plan)
    assert _validate_frozen_evidence(plan) == []

    plan["tasks"][0]["execution_allowed"] = False
    errors = _validate_frozen_evidence(plan)
    assert any("plan hash mismatch" in item for item in errors)
    assert any("not execution allowed" in item for item in errors)
