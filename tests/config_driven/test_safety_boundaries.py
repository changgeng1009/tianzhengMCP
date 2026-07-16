from __future__ import annotations

import builtins
from copy import deepcopy
import pytest

from adapters.original_skill import OriginalRedrawSkillAdapter
from adapters.registry import BackendRegistry
from config import ConfigMerger, DefaultRegistry, ManifestPathResolver, canonical_hash
from runtime.errors import ConfigPrivilegeEscalationBlocked, UnsafeOperation
from runtime.execution_plan import execution_plan_hash
from runtime.simulation import simulate_plan
from tests.safety.pytest_plugin import CAD_ACCESS_GUARD


def _minimal_plan(backend: str = "offline") -> dict:
    plan = {
        "plan_schema_version": "1.0.0",
        "plan_id": "",
        "project_id": "fictional-project",
        "task_id": "fictional-task",
        "runtime_mode": "offline_analysis",
        "product_mode": "unknown",
        "backend": backend,
        "workflow_id": "offline_capability_audit",
        "approval_requirement": {},
        "document_requirements": [],
        "protected_regions": [],
        "operation_allowlist": [],
        "operation_denylist": [],
        "stages": [],
        "expected_artifacts": [],
        "verification_requirements": {},
        "recovery_policy": {},
        "limitations": [],
        "executable": True,
        "blocked_reasons": [],
        "canonical_manifest_hash": "0" * 64,
        "plan_hash": "",
    }
    plan["plan_hash"] = execution_plan_hash(plan)
    plan["plan_id"] = f"plan-{plan['plan_hash'][:16]}"
    return plan


def test_req_091_offline_simulation_does_not_connect_autocad(monkeypatch):
    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        imported.append(name)
        if name.startswith(("win32com", "comtypes")):
            raise AssertionError("离线模拟不得导入真实 COM")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    result = simulate_plan(_minimal_plan())
    assert result["cad_connected"] is False
    assert not any(name.startswith(("win32com", "comtypes")) for name in imported)


def test_req_092_offline_simulation_reports_zero_com_connection():
    result = simulate_plan(_minimal_plan())
    assert result["com_connected"] is False
    assert result["tianzheng_connected"] is False


def test_req_093_simulation_does_not_start_subprocess(cad_access_guard):
    result = simulate_plan(_minimal_plan())
    assert result["subprocess_started"] is False
    assert cad_access_guard is CAD_ACCESS_GUARD


def test_req_094_lexical_manifest_path_does_not_read_cad(cad_access_guard):
    resolver = ManifestPathResolver(project_root="C:/fictional/project")
    record = resolver.resolve_one(
        "inputs/reference.dwg", field="document.path", manifest_directory="C:/fictional/project"
    )
    assert record.filesystem_accessed is False
    assert cad_access_guard is CAD_ACCESS_GUARD


def test_req_095_canonical_hash_never_hashes_a_cad_file(cad_access_guard):
    value = {"document_path": "inputs/reference.dwg", "identity_status": "DECLARED"}
    assert len(canonical_hash(value)) == 64
    assert cad_access_guard is CAD_ACCESS_GUARD


def test_req_096_manifest_cannot_grant_l4():
    with pytest.raises(ConfigPrivilegeEscalationBlocked):
        ConfigMerger().merge_layers([
            ("project_manifest", {"safety": {"requested_level": "L4_CONTROLLED_PRODUCTION"}})
        ])


def test_req_097_production_defaults_are_false():
    defaults = DefaultRegistry().system_defaults()
    assert defaults["safety"]["production_allowed"] is False
    assert defaults["safety"]["production_d1_allowed"] is False


def test_req_098_real_backend_statuses_are_never_promoted():
    registry = BackendRegistry()
    real_ids = {
        "legacy_com",
        "nextgen_real",
        "autocad_dotnet_plugin",
        "tianzheng_water_real",
        "tianzheng_hvac_real",
    }
    for backend_id in real_ids:
        contract = registry.get(backend_id)
        assert contract.selection_available is False
        assert contract.real_execution_supported is False


def test_req_099_sec_final_019_guard_is_active(cad_access_guard):
    assert cad_access_guard is CAD_ACCESS_GUARD
    assert CAD_ACCESS_GUARD._installed is True


def test_req_100_original_skill_adapter_is_read_only():
    adapter = OriginalRedrawSkillAdapter()
    patch = adapter.to_manifest_patch("redraw_from_reference")
    assert patch["production_allowed"] is False
    assert patch["product"] == "generic_autocad"
    with pytest.raises(UnsafeOperation):
        adapter.execute_script(deepcopy(patch))
