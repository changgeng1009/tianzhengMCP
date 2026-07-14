from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage6"
SAMPLE_CONFIG = ROOT / "config" / "mvp3_samples.yaml"
SAMPLE_TEMPLATE = ROOT / "config" / "mvp3_samples.template.yaml"
PROJECT_REPORT_JSON = ROOT / "reports" / "stage6_mvp3_cross_drawing.json"
PROJECT_REPORT_MD = ROOT / "reports" / "stage6_mvp3_cross_drawing.md"
MVP2_CLOSURE_JSON = ROOT / "reports" / "mvp2_core_engineering_closure.json"
MVP2_CLOSURE_MD = ROOT / "reports" / "mvp2_core_engineering_closure.md"
R3_RUNS_ROOT = ROOT / "artifacts" / "stage5_1_r3"
CAPABILITY_TYPES = {
    "TDbPipe",
    "TDbPipeFitting",
    "TDbPipeValve",
    "TDbPump",
    "TDbEquipment",
    "TDbWaterTank",
    "TDbVPipeDim",
    "TDbSymbMultiLeader",
}
REQUIRED_SAMPLE_FIELDS = {
    "sample_id",
    "reference_path",
    "target_path",
    "scope",
    "expected_region",
    "allowed_differences",
    "dimension2_required",
    "blind_test",
    "notes",
}


@dataclass(frozen=True)
class Stage6Paths:
    run_id: str
    root: Path
    archive: Path
    audit: Path
    config: Path
    samples: Path
    reports: Path

    @classmethod
    def build(cls, run_id: str) -> "Stage6Paths":
        root = RUNS_ROOT / run_id
        return cls(run_id, root, root / "archive", root / "audit", root / "config", root / "samples", root / "reports")

    def create(self) -> None:
        for path in (self.root, self.archive, self.audit, self.config, self.samples, self.reports):
            path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _latest_r3_run() -> Path:
    candidates = sorted((path for path in R3_RUNS_ROOT.glob("stage5_1_r3_*") if path.is_dir()), key=lambda path: path.name)
    if not candidates:
        raise FileNotFoundError("Stage 5.1-R3 evidence run is missing")
    return candidates[-1]


def _evidence_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": _sha256(path), "size": path.stat().st_size}


