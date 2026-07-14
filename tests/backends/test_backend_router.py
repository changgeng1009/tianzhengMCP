from __future__ import annotations

import pytest

from mcp.backends.models import RepairTask
from mcp.backends.registry import build_default_registry
from mcp.backends.router import BackendRouter
from mcp.backends.safety import BackendSafetyEnforcer, BackendSafetyPolicy


SOURCE = r"D:\samples\source.dwg"
COPY = r"D:\samples\working-copy.dwg"


def line_task(**overrides) -> dict:
    task = {
        "task_id": "line_001",
        "classification": "confirmed_direct_com",
        "object_type": "line",
        "professional_domain": "water_supply_and_drainage",
        "system_type": "water_supply",
        "domain_object_type": "line",
        "geometry": {"start_point": [1.0, 2.0, 0.0], "end_point": [3.0, 2.0, 0.0]},
        "execution_allowed": True,
        "required_capabilities": ["create_acdb_line"],
        "preferred_backend": "com",
        "allowed_backends": ["com"],
        "fallback_policy": "blocked",
    }
    task.update(overrides)
    return task


def tdb_task(**overrides) -> dict:
    task = {
        "task_id": "tdb_001",
        "classification": "controlled_tianzheng_execution",
        "object_type": "TDbPipe",
        "professional_domain": "water_supply_and_drainage",
        "system_type": "water_supply",
        "domain_object_type": "pipe",
        "geometry": {"start_point": [1.0, 2.0, 0.0], "end_point": [3.0, 2.0, 0.0]},
        "execution_allowed": True,
        "required_capabilities": ["create_tdb_pipe", "persistence_qa"],
        "preferred_backend": "tianzheng_api",
        "allowed_backends": ["tianzheng_api", "net_bridge"],
        "fallback_policy": "manual_tianzheng",
    }
    task.update(overrides)
    return task


def router(*, automatic_fallback: bool = False, tianzheng: bool = False) -> BackendRouter:
    policy = BackendSafetyPolicy(allow_automatic_fallback=automatic_fallback, tianzheng_execution_allowed=tianzheng)
    return BackendRouter(build_default_registry(), BackendSafetyEnforcer(policy))


def _force_com_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp.backends.com_backend.importlib.util.find_spec", lambda _name: object()
    )


def test_acdb_line_routes_to_verified_com_backend(monkeypatch) -> None:
    _force_com_probe(monkeypatch)
    result = router().route(line_task(), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "selected"
    assert result.selected_backend == "com"
    assert result.backend_capability_evidence["sandbox_verified"] is True


def test_backend_without_capability_never_executes() -> None:
    result = router().route(line_task(preferred_backend="net_bridge", allowed_backends=["net_bridge"]), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"
    assert result.selected_backend is None


def test_fallback_does_not_happen_silently(monkeypatch) -> None:
    _force_com_probe(monkeypatch)
    task = line_task(preferred_backend="net_bridge", allowed_backends=["net_bridge", "com"])
    result = router(automatic_fallback=False).route(task, source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"
    assert result.selected_backend is None


def test_explicit_automatic_fallback_is_recorded(monkeypatch) -> None:
    _force_com_probe(monkeypatch)
    task = line_task(preferred_backend="net_bridge", allowed_backends=["net_bridge", "com"])
    result = router(automatic_fallback=True).route(task, source_path=SOURCE, working_copy=COPY)
    assert result.selected_backend == "com"
    assert result.fallback_used is True


def test_tdb_pipe_does_not_route_to_com_and_uses_manual_fallback() -> None:
    result = router(tianzheng=True).route(tdb_task(), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "manual_fallback"
    assert result.selected_backend is None
    assert all(item.get("backend_id") != "com" for item in result.candidate_backends)


def test_tdb_pipe_is_not_substituted_with_acdb_line(monkeypatch) -> None:
    _force_com_probe(monkeypatch)
    result = router(tianzheng=True).route(tdb_task(allowed_backends=["com"]), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "manual_fallback"
    assert result.selected_backend is None


@pytest.mark.parametrize("classification", ["review_only", "blocked_invalid_task", "blocked_geometry", "blocked"])
def test_isolated_classifications_never_enter_backend(classification: str) -> None:
    result = router().route(line_task(classification=classification, execution_allowed=False), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"
    assert result.selected_backend is None


def test_incomplete_geometry_is_blocked() -> None:
    result = router().route(line_task(geometry={}), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"
    assert "geometry" in result.selection_reason


def test_zero_length_line_is_blocked() -> None:
    point = [1.0, 2.0, 0.0]
    result = router().route(line_task(geometry={"start_point": point, "end_point": point}), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"


def test_source_path_cannot_be_working_copy() -> None:
    result = router().route(line_task(), source_path=SOURCE, working_copy=SOURCE)
    assert result.selection_status == "blocked"
    assert "source" in result.selection_reason


def test_working_copy_is_required() -> None:
    result = router().route(line_task(), source_path=SOURCE, working_copy=None)
    assert result.selection_status == "blocked"


def test_hvac_task_cannot_be_executable() -> None:
    result = router().route(line_task(professional_domain="hvac"), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"


def test_sendcommand_marker_is_blocked() -> None:
    result = router().route(line_task(metadata={"command": "SendCommand hsxg"}), source_path=SOURCE, working_copy=COPY)
    assert result.selection_status == "blocked"


def test_task_model_contains_backend_selection_fields() -> None:
    task = RepairTask.from_dict(line_task())
    data = task.to_dict()
    assert "required_capabilities" in data
    assert "selected_backend" in data
    assert "backend_capability_evidence" in data
