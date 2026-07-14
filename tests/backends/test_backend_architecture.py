from __future__ import annotations

import ast
from pathlib import Path

from mcp.backends.base import CadBackend
from mcp.backends.com_backend import ComCadBackend
from mcp.backends.mock_backend import MockCadBackend
from mcp.backends.net_bridge_backend import NetBridgeCadBackend
from mcp.backends.registry import BackendRegistry, build_default_registry
from mcp.backends.tianzheng_api_backend import TianzhengOfficialApiBackend


def test_cad_backend_protocol_exists_and_is_runtime_checkable() -> None:
    assert CadBackend is not None


def test_all_backends_implement_protocol() -> None:
    backends = [ComCadBackend(), MockCadBackend(), NetBridgeCadBackend(), TianzhengOfficialApiBackend()]
    assert all(isinstance(backend, CadBackend) for backend in backends)


def test_backend_registry_registers_and_lists_backends() -> None:
    registry = BackendRegistry()
    registry.register(MockCadBackend())
    assert registry.ids() == ["mock"]
    assert registry.get("mock").backend_id == "mock"


def test_default_registry_has_expected_backends() -> None:
    assert build_default_registry().ids() == ["com", "mock", "net_bridge", "tianzheng_api"]


def test_future_backend_skeletons_are_disabled_and_unavailable() -> None:
    for backend in (NetBridgeCadBackend(), TianzhengOfficialApiBackend()):
        assert backend.enabled is False
        assert backend.probe().available is False
        assert backend.get_capabilities().available is False


def test_com_does_not_claim_tdb_creation_or_command_tracking(monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp.backends.com_backend.importlib.util.find_spec", lambda _name: object()
    )
    capabilities = ComCadBackend().get_capabilities().capabilities
    assert capabilities["scan_tdb_pipe"] is True
    assert capabilities["create_tdb_pipe"] is False
    assert capabilities["create_tdb_valve"] is False
    assert capabilities["create_tdb_fitting"] is False
    assert capabilities["create_tianzheng_water_equipment"] is False
    assert capabilities["command_completion_tracking"] is False
    assert capabilities["official_tianzheng_api"] is False


def test_business_and_domain_layers_do_not_import_native_execution_apis() -> None:
    root = Path(__file__).parents[2] / "mcp"
    business_dirs = ["domains", "diff", "planning", "recognition", "repair_actions", "semantic", "spatial", "qa", "alignment", "extraction"]
    forbidden = ("win32com", "Dispatch", "GetActiveObject")
    violations = []
    for directory in business_dirs:
        for path in (root / directory).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in forbidden):
                violations.append(str(path.relative_to(root)))
    assert violations == []


def test_backend_models_are_serializable_without_native_handles() -> None:
    session = MockCadBackend().connect(None)  # type: ignore[arg-type]
    assert "native_handle" not in session.to_dict()
