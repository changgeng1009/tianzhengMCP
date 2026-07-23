"""文件访问守卫专项测试。

这些测试只使用不存在的虚构路径或 ``tmp_path`` 动态 synthetic 文件，绝不读取
现存 DWG/DXF。预期阻断由 ``guard_self_test`` marker 单独计数。
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.safety.real_cad_access_guard import (
    RealCadAccessGuard,
    RealCadAccessViolation,
    guarded_file_sha256,
)


pytestmark = pytest.mark.guard_self_test


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FAKE_REAL_DWG = PROJECT_ROOT / "图纸" / "never-created-course-file.dwg"
FAKE_ARTIFACT_DWG = PROJECT_ROOT / "artifacts" / "never-created-candidate.dwg"
_CROSS_TEST_SYNTHETIC_PATH: Path | None = None


def test_builtin_open_binary_blocks_unregistered_dwg():
    with pytest.raises(RealCadAccessViolation, match="builtins.open"):
        builtins.open(FAKE_REAL_DWG, "rb")


def test_path_open_blocks_unregistered_dwg():
    with pytest.raises(RealCadAccessViolation, match="Path.open"):
        FAKE_REAL_DWG.open("rb")


def test_path_read_bytes_blocks_unregistered_dwg():
    with pytest.raises(RealCadAccessViolation, match="Path.read_bytes"):
        FAKE_REAL_DWG.read_bytes()


def test_path_read_text_blocks_dxf():
    with pytest.raises(RealCadAccessViolation, match="Path.read_text"):
        FAKE_REAL_DWG.with_suffix(".dxf").read_text(encoding="utf-8")


@pytest.mark.parametrize("suffix", [".dwt", ".dws", ".bak", ".sv$"])
def test_additional_cad_related_extensions_are_blocked(suffix):
    with pytest.raises(RealCadAccessViolation):
        FAKE_REAL_DWG.with_suffix(suffix).read_bytes()


def test_os_open_blocks_unregistered_dwg():
    with pytest.raises(RealCadAccessViolation, match="os.open"):
        os.open(FAKE_REAL_DWG, os.O_RDONLY)


@pytest.mark.parametrize("copy_name", ["copy", "copy2", "copyfile"])
def test_shutil_copy_family_blocks_real_cad(copy_name, tmp_path):
    copier = getattr(shutil, copy_name)
    with pytest.raises(RealCadAccessViolation, match=f"shutil.{copy_name}"):
        copier(FAKE_REAL_DWG, tmp_path / "copy.bin")


def test_custom_sha256_helper_blocks_before_hashing(cad_access_guard):
    with pytest.raises(RealCadAccessViolation, match="guarded_file_sha256"):
        guarded_file_sha256(FAKE_REAL_DWG, cad_access_guard)


def test_subprocess_with_dwg_argument_is_blocked():
    with pytest.raises(RealCadAccessViolation, match="子进程阻断"):
        subprocess.run(
            ["python", "preflight.py", "--input", str(FAKE_REAL_DWG)],
            check=False,
        )


def test_powershell_scanner_command_with_dxf_is_blocked():
    command = f"Get-Content -LiteralPath '{FAKE_REAL_DWG.with_suffix('.dxf')}'"
    with pytest.raises(RealCadAccessViolation, match="子进程阻断"):
        subprocess.run(["powershell", "-Command", command], check=False)


def test_cad_process_is_blocked_even_without_document_argument():
    with pytest.raises(RealCadAccessViolation, match="cad_process_forbidden"):
        subprocess.Popen(["acad.exe", "/nologo"])


def test_popen_guard_remains_class_compatible_for_windows_asyncio():
    assert isinstance(subprocess.Popen, type)
    assert issubclass(subprocess.Popen, subprocess.Popen.__mro__[1])


def test_normal_json_read_is_allowed(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text('{"synthetic_test_file": true}', encoding="utf-8")
    assert "synthetic_test_file" in path.read_text(encoding="utf-8")


def test_python_source_read_is_allowed():
    text = Path(__file__).read_text(encoding="utf-8")
    assert "test_python_source_read_is_allowed" in text


def test_registered_tmp_synthetic_dwg_can_be_written_and_read(
    tmp_path, cad_access_guard
):
    path = tmp_path / "dynamic-synthetic.dwg"
    cad_access_guard.register_synthetic_cad(path, synthetic_test_file=True)
    payload = os.urandom(32)
    path.write_bytes(payload)
    assert path.read_bytes() == payload


def test_unregistered_tmp_dwg_is_blocked(tmp_path):
    path = tmp_path / "unregistered-synthetic.dwg"
    with pytest.raises(RealCadAccessViolation):
        path.write_bytes(b"synthetic")


def test_only_real_dwg_marker_does_not_release_readonly(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.add("real_dwg")
        monkeypatch.setenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", "1")
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "rb")
        assert allowed is False
        assert reason == "real_cad_boundary"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_only_external_integration_marker_does_not_release_readonly(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.add("external_integration")
        monkeypatch.setenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", "1")
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "rb")
        assert allowed is False
        assert reason == "real_cad_boundary"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_both_external_markers_without_environment_do_not_release_readonly(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.update(
            {"real_dwg", "external_integration"}
        )
        monkeypatch.delenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", raising=False)
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "rb")
        assert allowed is False
        assert reason == "real_cad_boundary"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_both_external_markers_and_environment_release_readonly(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.update(
            {"real_dwg", "external_integration"}
        )
        monkeypatch.setenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", "1")
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "rb")
        assert allowed is True
        assert reason == "explicit_external_readonly"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_real_cad_write_remains_blocked_with_both_markers_and_environment(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.update(
            {"real_dwg", "external_integration"}
        )
        monkeypatch.setenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", "1")
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "wb")
        assert allowed is False
        assert reason == "real_cad_boundary"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_other_external_markers_do_not_release_readonly(
    cad_access_guard, monkeypatch
):
    previous_markers = set(cad_access_guard._current_markers)
    try:
        cad_access_guard._current_markers.add("autocad_required")
        monkeypatch.setenv("CAD_TEST_ALLOW_EXTERNAL_READONLY", "1")
        allowed, reason, _ = cad_access_guard.evaluate_path(FAKE_REAL_DWG, "rb")
        assert allowed is False
        assert reason == "real_cad_boundary"
    finally:
        cad_access_guard._current_markers = previous_markers


def test_artifacts_dwg_is_blocked():
    with pytest.raises(RealCadAccessViolation):
        FAKE_ARTIFACT_DWG.read_bytes()


@pytest.mark.parametrize("operation", ["rename", "replace"])
def test_os_rename_family_blocks_real_cad(operation, tmp_path):
    with pytest.raises(RealCadAccessViolation):
        getattr(os, operation)(FAKE_REAL_DWG, tmp_path / "output.bin")


def test_shutil_move_blocks_real_cad(tmp_path):
    with pytest.raises(RealCadAccessViolation):
        shutil.move(FAKE_REAL_DWG, tmp_path / "output.bin")


def test_artifacts_json_is_allowed_by_policy(tmp_path):
    artifact_json = tmp_path / "artifacts" / "report.json"
    artifact_json.parent.mkdir()
    artifact_json.write_text("{}", encoding="utf-8")
    assert artifact_json.read_text(encoding="utf-8") == "{}"


def test_case_and_slash_variants_cannot_bypass_guard():
    variant = str(FAKE_REAL_DWG).upper().replace("\\", "/")
    with pytest.raises(RealCadAccessViolation):
        builtins.open(variant, "rb")


def test_relative_dotdot_path_cannot_bypass_guard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = Path("..") / ".." / "escape" / "drawing.dwg"
    with pytest.raises(RealCadAccessViolation):
        relative.read_bytes()


def test_unc_cad_path_is_blocked():
    unc_path = r"\\server\share\customer\drawing.dwg"
    with pytest.raises(RealCadAccessViolation):
        builtins.open(unc_path, "rb")


def test_known_drawing_directory_blocks_non_cad_file():
    fake_note = PROJECT_ROOT / "图纸" / "never-created-note.json"
    with pytest.raises(RealCadAccessViolation):
        fake_note.read_text(encoding="utf-8")


def test_synthetic_registration_rejects_non_tmp_path(cad_access_guard):
    with pytest.raises(ValueError, match="tmp_path"):
        cad_access_guard.register_synthetic_cad(
            PROJECT_ROOT / "synthetic.dwg", synthetic_test_file=True
        )


def test_synthetic_registration_requires_explicit_flag(tmp_path, cad_access_guard):
    with pytest.raises(ValueError, match="synthetic_test_file=true"):
        cad_access_guard.register_synthetic_cad(
            tmp_path / "synthetic.dwg", synthetic_test_file=False
        )


def test_synthetic_symlink_cannot_escape_tmp_root(tmp_path, cad_access_guard):
    outside_target = tmp_path.parent / "outside-synthetic-target.bin"
    outside_target.write_bytes(os.urandom(16))
    link = tmp_path / "linked-synthetic.dwg"
    try:
        link.symlink_to(outside_target)
    except OSError as exc:
        pytest.skip(f"当前环境不可创建 symlink/junction: {exc}")
    with pytest.raises(ValueError, match="解析后的真实路径"):
        cad_access_guard.register_synthetic_cad(link, synthetic_test_file=True)


def test_synthetic_dotdot_registration_cannot_escape_tmp_root(
    tmp_path, cad_access_guard
):
    escaped = tmp_path / ".." / "escaped-synthetic.dwg"
    with pytest.raises(ValueError, match="解析后的真实路径"):
        cad_access_guard.register_synthetic_cad(
            escaped, synthetic_test_file=True
        )


@pytest.mark.parametrize(
    "command",
    [
        ["cmd", "/c", "acad.exe", "/nologo"],
        ["powershell", "-File", "tools/drawing_scanner.ps1"],
        [
            "python",
            "scripts/run_stage6_p1_accelerated_r4.py",
            "--preflight-only",
        ],
        ["python", "tools/file_sha256.py", "--config", "safe.json"],
    ],
)
def test_known_cad_access_subprocess_chain_without_cad_literal_is_blocked(command):
    with pytest.raises(RealCadAccessViolation, match="子进程阻断"):
        subprocess.run(command, check=False)


def test_summary_counts_are_derived_from_events(tmp_path):
    local_guard = RealCadAccessGuard(PROJECT_ROOT, tmp_path / "summary")
    local_guard._record(
        operation="builtins.open.completed",
        path="synthetic-policy-path.dwg",
        mode="rb",
        allowed=True,
        reason="explicit_external_readonly",
    )
    local_guard._record(
        operation="subprocess.started",
        path="python safe_tool.py",
        mode="execute",
        allowed=True,
        reason="non_cad_subprocess",
        process=True,
    )
    local_guard._record(
        operation="autocad_com_connection.completed",
        path="mock-event-only",
        mode="connect",
        allowed=True,
        reason="test_fact",
    )
    local_guard._record(
        operation="tianzheng_connection.completed",
        path="mock-event-only",
        mode="connect",
        allowed=True,
        reason="test_fact",
    )
    summary = local_guard.build_summary()
    assert summary["real_dwg_successful_reads"] == 1
    assert summary["external_processes_started"] == 1
    assert summary["autocad_com_connections"] == 1
    assert summary["tianzheng_connections"] == 1


def test_project_plugin_covers_explicit_skill_test_invocation():
    pytest_ini = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "-p tests.safety.pytest_plugin" in pytest_ini
    assert (PROJECT_ROOT / "tests/safety/pytest_plugin.py").is_file()


def test_zz_owner_a_registers_and_allows_synthetic_file(synthetic_cad_factory):
    global _CROSS_TEST_SYNTHETIC_PATH
    _CROSS_TEST_SYNTHETIC_PATH = synthetic_cad_factory("cross-owner.dwg")
    assert _CROSS_TEST_SYNTHETIC_PATH.read_bytes()


def test_zz_owner_b_same_path_is_blocked_after_a_teardown():
    assert _CROSS_TEST_SYNTHETIC_PATH is not None
    assert _CROSS_TEST_SYNTHETIC_PATH.exists()
    with pytest.raises(RealCadAccessViolation):
        _CROSS_TEST_SYNTHETIC_PATH.read_bytes()
    assert _CROSS_TEST_SYNTHETIC_PATH.exists(), "teardown 只能撤销登记，不得删除 fixture 文件"


def test_owner_mismatch_cannot_use_another_tests_registration(
    tmp_path, synthetic_cad_factory
):
    path = synthetic_cad_factory(tmp_path / "owner-mismatch.dwg")
    local_guard = RealCadAccessGuard(PROJECT_ROOT, tmp_path / "local-log")
    local_guard.add_synthetic_root(tmp_path, owner_test_id="owner-A")
    local_guard.register_synthetic_cad(
        path, synthetic_test_file=True, owner_test_id="owner-A"
    )
    local_guard._current_test = "owner-B"
    allowed, reason, _ = local_guard.evaluate_path(path, "rb")
    assert allowed is False
    assert reason == "real_cad_boundary"


def test_clear_owner_revokes_registration_without_deleting_file(
    tmp_path, synthetic_cad_factory
):
    path = synthetic_cad_factory(tmp_path / "clear-owner.dwg")
    assert path.exists()
    owner = "manual-owner"
    local_guard = RealCadAccessGuard(PROJECT_ROOT, tmp_path / "local-log")
    local_guard.add_synthetic_root(tmp_path, owner_test_id=owner)
    local_guard.register_synthetic_cad(
        path, synthetic_test_file=True, owner_test_id=owner
    )
    local_guard.clear_owner(owner)
    local_guard._current_test = owner
    allowed, reason, _ = local_guard.evaluate_path(path, "rb")
    assert allowed is False
    assert reason == "real_cad_boundary"
    assert path.exists()
