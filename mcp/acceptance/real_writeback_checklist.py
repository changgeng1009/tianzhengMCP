from __future__ import annotations

from pathlib import Path

from mcp.acceptance.models import AcceptanceRunConfig


def generate_real_writeback_checklist(
    config: AcceptanceRunConfig,
    confirmed_schema_status: dict | None = None,
) -> dict:
    confirmed_schema_status = dict(confirmed_schema_status or {})
    blocking: list[str] = []
    warnings: list[str] = []
    if not Path(config.scenario_path).exists():
        blocking.append("scenario_path_missing")
    if not Path(config.probe_result_path).exists():
        blocking.append("probe_result_path_missing")
    if not Path(config.manual_confirmation_path).exists():
        blocking.append("manual_confirmation_path_missing")
    try:
        Path(config.sandbox_dir).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        blocking.append("sandbox_dir_not_writable")
        warnings.append(str(exc))
    if not config.enable_real_writeback:
        blocking.append("enable_real_writeback_not_true")
    if not config.real_com_mode:
        blocking.append("real_com_mode_not_true")
    if config.dry_run_only:
        blocking.append("dry_run_only_true")
    if config.verification_mode not in {"reread_dwg", "manual_review"}:
        blocking.append("verification_mode_not_real_acceptance")
    if not confirmed_schema_status.get("confirmed_object_types"):
        blocking.append("confirmed_schema_missing")
    return {
        "ready": not blocking,
        "blocking_items": blocking,
        "warnings": warnings,
        "safety_summary": {
            "writes_original_dwg": False,
            "target_write_scope": "sandbox_only",
            "enable_real_writeback": config.enable_real_writeback,
            "real_com_mode": config.real_com_mode,
            "dry_run_only": config.dry_run_only,
            "verification_mode": config.verification_mode,
        },
    }

