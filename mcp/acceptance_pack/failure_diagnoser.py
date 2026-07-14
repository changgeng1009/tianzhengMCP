from __future__ import annotations


def diagnose_acceptance_failure(collected_result: dict) -> dict:
    artifacts = list(collected_result.get("artifacts", []))
    report = _first_report_data(artifacts)
    warnings = list(collected_result.get("warnings", []))
    errors = list(collected_result.get("errors", []))
    missing = list(collected_result.get("missing_artifacts", []))

    if errors and any("probe" in error.lower() for error in errors):
        return _diagnosis("probe_failed", "probe execution or loading failed", "重新运行 run_probe.bat，并确认 AutoCAD/T30 环境已加载。", errors)
    if report:
        schema = report.get("confirmed_schema_status", {})
        if not schema.get("confirmed_object_types"):
            return _diagnosis("no_confirmed_schema", "no confirmed T30 schema found", "填写 manual_confirmation.json，并确保 probe_result 中对应能力为 confirmed。", schema)
        reread = report.get("reread_verification", {})
        if reread.get("status") in {"failed", "unverified"}:
            return _diagnosis("reread_verification_failed", "re-read verification did not pass", "检查 sandbox DWG、created_entities 与 re-read verifier 输出。", reread)
        writeback = report.get("writeback_result", {})
        if writeback.get("status") == "failed":
            return _diagnosis("writeback_failed", "writeback transaction failed", "查看 acceptance report 的 writeback_result.errors 并修正 schema 或 COM 参数。", writeback)
        if writeback.get("status") in {"dry_run", "skipped"}:
            return _diagnosis("writeback_blocked", "writeback was not executed", "确认 checklist 后再显式开启 real sandbox acceptance。", writeback)
    if any("checklist" in warning.lower() or "gate" in warning.lower() for warning in warnings):
        return _diagnosis("checklist_not_ready", "real writeback checklist is not ready", "逐项完成 checklist.md 后重新运行。", warnings)
    if "t30_probe_result.json" in missing:
        return _diagnosis("probe_failed", "probe result artifact missing", "先运行 run_probe.bat。", missing)
    return _diagnosis("unknown", "failure reason is not classified", "收集完整 artifacts 后重新诊断。", {"warnings": warnings, "errors": errors, "missing": missing})


def _first_report_data(artifacts: list[dict]) -> dict:
    for artifact in artifacts:
        if artifact.get("type") == "acceptance_report_json":
            return dict(artifact.get("data") or {})
    return {}


def _diagnosis(failure_type: str, reason: str, action: str, details) -> dict:
    return {
        "failure_type": failure_type,
        "blocking_reason": reason,
        "suggested_next_action": action,
        "details": details,
    }

