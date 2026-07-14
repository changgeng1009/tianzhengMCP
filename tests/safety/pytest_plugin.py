"""项目级 pytest 插件入口，确保任意显式测试树均加载 CAD 守卫。"""

from __future__ import annotations

from pathlib import Path
import os
import sys
from types import SimpleNamespace
from types import ModuleType
import datetime

import pytest

from tests.safety.real_cad_access_guard import RealCadAccessGuard


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAD_ACCESS_GUARD = RealCadAccessGuard.from_environment(PROJECT_ROOT)


def pytest_configure(config):
    """在测试收集前启用守卫，覆盖 import-time 文件访问。"""

    CAD_ACCESS_GUARD.install()


def pytest_collection_modifyitems(items):
    CAD_ACCESS_GUARD.set_collection(items)


def pytest_runtest_setup(item):
    CAD_ACCESS_GUARD.set_test_context(item)


def pytest_runtest_teardown(item, nextitem):
    CAD_ACCESS_GUARD.clear_test_context()


def pytest_unconfigure(config):
    CAD_ACCESS_GUARD.finalize()
    CAD_ACCESS_GUARD.uninstall()


@pytest.fixture
def cad_access_guard(tmp_path, request):
    """向测试暴露只允许登记 ``tmp_path`` 内 synthetic CAD 的接口。"""

    owner = request.node.nodeid
    CAD_ACCESS_GUARD.add_synthetic_root(tmp_path, owner_test_id=owner)
    try:
        yield CAD_ACCESS_GUARD
    finally:
        CAD_ACCESS_GUARD.clear_owner(owner)


@pytest.fixture
def synthetic_cad_factory(tmp_path, cad_access_guard):
    """在 ``tmp_path`` 内登记后创建随机或空内容的 synthetic CAD 文件。"""

    def create(path_or_name, *, size: int = 32, payload: bytes | None = None, create: bool = True):
        path = Path(path_or_name)
        if any(token in str(path) for token in ("*", "?", "[", "]")):
            raise ValueError("synthetic_cad_factory 拒绝 glob 或通配路径")
        if not path.is_absolute():
            path = tmp_path / path
        resolved = path.resolve(strict=False)
        root = tmp_path.resolve(strict=False)
        if os.path.commonpath([str(resolved), str(root)]) != str(root):
            raise ValueError("synthetic CAD 必须位于当前 pytest tmp_path 内")
        if resolved.suffix.lower() not in {".dwg", ".dxf"}:
            raise ValueError("synthetic_cad_factory 仅创建 .dwg/.dxf")
        if resolved.exists() and resolved.is_dir():
            raise ValueError("synthetic_cad_factory 拒绝目录登记")
        cad_access_guard.register_synthetic_cad(
            resolved, synthetic_test_file=True
        )
        if create:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(
                payload if payload is not None else (os.urandom(size) if size else b"")
            )
        return resolved

    return create


@pytest.fixture
def register_t30_sandbox_outputs(monkeypatch, synthetic_cad_factory):
    """固定测试 UUID，并精确登记一次 T30 sandbox 的两个输出文件。"""

    from mcp.t30_writeback import sandbox as sandbox_module

    token = "cadtest00000000000000000000000001"
    monkeypatch.setattr(
        sandbox_module, "uuid4", lambda: SimpleNamespace(hex=token)
    )

    def register(root, original_name):
        root = Path(root)
        original = Path(original_name)
        run_dir = root / f"tx_{token}"
        sandbox_path = synthetic_cad_factory(
            run_dir / original.name, create=False
        )
        backup_path = synthetic_cad_factory(
            run_dir / f"{original.stem}.backup{original.suffix}", create=False
        )
        return sandbox_path, backup_path

    return register


@pytest.fixture
def cad_test_mock_com_modules(monkeypatch):
    """注入带安全标记的纯测试 COM 模块，不包含任何真实连接入口。"""

    pythoncom = ModuleType("pythoncom")
    pythoncom.__cad_test_mock__ = True
    pythoncom.VT_ARRAY = 0x2000
    pythoncom.VT_R8 = 5
    pythoncom.PumpWaitingMessages = lambda: None

    client = ModuleType("win32com.client")
    client.__cad_test_mock__ = True

    class FakeVariant:
        def __init__(self, _variant_type, value):
            self.value = value

    client.VARIANT = FakeVariant
    package = ModuleType("win32com")
    package.__cad_test_mock__ = True
    package.client = client

    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    return SimpleNamespace(pythoncom=pythoncom, win32com=package, client=client)


@pytest.fixture
def d2_synthetic_intake(tmp_path, monkeypatch, synthetic_cad_factory):
    """为每个 D2 测试构造独立、可哈希且不依赖历史 artifacts 的输入。"""

    from mcp.intake import reference_file_intake as intake

    source = synthetic_cad_factory(tmp_path / "source.dwg")
    reference_dwg = synthetic_cad_factory(tmp_path / "reference_source.dwg")
    reference_pdf = tmp_path / "reference.pdf"
    reference_pdf.write_bytes(os.urandom(32))
    artifacts_input = tmp_path / "artifacts" / "input"
    sandbox_dir = tmp_path / "artifacts" / "sandbox"
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True)

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 1, 2, 3, 4, 5)
            return value.replace(tzinfo=tz) if tz is not None else value

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(intake, "SOURCE_DWG", str(source))
    monkeypatch.setattr(intake, "REF_PDF", str(reference_pdf))
    monkeypatch.setattr(intake, "REF_DWG", str(reference_dwg))
    monkeypatch.setattr(intake, "ARTIFACTS_INPUT", str(artifacts_input))
    monkeypatch.setattr(intake, "SANDBOX_DIR", str(sandbox_dir))
    monkeypatch.setattr(
        intake,
        "datetime",
        SimpleNamespace(datetime=FixedDateTime, timezone=datetime.timezone),
    )

    synthetic_cad_factory(artifacts_input / "reference.dwg", create=False)
    synthetic_cad_factory(
        sandbox_dir / "sandbox_20260102_030405.dwg", create=False
    )
    result = intake.run_intake()
    return SimpleNamespace(
        result=result,
        report_path=report_dir / "phase_d2_reference_file_intake.json",
    )
