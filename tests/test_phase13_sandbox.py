from __future__ import annotations


def test_create_dwg_sandbox_copies_original_and_backup(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.t30_writeback.sandbox import create_dwg_sandbox

    original = synthetic_cad_factory(tmp_path / "source.dwg")
    original_bytes = original.read_bytes()
    register_t30_sandbox_outputs(tmp_path / "sandbox_root", original.name)

    result = create_dwg_sandbox(str(original), str(tmp_path / "sandbox_root"))

    assert result["status"] == "success"
    assert result["original_dwg_path"] == str(original)
    assert result["sandbox_dwg_path"] != str(original)
    assert result["backup_path"] != str(original)
    assert original.read_bytes() == original_bytes


def test_create_dwg_sandbox_missing_file_returns_structured_failure(tmp_path) -> None:
    from mcp.t30_writeback.sandbox import create_dwg_sandbox

    result = create_dwg_sandbox(str(tmp_path / "missing.dwg"))

    assert result["status"] == "failed"
    assert result["errors"]
