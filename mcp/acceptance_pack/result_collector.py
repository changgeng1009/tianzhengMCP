from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EXPECTED_ARTIFACTS = {
    "t30_probe_result.json": "probe_result",
    "manual_confirmation.json": "manual_confirmation",
}


def collect_acceptance_results(
    artifacts_dir: str,
    output_path: str | None = None,
) -> dict:
    root = Path(artifacts_dir)
    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    for filename, artifact_type in EXPECTED_ARTIFACTS.items():
        path = root / filename
        if path.exists():
            artifacts.append(_artifact(path, artifact_type))
        else:
            missing.append(filename)
    for report_dir_name, json_type, md_type in [
        ("e2e_reports", "e2e_report_json", "e2e_report_markdown"),
        ("acceptance_reports", "acceptance_report_json", "acceptance_report_markdown"),
    ]:
        report_dir = root / report_dir_name
        if report_dir.exists():
            for path in report_dir.glob("*.json"):
                artifact = _artifact(path, json_type)
                artifacts.append(artifact)
                data = artifact.get("data", {})
                warnings.extend(data.get("warnings", []))
                errors.extend(data.get("errors", []))
            for path in report_dir.glob("*.md"):
                artifacts.append(_artifact(path, md_type))
        else:
            missing.append(report_dir_name)
    sandbox_dir = root / "acceptance_sandbox"
    if sandbox_dir.exists():
        for path in sandbox_dir.rglob("*.dwg"):
            artifacts.append(_artifact(path, "sandbox_dwg" if "backup" not in path.name.lower() else "backup_dwg"))
    result = {
        "status": "failed" if errors else ("warning" if missing or warnings else "success"),
        "artifacts": artifacts,
        "missing_artifacts": missing,
        "warnings": warnings,
        "errors": errors,
    }
    if output_path:
        Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _artifact(path: Path, artifact_type: str) -> dict[str, Any]:
    item: dict[str, Any] = {"type": artifact_type, "path": str(path), "name": path.name}
    if path.suffix.lower() == ".json":
        try:
            item["data"] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            item["load_error"] = str(exc)
    return item