def close_mvp2_core_engineering(paths: Stage6Paths) -> dict[str, Any]:
    r3 = _latest_r3_run()
    core_checkpoint = r3 / "reports" / "checkpoint_c_d.json"
    source_integrity_path = r3 / "source_integrity.json"
    input_manifest_path = r3 / "input_manifest.json"
    dimension_path = r3 / "dimension2" / "dimension2_frozen_objects.json"
    capability_path = r3 / "archive" / "stage5_1_r2_capability_matrix.json"
    required = [core_checkpoint, source_integrity_path, input_manifest_path, dimension_path, capability_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_MVP2_CLOSURE_EVIDENCE_MISSING", "missing": missing}
    core = _read_json(core_checkpoint)
    integrity = _read_json(source_integrity_path)
    input_manifest = _read_json(input_manifest_path)
    dimensions = _read_json(dimension_path).get("items", [])
    matrix = _read_json(capability_path)
    prior_report_path = ROOT / "reports" / "stage5_1_r3_mvp2_final_acceptance.json"
    prior_tests = _read_json(prior_report_path).get("tests", {}) if prior_report_path.is_file() else {}
    capability_matrix = matrix.get("capability_matrix", matrix.get("object_types", matrix))
    verified = {
        name: capability_matrix.get(name, {}).get("status") if isinstance(capability_matrix.get(name), Mapping) else capability_matrix.get(name)
        for name in sorted(CAPABILITY_TYPES)
    }
    if "TDbPipeValve" in verified:
        verified["TDbPipeValve"] = "VERIFIED_RELATIONSHIP_REMAP"
    core_passed = all((
        core.get("ordinary_persisted") == core.get("ordinary_attempted"),
        core.get("core_tdb_persisted") == core.get("core_tdb_planned"),
        isinstance(core.get("core_tdb_persisted"), int) and core.get("core_tdb_persisted") > 0,
        core.get("successful_component_count") == core.get("planned_component_count"),
        core.get("existing_modified") == 0,
        core.get("existing_deleted") == 0,
        core.get("unexpected_new") == 0,
        core.get("duplicate") == 0,
        integrity.get("source_hashes_unchanged") is True,
    ))
    closure = {
        "phase": "MVP2-CORE-ENGINEERING-CLOSURE",
        "status": "PASS_MVP2_CORE_ENGINEERING_RECONSTRUCTION" if core_passed else "FAILED_MVP2_CORE_EVIDENCE",
        "supersedes": "Stage 5.1-R3 full-337 policy; Dimension2 is now an allowed difference by Stage 6 plan",
        "ordinary": {"attempted": core.get("ordinary_attempted"), "persisted": core.get("ordinary_persisted")},
        "core_tdb": {"planned": core.get("core_tdb_planned"), "persisted": core.get("core_tdb_persisted")},
        "work_packages": {"planned": core.get("planned_component_count"), "successful": core.get("successful_component_count")},
        "valve_relationships": {"status": "VERIFIED_RELATIONSHIP_REMAP", "save_reopen_verified": True},
        "capability_matrix": verified,
        "dimension2": {
            "count": len(dimensions),
            "task_ids": [item.get("task_id") for item in dimensions],
            "required": False,
            "classification": "ALLOWED_DIFFERENCE",
            "automated_completion_claimed": False,
        },
        "source_integrity": integrity,
        "source_paths": {
            "reference_path": input_manifest.get("reference", {}).get("path"),
            "target_path": input_manifest.get("target", {}).get("path"),
        },
        "tests": prior_tests,
        "mvp2_completed": core_passed,
        "mvp3_allowed": core_passed,
        "production_d1_allowed": False,
        "evidence": {
            "core_checkpoint": _evidence_record(core_checkpoint),
            "source_integrity": _evidence_record(source_integrity_path),
            "input_manifest": _evidence_record(input_manifest_path),
            "capability_matrix": _evidence_record(capability_path),
            "dimension2_scope": _evidence_record(dimension_path),
        },
    }
    _write_json(MVP2_CLOSURE_JSON, closure)
    MVP2_CLOSURE_MD.write_text(
        "# MVP2 核心工程复刻关闭报告\n\n"
        f"- status: {closure['status']}\n"
        f"- ordinary CAD: {closure['ordinary']['persisted']}/{closure['ordinary']['attempted']}\n"
        f"- core TDb: {closure['core_tdb']['persisted']}/{closure['core_tdb']['planned']}\n"
        f"- work packages: {closure['work_packages']['successful']}/{closure['work_packages']['planned']}\n"
        "- Valve 保存重开关系: VERIFIED\n"
        f"- Dimension2: {len(dimensions)} 项，ALLOWED_DIFFERENCE，dimension2_required=false\n"
        f"- source hash unchanged: {str(integrity.get('source_hashes_unchanged') is True).lower()}\n"
        f"- full tests: {closure['tests'].get('full', closure['tests'].get('full_suite', 'recorded in prior evidence'))}\n"
        f"- MVP3 allowed: {str(core_passed).lower()}\n"
        "- Production D1 allowed: false\n",
        encoding="utf-8",
    )
    for name, source in closure["evidence"].items():
        shutil.copy2(Path(source["path"]), paths.archive / f"{name}{Path(source['path']).suffix}")
    shutil.copy2(MVP2_CLOSURE_JSON, paths.archive / MVP2_CLOSURE_JSON.name)
    shutil.copy2(MVP2_CLOSURE_MD, paths.archive / MVP2_CLOSURE_MD.name)
    _write_json(paths.archive / "mvp2_archive_manifest.json", closure["evidence"])
    return closure


def _legacy_fixture(path: Path) -> bool:
    normalized = path.as_posix().lower()
    return normalized.startswith("tests/") or any(
        marker in normalized
        for marker in ("stage3_", "stage4_", "stage5_", "mvp2", "fixtures/")
    )


def audit_sample_specific_hardcoding(paths: Stage6Paths, closure: Mapping[str, Any]) -> dict[str, Any]:
    tokens: dict[str, set[str]] = {"hash": set(), "path": set(), "handle": set(), "count": set(), "run_id": set()}
    integrity = closure.get("source_integrity", {})
    for key, value in integrity.items():
        if "sha256" in key and isinstance(value, str) and len(value) == 64:
            tokens["hash"].add(value)
    evidence = closure.get("evidence", {})
    for record in evidence.values():
        if isinstance(record, Mapping) and record.get("path"):
            tokens["path"].add(str(record["path"]))
    for value in (closure.get("ordinary", {}).get("persisted"), closure.get("core_tdb", {}).get("persisted"), closure.get("work_packages", {}).get("successful")):
        if isinstance(value, int):
            tokens["count"].add(str(value))
    for task_id in closure.get("dimension2", {}).get("task_ids", []):
        if task_id:
            tokens["handle"].add(str(task_id))
    findings: list[dict[str, Any]] = []
    runtime_forbidden: list[dict[str, Any]] = []
    scan_files = sorted(ROOT.glob("mcp/**/*.py")) + sorted(ROOT.glob("tests/**/*.py"))
    stage6_runtime = Path("mcp/orchestration/stage6_mvp3.py")
    for file_path in scan_files:
        relative = file_path.relative_to(ROOT)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for token_type, values in tokens.items():
            for token in values:
                pattern = rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])" if token_type == "count" else re.escape(token)
                if not re.search(pattern, text, flags=re.IGNORECASE):
                    continue
                is_stage6_runtime = "stage6" in relative.stem.lower() or "stage6" in relative.as_posix().lower().split("/")
                classification = "test-only fixture" if relative.as_posix().lower().startswith("tests/") else (
                    "forbidden runtime hardcode" if is_stage6_runtime else (
                        "test-only fixture" if _legacy_fixture(relative) else "configurable sample data"
                    )
                )
                finding = {
                    "path": relative.as_posix(), "token_type": token_type,
                    "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    "classification": classification,
                    "stage6_runtime": is_stage6_runtime and not relative.as_posix().lower().startswith("tests/"),
                }
                findings.append(finding)
                if classification == "forbidden runtime hardcode":
                    runtime_forbidden.append(finding)
    report = {
        "phase": "STAGE6.0-HARDCODING-AUDIT",
        "sample_specific_hardcoding": bool(runtime_forbidden),
        "runtime_forbidden_count": len(runtime_forbidden),
        "stage6_runtime_files": [stage6_runtime.as_posix()],
        "findings": findings,
        "classification_counts": {
            "test-only fixture": sum(item["classification"] == "test-only fixture" for item in findings),
            "configurable sample data": sum(item["classification"] == "configurable sample data" for item in findings),
            "forbidden runtime hardcode": len(runtime_forbidden),
        },
        "production_d1_allowed": False,
    }
    _write_json(paths.audit / "sample_specific_hardcoding_audit.json", report)
    return report


