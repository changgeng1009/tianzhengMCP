from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any


class FakeAcadAdapter:
    """旧 E1 安全测试使用的纯内存适配器，不连接 AutoCAD。"""

    def __init__(self) -> None:
        self.connected = False
        self.doc_path = ""
        self.saved = False

    def connect(self) -> None:
        self.connected = True

    def is_ready(self) -> bool:
        return self.connected

    def open_document(self, path: str) -> Any:
        self.doc_path = path
        return type("FakeDocument", (), {"FullName": path, "Name": Path(path).name})()

    def get_active_document_fullname(self) -> str:
        return self.doc_path

    def save_document(self, expected_path: str = "") -> bool:
        if expected_path and Path(expected_path) != Path(self.doc_path):
            return False
        self.saved = True
        return True

    def close_document(self, save: bool = False) -> None:
        if save:
            self.save_document(self.doc_path)


class FakeScannerAdapter:
    def __init__(self, before_draw_tdb: int = 0, after_draw_tdb: int = 0, after_reopen_tdb: int = 0) -> None:
        self.values = [before_draw_tdb, after_draw_tdb, after_reopen_tdb]
        self.calls = 0

    def scan(self, _document: Any) -> dict[str, Any]:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        count = self.values[index]
        return {
            "modelspace_count": count,
            "tdb_double_line_pipe_count": count,
            "object_name_distribution": {"TDbDoubleLinePipe": count} if count else {},
        }


class FakeWatchdogAdapter:
    def __init__(self, fired: bool = False, active: bool = False) -> None:
        self.fired = fired
        self.command_active = active

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        pass

    def send_command(self, _document: Any, _command: str) -> None:
        pass


def run_e1_orchestrator(
    source_dwg: str,
    sandbox_path: str,
    acad: FakeAcadAdapter,
    scanner: FakeScannerAdapter,
    watchdog: FakeWatchdogAdapter,
    variant_id: str = "HSXG_v01_points_2d",
) -> dict[str, Any]:
    """兼容旧回归测试的 Fake-only E1 结果；永远不放行 D1。"""
    result: dict[str, Any] = {
        "phase": "E1.0.1",
        "variant_id": variant_id,
        "acceptance": "needs_manual_review",
        "d1_allowed": False,
        "production_d1_allowed": False,
        "production_d1_executed": False,
        "source_modification_allowed": False,
        "d1_readiness": False,
        "e1_1_real_complete": False,
        "three_segments_independently_verified": False,
        "persisted_after_reopen_independently_verified": False,
        "draw_delta": 0,
        "persisted_delta": 0,
        "fallback_used": False,
        "errors": [],
    }
    try:
        shutil.copy2(source_dwg, sandbox_path)
        acad.connect()
        document = acad.open_document(sandbox_path)
        before = scanner.scan(document)["tdb_double_line_pipe_count"]
        watchdog.start()
        watchdog.send_command(document, "fake-only")
        watchdog.cancel()
        after = scanner.scan(document)["tdb_double_line_pipe_count"]
        result["draw_delta"] = max(after - before, 0)
        if watchdog.fired or watchdog.command_active:
            result["acceptance"] = "inconclusive"
        acad.close_document(save=False)
    except Exception as exc:
        result["acceptance"] = "inconclusive"
        result["errors"].append(f"fake_orchestrator_error: {type(exc).__name__}")
    return result
