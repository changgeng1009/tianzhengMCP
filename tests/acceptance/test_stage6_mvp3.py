from __future__ import annotations

from pathlib import Path

import yaml

from mcp.orchestration import stage6_mvp3 as stage6


def _sample(reference: Path, target: Path, *, sample_id: str = "sample", blind: bool = False) -> dict:
    return {
        "sample_id": sample_id,
        "reference_path": str(reference),
        "target_path": str(target),
        "scope": "water_supply_and_drainage",
        "expected_region": None,
        "allowed_differences": ["TDbDimension2"],
        "dimension2_required": False,
        "blind_test": blind,
        "notes": "new real sample",
    }


def test_sample_template_contains_pilot_and_two_blind_slots() -> None:
    payload = yaml.safe_load(stage6.SAMPLE_TEMPLATE.read_text(encoding="utf-8"))
    samples = payload["samples"]
    assert len(samples) == 3
    assert sum(bool(sample["blind_test"]) for sample in samples) == 2
    assert all(stage6.REQUIRED_SAMPLE_FIELDS.issubset(sample) for sample in samples)
    assert all(sample["dimension2_required"] is False for sample in samples)


def test_validate_sample_accepts_existing_new_pair(tmp_path: Path, synthetic_cad_factory) -> None:
    reference = tmp_path / "reference.dwg"
    target = tmp_path / "target.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    result = stage6.validate_sample(_sample(reference, target), [])
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_sample_rejects_mvp2_reuse(tmp_path: Path, synthetic_cad_factory) -> None:
    reference = tmp_path / "reference.dwg"
    target = tmp_path / "target.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    result = stage6.validate_sample(_sample(reference, target), [str(reference)])
    assert result["valid"] is False
    assert "reference_reuses_mvp2_sample" in result["errors"]


def test_validate_sample_requires_real_paths_and_distinct_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.dwg"
    result = stage6.validate_sample(_sample(missing, missing), [])
    assert result["valid"] is False
    assert "reference_path_missing" in result["errors"]
    assert "target_path_missing" in result["errors"]
    assert "reference_target_same_path" in result["errors"]


def test_missing_config_returns_empty_sample_gate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(stage6, "SAMPLE_CONFIG", tmp_path / "missing.yaml")
    gate = stage6.load_and_validate_samples({"source_paths": {}})
    assert gate["config_found"] is False
    assert gate["valid_sample_count"] == 0
    assert gate["blind_sample_count"] == 0


def test_hardcoding_boolean_false_means_runtime_is_clean(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "mcp" / "orchestration" / "stage6_mvp3.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("SAMPLE_VALUE = 'dynamic'\n", encoding="utf-8")
    monkeypatch.setattr(stage6, "ROOT", tmp_path)
    paths = stage6.Stage6Paths.build("audit_test")
    monkeypatch.setattr(stage6, "RUNS_ROOT", tmp_path / "artifacts" / "stage6")
    paths = stage6.Stage6Paths.build("audit_test")
    paths.create()
    closure = {
        "source_integrity": {"reference_sha256_after": "a" * 64},
        "evidence": {},
        "ordinary": {"persisted": 16},
        "core_tdb": {"persisted": 331},
        "work_packages": {"successful": 103},
        "dimension2": {"task_ids": ["fixture_task"]},
    }
    audit = stage6.audit_sample_specific_hardcoding(paths, closure)
    assert audit["sample_specific_hardcoding"] is False
    assert audit["runtime_forbidden_count"] == 0


def test_stage6_runtime_has_no_mvp2_fixed_hash_or_transform() -> None:
    source = Path(stage6.__file__).read_text(encoding="utf-8")
    import re
    assert not re.search(r'(?m)^\s*(?:EXPECTED_)?(?:REFERENCE|TARGET)_SHA256\s*=\s*["\'][0-9a-f]{64}', source)
    assert "TRANSLATION = [" not in source
    assert ".SendCommand" not in source
    assert "production_d1_allowed" in source
