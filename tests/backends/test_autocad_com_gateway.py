"""S5 COM gateway 的纯 Fake 单元测试。

本文件刻意不导入 win32com、不创建 COM 对象，也不落盘任何 `.dwg`。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import importlib
from pathlib import Path

import pytest

from mcp_nextgen.backends.autocad_com_gateway import (
    AutoCadComGatewayError,
    ComSafeArrayAdapter,
    Pywin32AutoCadSandboxGateway,
)
import mcp_nextgen.backends.autocad_com_gateway as gateway_module
from mcp_nextgen.backends.real_autocad_com import (
    CircleSpec,
    DocumentOwnershipRegistry,
    LineSpec,
    Point3,
    PolylineSpec,
)


@dataclass
class FakeEntity:
    ObjectName: str
    Handle: str
    Layer: str = "0"
    Closed: bool = False
    StartPoint: tuple[float, float, float] | None = None
    EndPoint: tuple[float, float, float] | None = None
    Center: tuple[float, float, float] | None = None
    Radius: float | None = None
    Coordinates: tuple[float, ...] = ()


class FakeModelSpace(list[FakeEntity]):
    def __init__(self) -> None:
        super().__init__()
        self.line_args = None
        self.circle_args = None
        self.polyline_args = None

    def AddLine(self, start, end):  # noqa: N802 - COM 形状
        self.line_args = (start, end)
        entity = FakeEntity("AcDbLine", f"H{len(self) + 1}", StartPoint=tuple(start), EndPoint=tuple(end))
        self.append(entity)
        return entity

    def AddCircle(self, center, radius):  # noqa: N802 - COM 形状
        self.circle_args = (center, radius)
        entity = FakeEntity("AcDbCircle", f"H{len(self) + 1}", Center=tuple(center), Radius=float(radius))
        self.append(entity)
        return entity

    def AddLightWeightPolyline(self, coordinates):  # noqa: N802 - COM 形状
        self.polyline_args = coordinates
        entity = FakeEntity("AcDbPolyline", f"H{len(self) + 1}", Coordinates=tuple(coordinates))
        self.append(entity)
        return entity


class FakeLayers:
    def __init__(self) -> None:
        self.items: set[str] = set()

    def Item(self, name):  # noqa: N802 - COM 形状
        if name not in self.items:
            raise RuntimeError("missing")
        return name

    def Add(self, name):  # noqa: N802 - COM 形状
        self.items.add(name)
        return name


class FakeDocument:
    def __init__(self) -> None:
        self.FullName = ""
        self.Name = "Drawing1.dwg"
        self.ReadOnly = False
        self.ModelSpace = FakeModelSpace()
        self.Layers = FakeLayers()
        self.save_calls = 0
        self.closed = False

    def SaveAs(self, value):  # noqa: N802 - COM 形状
        self.FullName = str(value)
        self.Name = Path(str(value)).name

    def Save(self):  # noqa: N802 - COM 形状
        self.save_calls += 1

    def Close(self, _save_changes):  # noqa: N802 - COM 形状
        self.closed = True


class FakeDocuments:
    def __init__(self) -> None:
        self.document: FakeDocument | None = None

    @property
    def Count(self) -> int:  # noqa: N802 - COM 形状
        return int(self.document is not None and not self.document.closed)

    def Add(self):  # noqa: N802 - COM 形状
        self.document = FakeDocument()
        return self.document

    def Open(self, path, _read_only):  # noqa: N802 - COM 形状
        if self.document is None or str(path) != self.document.FullName:
            raise RuntimeError("unexpected path")
        self.document.closed = False
        return self.document


class FakeApplication:
    def __init__(self) -> None:
        self.Documents = FakeDocuments()
        self.quit_calls = 0

    def Quit(self):  # noqa: N802 - COM 形状
        self.quit_calls += 1


class FakeSafeArrayAdapter(ComSafeArrayAdapter):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[float, ...]]] = []

    def point3(self, values: tuple[float, float, float]):
        self.calls.append(("point3", values))
        return {"com_array": "point3", "values": values}

    def coordinates(self, values: tuple[float, ...]):
        self.calls.append(("coordinates", values))
        return {"com_array": "coordinates", "values": values}


def _identity(tmp_path: Path):
    registry = DocumentOwnershipRegistry(tmp_path)
    return registry.reserve(
        run_id="gateway-unit", job_id="gateway-job", plan_hash="a" * 64,
        output_path=tmp_path / "sandbox" / "s5_synthetic_autocad_mvp.dwg",
    )


def test_gateway_creates_only_held_synthetic_document_and_round_trips_geometry(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    app = FakeApplication()
    gateway = Pywin32AutoCadSandboxGateway(application=app)
    snapshot = gateway.create_synthetic(identity)
    assert snapshot["synthetic"] is True
    assert snapshot["canonical_path"] == identity.canonical_path

    line = gateway.create_line(identity, LineSpec(Point3(0, 0), Point3(1000, 0), operation_key="line"))
    circle = gateway.create_circle(identity, CircleSpec(Point3(2000, 0), 500, operation_key="circle"))
    poly = gateway.create_polyline(identity, PolylineSpec((Point3(0, 1), Point3(1, 1), Point3(1, 2)), False, operation_key="poly"))
    assert {item["entity_type"] for item in (line, circle, poly)} == {"line", "circle", "polyline"}
    assert {item["operation_key"] for item in gateway.list_entities(identity)} == {"line", "circle", "poly"}


def test_default_fake_gateway_path_never_imports_pywin32(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """默认 adapter 只能返回纯值；真实 COM adapter 必须显式注入。"""
    identity = _identity(tmp_path)
    calls: list[str] = []
    original_import = importlib.import_module

    def guarded_import(name: str, *args, **kwargs):
        calls.append(name)
        if name in {"pythoncom", "win32com.client"}:
            raise AssertionError("Fake gateway 不得导入 pywin32")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(gateway_module.importlib, "import_module", guarded_import)
    gateway = Pywin32AutoCadSandboxGateway(application=FakeApplication())
    gateway.create_synthetic(identity)
    gateway.create_line(identity, LineSpec(Point3(0, 0), Point3(10, 0), operation_key="line"))
    gateway.create_circle(identity, CircleSpec(Point3(20, 0), 5, operation_key="circle"))
    gateway.create_polyline(identity, PolylineSpec((Point3(0, 1), Point3(1, 1), Point3(1, 2)), False, operation_key="poly"))
    assert calls == []


def test_gateway_uses_injected_com_safe_array_adapter_for_all_s5_geometry_calls(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    app = FakeApplication()
    adapter = FakeSafeArrayAdapter()
    gateway = Pywin32AutoCadSandboxGateway(application=app, array_adapter=adapter)
    gateway.create_synthetic(identity)
    gateway.create_line(identity, LineSpec(Point3(0, 0), Point3(10, 0), operation_key="line"))
    gateway.create_circle(identity, CircleSpec(Point3(20, 0), 5, operation_key="circle"))
    gateway.create_polyline(identity, PolylineSpec((Point3(0, 1), Point3(1, 1), Point3(1, 2)), False, operation_key="poly"))

    model = app.Documents.document.ModelSpace
    assert adapter.calls == [
        ("point3", (0.0, 0.0, 0.0)), ("point3", (10.0, 0.0, 0.0)),
        ("point3", (20.0, 0.0, 0.0)),
        ("coordinates", (0.0, 1.0, 1.0, 1.0, 1.0, 2.0)),
    ]
    assert model.line_args == (
        {"com_array": "point3", "values": (0.0, 0.0, 0.0)},
        {"com_array": "point3", "values": (10.0, 0.0, 0.0)},
    )
    assert model.circle_args == ({"com_array": "point3", "values": (20.0, 0.0, 0.0)}, 5)
    assert model.polyline_args == {"com_array": "coordinates", "values": (0.0, 1.0, 1.0, 1.0, 1.0, 2.0)}

    gateway.save(identity)
    gateway.close(identity)
    assert app.Documents.Count == 0
    gateway.reopen(identity)
    assert app.Documents.Count == 1


def test_gateway_recovers_operation_key_after_reopen_with_com_numeric_shape_changes(tmp_path: Path) -> None:
    """纯值 adapter 模拟 COM 重开后 tuple/list/int/float 的正常形态转换。"""
    identity = _identity(tmp_path)
    app = FakeApplication()
    gateway = Pywin32AutoCadSandboxGateway(application=app)
    gateway.create_synthetic(identity)
    gateway.create_line(identity, LineSpec(Point3(0, 0), Point3(10, 0), operation_key="line"))
    gateway.create_circle(identity, CircleSpec(Point3(20, 0), 5, operation_key="circle"))
    gateway.create_polyline(identity, PolylineSpec((Point3(0, 1), Point3(1, 1), Point3(1, 2)), False, operation_key="poly"))
    gateway.save(identity)
    gateway.close(identity)
    gateway.reopen(identity)
    # _read_geometry 产出 list/float，而创建期为 tuple/int；指纹必须归一。
    assert {item["operation_key"] for item in gateway.list_entities(identity)} == {"line", "circle", "poly"}


def test_gateway_rejects_foreign_identity_and_quits_only_empty_job_owned_session(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    app = FakeApplication()
    gateway = Pywin32AutoCadSandboxGateway(application=app)
    gateway.create_synthetic(identity)
    foreign = DocumentOwnershipRegistry(tmp_path).reserve(
        run_id="other", job_id="other", plan_hash="b" * 64,
        output_path=tmp_path / "sandbox" / "other.dwg",
    )
    with pytest.raises(AutoCadComGatewayError, match="IDENTITY_MISMATCH"):
        gateway.document_snapshot(foreign)
    with pytest.raises(AutoCadComGatewayError, match="尚未关闭"):
        gateway.quit_if_job_owned()
    gateway.close(identity)
    gateway.quit_if_job_owned()
    assert app.quit_calls == 1


def test_failure_cleanup_can_discard_only_registered_synthetic_document(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    app = FakeApplication()
    gateway = Pywin32AutoCadSandboxGateway(application=app)
    gateway.create_synthetic(identity)
    foreign = DocumentOwnershipRegistry(tmp_path).reserve(
        run_id="foreign", job_id="foreign", plan_hash="c" * 64,
        output_path=tmp_path / "sandbox" / "foreign.dwg",
    )
    with pytest.raises(AutoCadComGatewayError, match="IDENTITY_MISMATCH"):
        gateway.discard_registered_synthetic_document(foreign)
    assert app.Documents.Count == 1
    gateway.discard_registered_synthetic_document(identity)
    assert app.Documents.Count == 0


def test_gateway_never_imports_win32com_or_uses_active_document() -> None:
    source = (Path(__file__).parents[2] / "mcp_nextgen" / "backends" / "autocad_com_gateway.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    imported_modules.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module for alias in node.names
    )
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not any(name.startswith("win32com") for name in imported_modules)
    assert "ActiveDocument" not in attributes
