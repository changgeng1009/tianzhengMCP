from __future__ import annotations

from mcp.backends.mock_backend import MockCadBackend
from mcp.backends.models import BackendConfig, RepairTask, ScanRequest


def test_mock_backend_never_claims_real_cad_execution_or_dwg_modification() -> None:
    backend = MockCadBackend()
    session = backend.connect(BackendConfig("mock", enabled=True, execution_allowed=True))
    backend.open_working_copy(session, "中文路径/测试副本.dwg")
    task = RepairTask(
        task_id="mock_line",
        classification="confirmed_direct_com",
        object_type="line",
        execution_allowed=True,
        required_capabilities=["create_acdb_line"],
        geometry={"start_point": [1, 2, 0], "end_point": [2, 2, 0]},
    )
    result = backend.create_entity(session, task)
    saved = backend.save_working_copy(session)
    assert result.real_cad_execution is False
    assert result.real_dwg_modified is False
    assert saved.document_saved is False
    assert saved.real_dwg_modified is False


def test_mock_scan_and_utf8_path_round_trip() -> None:
    backend = MockCadBackend(entities=[{"object_name": "AcDbLine"}])
    session = backend.connect(BackendConfig("mock", enabled=True))
    opened = backend.open_working_copy(session, "D:/图纸/给排水副本.dwg")
    scanned = backend.scan_entities(session, ScanRequest())
    assert opened.document_path == "D:/图纸/给排水副本.dwg"
    assert scanned.entities == [{"object_name": "AcDbLine"}]
