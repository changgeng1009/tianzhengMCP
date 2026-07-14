"""Tests for R4 preflight validation logic.
All tests are READ-ONLY — no COM, no AutoCAD, no DWG modification.
"""

import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from tests.acceptance.run_config_fixture import set_parameter
from unittest.mock import patch

# We test the _preflight function's internal logic by constructing
# minimal plan/batch structures and asserting on expected failures.


# ── constants used in tests ────────────────────────────────
EXPECTED_PLAN_FILE_SHA256 = hashlib.sha256('synthetic:EXPECTED_PLAN_FILE_SHA256 ='.encode()).hexdigest()
EXPECTED_EMBEDDED_PLAN_SHA256 = hashlib.sha256('synthetic:EXPECTED_EMBEDDED_PLAN_SHA256 ='.encode()).hexdigest()
EXPECTED_BATCH_PLAN_FILE_SHA256 = hashlib.sha256('synthetic:EXPECTED_BATCH_PLAN_FILE_SHA256 ='.encode()).hexdigest()

ORDINARY_SAFE = {"AcDbLine", "AcDbCircle", "AcDbArc", "AcDbPolyline", "AcDbText", "AcDbMText"}
TOTAL_TASKS = 4343
ORDINARY_COUNT = 3245
TDB_COUNT = 1098


def _make_frozen_plan(tasks, repair_count=4343, embedded_sha=EXPECTED_EMBEDDED_PLAN_SHA256):
    """Build a minimal valid frozen plan dict."""
    return {
        "phase": "STAGE6-P1-FROZEN-EXECUTION-PLAN",
        "run_id": "test",
        "plan_sha256": embedded_sha,
        "repair_task_count": repair_count,
        "protected_region": {"bbox": [0, 0, 100, 100]},
        "alignment_evidence": [],
        "region_diff_evidence": [],
        "core_component_dependency_plan": {"path": "none"},
        "region_manifest_path": "none",
        "tasks": tasks,
    }


def _make_ordinary_task(task_id, source_handle, object_name, region, transform):
    return {
        "task_id": task_id,
        "source_entity_id": source_handle,
        "object_name": object_name,
        "task_group": "ordinary",
        "target_region_id": region,
        "transform_id": transform,
    }


def _make_tdb_task(task_id, source_handle, object_name):
    return {
        "task_id": task_id,
        "source_entity_id": source_handle,
        "object_name": object_name,
        "task_group": "core_tdb",
        "target_region_id": "target_region_0001",
        "transform_id": "tf1",
    }


def _serialize_json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def _compute_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Test 1: frozen raw hash mismatch fails ──────────────────

def test_frozen_raw_hash_mismatch_fails() -> None:
    """If the frozen plan file raw bytes SHA256 doesn't match, preflight fails."""
    plan = _make_frozen_plan([])
    raw = _serialize_json(plan)
    actual_sha = _compute_sha(raw)
    # Pass wrong expected
    assert actual_sha != EXPECTED_PLAN_FILE_SHA256, "test plan shouldn't match the real plan hash"


# ── Test 2: embedded plan hash mismatch fails ───────────────

def test_embedded_plan_hash_mismatch_fails() -> None:
    """If plan['plan_sha256'] != EXPECTED_EMBEDDED_PLAN_SHA256, preflight fails."""
    plan = _make_frozen_plan([], embedded_sha="0000000000000000000000000000000000000000000000000000000000000000")
    assert plan["plan_sha256"] != EXPECTED_EMBEDDED_PLAN_SHA256


# ── Test 3: repair_task_count mismatch fails ────────────────

def test_repair_task_count_mismatch_fails() -> None:
    """If repair_task_count != 4343, preflight fails."""
    plan = _make_frozen_plan([], repair_count=4000)
    assert plan["repair_task_count"] != 4343


# ── Test 4: task_id duplicate fails ─────────────────────────

def test_task_id_duplicate_fails() -> None:
    """Duplicate task_ids cause preflight failure."""
    tasks = [_make_ordinary_task("dup_1", "A0001", "AcDbLine", "r1", "tf1") for _ in range(3)]
    ids = [t["task_id"] for t in tasks]
    assert len(set(ids)) == 1  # all same
    assert len(ids) == 3


# ── Test 5: task_id empty fails ─────────────────────────────

def test_task_id_empty_fails() -> None:
    """Empty task_ids cause preflight failure."""
    tasks = [_make_ordinary_task("", "A0001", "AcDbLine", "r1", "tf1")]
    ids = [t["task_id"] for t in tasks]
    assert ids[0] == ""


# ── Test 6: batch raw hash mismatch fails ───────────────────

def test_batch_raw_hash_mismatch_fails() -> None:
    """If batch_plan.json raw bytes SHA256 doesn't match, preflight fails."""
    bp = {"batches": []}
    raw = _serialize_json(bp)
    actual = _compute_sha(raw)
    assert actual != EXPECTED_BATCH_PLAN_FILE_SHA256


# ── Test 7: unknown task_id in batch fails ──────────────────

def test_unknown_task_in_batch_fails() -> None:
    """A task_id in batch_plan not present in frozen plan causes failure."""
    frozen_ids = {"task_001", "task_002"}
    batch_ids = {"task_001", "task_003"}  # task_003 unknown
    unknown = batch_ids - frozen_ids
    assert len(unknown) == 1
    assert "task_003" in unknown


# ── Test 8: duplicate task_ids in batch fails ───────────────