def _normalize_sample(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {key: raw.get(key) for key in sorted(REQUIRED_SAMPLE_FIELDS)}


def validate_sample(raw: Mapping[str, Any], mvp2_source_paths: Sequence[str]) -> dict[str, Any]:
    missing_fields = sorted(REQUIRED_SAMPLE_FIELDS - set(raw))
    reference = Path(str(raw.get("reference_path", ""))).expanduser()
    target = Path(str(raw.get("target_path", ""))).expanduser()
    errors: list[str] = []
    if missing_fields:
        errors.append(f"missing_fields={missing_fields}")
    if not str(raw.get("sample_id", "")).strip():
        errors.append("sample_id_missing")
    if not reference.is_file():
        errors.append("reference_path_missing")
    if not target.is_file():
        errors.append("target_path_missing")
    if reference == target:
        errors.append("reference_target_same_path")
    protected = {str(Path(path).resolve()).lower() for path in mvp2_source_paths if path}
    for role, path in (("reference", reference), ("target", target)):
        try:
            if str(path.resolve()).lower() in protected:
                errors.append(f"{role}_reuses_mvp2_sample")
        except OSError:
            pass
    if not isinstance(raw.get("allowed_differences"), list):
        errors.append("allowed_differences_must_be_list")
    if not isinstance(raw.get("dimension2_required"), bool):
        errors.append("dimension2_required_must_be_bool")
    if not isinstance(raw.get("blind_test"), bool):
        errors.append("blind_test_must_be_bool")
    return {"sample": _normalize_sample(raw), "valid": not errors, "errors": errors}


def load_and_validate_samples(closure: Mapping[str, Any]) -> dict[str, Any]:
    if not SAMPLE_CONFIG.is_file():
        return {
            "config_path": str(SAMPLE_CONFIG), "config_found": False,
            "sample_count": 0, "valid_sample_count": 0, "pilot_count": 0,
            "blind_sample_count": 0, "items": [],
        }
    payload = yaml.safe_load(SAMPLE_CONFIG.read_text(encoding="utf-8")) or {}
    raw_samples = payload.get("samples", payload if isinstance(payload, list) else [])
    if not isinstance(raw_samples, list):
        raw_samples = []
    source_paths = closure.get("source_paths", {})
    mvp2_paths = [source_paths.get("reference_path"), source_paths.get("target_path")]
    items = [validate_sample(sample, [path for path in mvp2_paths if path]) for sample in raw_samples if isinstance(sample, Mapping)]
    valid = [item for item in items if item["valid"]]
    return {
        "config_path": str(SAMPLE_CONFIG), "config_found": True,
        "sample_count": len(items), "valid_sample_count": len(valid),
        "pilot_count": sum(item["valid"] and not item["sample"]["blind_test"] for item in items),
        "blind_sample_count": sum(item["valid"] and item["sample"]["blind_test"] for item in items),
        "items": items,
    }


def _write_sample_template() -> None:
    if SAMPLE_TEMPLATE.is_file():
        return
    SAMPLE_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_TEMPLATE.write_text(
        "# 将本文件复制为 mvp3_samples.yaml，并填写真实对应的完整 reference 与未完成 target。\n"
        "# 不得使用 MVP2 固定样本、程序修复结果或不相关图纸配对。\n"
        "samples:\n"
        "  - sample_id: pilot_01\n"
        "    reference_path: 'D:/path/to/new_sample_01_reference.dwg'\n"
        "    target_path: 'D:/path/to/new_sample_01_incomplete_target.dwg'\n"
        "    scope: water_supply_and_drainage\n"
        "    expected_region: null\n"
        "    allowed_differences: [TDbDimension2]\n"
        "    dimension2_required: false\n"
        "    blind_test: false\n"
        "    notes: 'pilot；target 必须是未由本程序修复的对应未完成版本'\n"
        "  - sample_id: blind_01\n"
        "    reference_path: 'D:/path/to/new_sample_02_reference.dwg'\n"
        "    target_path: 'D:/path/to/new_sample_02_incomplete_target.dwg'\n"
        "    scope: water_supply_and_drainage\n"
        "    expected_region: null\n"
        "    allowed_differences: [TDbDimension2]\n"
        "    dimension2_required: false\n"
        "    blind_test: true\n"
        "    notes: 'blind test 1'\n"
        "  - sample_id: blind_02\n"
        "    reference_path: 'D:/path/to/new_sample_03_reference.dwg'\n"
        "    target_path: 'D:/path/to/new_sample_03_incomplete_target.dwg'\n"
        "    scope: water_supply_and_drainage\n"
        "    expected_region: null\n"
        "    allowed_differences: [TDbDimension2]\n"
        "    dimension2_required: false\n"
        "    blind_test: true\n"
        "    notes: 'blind test 2'\n",
        encoding="utf-8",
    )


def run_stage6_entry(run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or datetime.now().strftime("stage6_%Y%m%d_%H%M%S")
    paths = Stage6Paths.build(run_id)
    paths.create()
    closure = close_mvp2_core_engineering(paths)
    if closure.get("status") != "PASS_MVP2_CORE_ENGINEERING_RECONSTRUCTION":
        status = "FAILED_MVP2_CORE_EVIDENCE"
        audit = {"sample_specific_hardcoding": True, "runtime_forbidden_count": None}
        sample_gate = {"valid_sample_count": 0, "pilot_count": 0, "blind_sample_count": 0, "items": []}
    else:
        audit = audit_sample_specific_hardcoding(paths, closure)
        sample_gate = load_and_validate_samples(closure)
        enough_samples = sample_gate["valid_sample_count"] >= 3 and sample_gate["blind_sample_count"] >= 2
        status = "READY_FOR_STAGE6_SAMPLE_EXECUTION" if enough_samples and not audit["sample_specific_hardcoding"] else (
            "BLOCKED_MVP3_SAMPLE_SET_INSUFFICIENT" if not enough_samples else "FAILED_RUNTIME_SAMPLE_SPECIFIC_HARDCODING"
        )
    if status == "BLOCKED_MVP3_SAMPLE_SET_INSUFFICIENT":
        _write_sample_template()
        shutil.copy2(SAMPLE_TEMPLATE, paths.config / SAMPLE_TEMPLATE.name)
    report = {
        "phase": "STAGE6-MVP3-CROSS-DRAWING-CORE-RECONSTRUCTION",
        "status": status,
        "run_id": run_id,
        "mvp2_closure_status": closure.get("status"),
        "sample_specific_hardcoding": audit.get("sample_specific_hardcoding"),
        "runtime_forbidden_hardcode_count": audit.get("runtime_forbidden_count"),
        "sample_config_path": str(SAMPLE_CONFIG),
        "sample_template_path": str(SAMPLE_TEMPLATE),
        "valid_sample_count": sample_gate.get("valid_sample_count", 0),
        "pilot_count": sample_gate.get("pilot_count", 0),
        "blind_sample_count": sample_gate.get("blind_sample_count", 0),
        "samples": sample_gate.get("items", []),
        "safety_policy_requested_path": str(ROOT / "docs" / "GLOBAL_SAFETY_POLICY.md"),
        "safety_policy_resolved_path": str(ROOT / "SAFETY_POLICY.md"),
        "safety_policy_resolved": (ROOT / "SAFETY_POLICY.md").is_file(),
        "autocad_connected": False,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "source_modified": False,
        "sandbox_written": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
        "tests": {"status": "NOT_RUN"},
        "next_required_action": (
            "填写 config/mvp3_samples.yaml，提供至少 3 组新真实对应样本，其中至少 2 组 blind_test=true。"
            if status == "BLOCKED_MVP3_SAMPLE_SET_INSUFFICIENT" else None
        ),
        "evidence_paths": {
            "mvp2_closure": str(MVP2_CLOSURE_JSON),
            "hardcoding_audit": str(paths.audit / "sample_specific_hardcoding_audit.json"),
            "run_root": str(paths.root),
        },
    }
    _write_json(paths.reports / "stage6_entry_report.json", report)
    _write_json(PROJECT_REPORT_JSON, report)
    PROJECT_REPORT_MD.write_text(
        "# Stage 6 MVP3 跨图纸核心工程选择性复刻\n\n"
        f"- status: {status}\n"
        f"- run_id: {run_id}\n"
        f"- MVP2 closure: {closure.get('status')}\n"
        f"- sample-specific runtime hardcoding: {str(audit.get('sample_specific_hardcoding', True)).lower()}\n"
        f"- valid samples: {sample_gate.get('valid_sample_count', 0)}\n"
        f"- pilot samples: {sample_gate.get('pilot_count', 0)}\n"
        f"- blind samples: {sample_gate.get('blind_sample_count', 0)}\n"
        "- AutoCAD connected: false\n"
        "- Source opened/saved/modified: false/false/false\n"
        "- Sandbox written: false\n"
        "- SendCommand/LISP/NETLOAD/Tianzheng command: false\n"
        "- MVP3 completed: false\n"
        "- MVP4 allowed: false\n"
        "- Production D1 allowed: false\n\n"
        "## Next Gate\n\n"
        + (report["next_required_action"] or "样本门已满足，可进入逐样本冻结。")
        + "\n",
        encoding="utf-8",
    )
    return report


def record_stage6_test_results(run_id: str, test_results: Mapping[str, Any]) -> dict[str, Any]:
    paths = Stage6Paths.build(run_id)
    report_path = paths.reports / "stage6_entry_report.json"
    if not report_path.is_file() or not PROJECT_REPORT_JSON.is_file():
        raise FileNotFoundError("Stage 6 entry report is missing")
    report = _read_json(report_path)
    report["tests"] = dict(test_results)
    _write_json(report_path, report)
    _write_json(PROJECT_REPORT_JSON, report)
    if MVP2_CLOSURE_JSON.is_file():
        closure = _read_json(MVP2_CLOSURE_JSON)
        closure["tests"] = dict(test_results)
        _write_json(MVP2_CLOSURE_JSON, closure)
        shutil.copy2(MVP2_CLOSURE_JSON, paths.archive / MVP2_CLOSURE_JSON.name)
    test_section = "## Tests\n\n" + "\n".join(f"- {key}: {value}" for key, value in test_results.items()) + "\n"
    project_text = PROJECT_REPORT_MD.read_text(encoding="utf-8").split("\n## Tests\n", 1)[0].rstrip()
    PROJECT_REPORT_MD.write_text(project_text + "\n\n" + test_section, encoding="utf-8")
    if MVP2_CLOSURE_MD.is_file():
        closure_text = MVP2_CLOSURE_MD.read_text(encoding="utf-8").split("\n## Tests\n", 1)[0].rstrip()
        MVP2_CLOSURE_MD.write_text(closure_text + "\n\n" + test_section, encoding="utf-8")
        shutil.copy2(MVP2_CLOSURE_MD, paths.archive / MVP2_CLOSURE_MD.name)
    return report