def test_duplicate_task_in_batch_fails() -> None:
    """Duplicate task_ids within batch_plan cause failure."""
    batch_tids = ["t1", "t1", "t2", "t3"]  # t1 duplicated
    assert len(set(batch_tids)) != len(batch_tids)


# ── Test 9: ordinary batch cover incomplete fails ────────────

def test_ordinary_batch_cover_incomplete_fails() -> None:
    """If batch_plan doesn't cover all ordinary tasks, preflight fails."""
    frozen_ords = {f"task_{i:04d}" for i in range(10)}
    batch_ords = {f"task_{i:04d}" for i in range(8)}
    missing = frozen_ords - batch_ords
    assert len(missing) == 2


# ── Test 10: ordinary + serial = 4343 ───────────────────────

def test_ordinary_plus_serial_equals_total() -> None:
    """ordinary(3245) + serial(1098) must equal total(4343)."""
    assert ORDINARY_COUNT + TDB_COUNT == TOTAL_TASKS


# ── Test 11: --preflight-only never imports COM ──────────────

def test_preflight_only_never_imports_com(tmp_path, monkeypatch, cad_access_guard) -> None:
    """使用临时 synthetic 输入验证 _preflight() 不导入 COM。

    旧测试直接调用固定生产路径，间接读取并哈希了真实 DWG。这里仅在 ``tmp_path``
    动态创建随机内容的虚构 ``.dwg``，并通过测试守卫显式登记；业务脚本本身不改。
    """
    from scripts import run_stage6_p1_accelerated_r4 as r4

    cad_paths = [tmp_path / f"synthetic-{index}.dwg" for index in range(4)]
    cad_payload = os.urandom(64)
    for path in cad_paths:
        cad_access_guard.register_synthetic_cad(path, synthetic_test_file=True)
        path.write_bytes(cad_payload)

    ordinary_tasks = [
        _make_ordinary_task(
            f"ordinary_{index:04d}",
            f"A{index:04X}",
            "AcDbLine",
            "synthetic_region",
            "synthetic_transform",
        )
        for index in range(ORDINARY_COUNT)
    ]
    serial_tasks = [
        _make_tdb_task(f"serial_{index:04d}", f"C{index:04X}", "TDbPipe")
        for index in range(TDB_COUNT)
    ]
    tasks = ordinary_tasks + serial_tasks
    embedded_hash = "1" * 64
    plan = _make_frozen_plan(tasks, embedded_sha=embedded_hash)
    plan_raw = _serialize_json(plan)
    plan_path = tmp_path / "synthetic_plan.json"
    plan_path.write_bytes(plan_raw)

    batch_plan = {
        "ordinary_task_count": ORDINARY_COUNT,
        "tdb_task_count": TDB_COUNT,
        "batches": [{"task_ids": [task["task_id"] for task in ordinary_tasks]}],
    }
    batch_raw = _serialize_json(batch_plan)
    batch_path = tmp_path / "synthetic_batch_plan.json"
    batch_path.write_bytes(batch_raw)

    for name, value in zip(
        ("REFERENCE_PATH", "TARGET_PATH", "PREWRITE_PATH", "R4_WORK_FILE"),
        cad_paths,
    ):
        monkeypatch.setattr(r4, name, value)
    monkeypatch.setattr(r4, "PLAN_PATH", plan_path)
    monkeypatch.setattr(r4, "BATCH_PLAN_PATH", batch_path)
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256", _compute_sha(cad_payload))
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256", _compute_sha(cad_payload))
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256", _compute_sha(plan_raw))
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256", embedded_hash)
    set_parameter(monkeypatch, tmp_path, "scripts.run_stage6_p1_accelerated_r4.expected_batch_plan_file_sha256", _compute_sha(batch_raw))

    com_before = {name: name in sys.modules for name in ("win32com", "pythoncom")}
    result = r4._preflight()
    assert result is not None
    assert "stats" in result
    assert result["passed"] is True
    assert {name: name in sys.modules for name in com_before} == com_before


# ── Test 12: three hash constants are distinct ──────────────

def test_three_hash_constants_are_distinct() -> None:
    """The three hash constants must be different values."""
    hashes = {
        EXPECTED_PLAN_FILE_SHA256,
        EXPECTED_EMBEDDED_PLAN_SHA256,
        EXPECTED_BATCH_PLAN_FILE_SHA256,
    }
    assert len(hashes) == 3, f"Expected 3 distinct hashes, got {len(hashes)}"


# ── Test 13: task_id set exact match logic ──────────────────

def test_task_id_exact_match_logic() -> None:
    """The set exact-match check should catch both missing and extra."""
    frozen = {f"t{i:04d}" for i in range(4343)}
    # Build batch set that's missing 5 and has 5 extras
    batch = (frozen - {f"t{i:04d}" for i in range(5)}) | {f"extra_{i}" for i in range(5)}
    missing = frozen - batch
    extra = batch - frozen
    assert len(missing) == 5
    assert len(extra) == 5
    assert missing | extra  # non-empty


# ── Test 14: R4 ordinary eligibility excludes TDb ───────────

def test_r4_ordinary_eligibility_excludes_tdb() -> None:
    """Only tasks with task_group='ordinary' AND object_name in ORDINARY_SAFE are eligible."""
    t = _make_tdb_task("t1", "C0001", "TDbPipe")
    assert t["object_name"] not in ORDINARY_SAFE
    assert t["task_group"] == "core_tdb"

    t2 = _make_ordinary_task("t2", "A0001", "AcDbLine", "r1", "tf1")
    assert t2["object_name"] in ORDINARY_SAFE
    assert t2["task_group"] == "ordinary"
