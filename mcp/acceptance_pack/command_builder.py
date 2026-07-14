from __future__ import annotations


def build_probe_command(
    output_path: str = "artifacts\\t30_probe_result.json",
    target_dwg_path: str | None = None,
    allow_open_document: bool = False,
) -> str:
    parts = ["python -m mcp.t30_writeback.manual_probe_runner", "--output", _quote(output_path)]
    if target_dwg_path:
        parts.extend(["--target-dwg", _quote(target_dwg_path)])
    if allow_open_document:
        parts.append("--allow-open-document")
    return " ".join(parts)


def build_dry_acceptance_command(
    scenario_path: str = "scenario_template.json",
    probe_result_path: str = "artifacts\\t30_probe_result.json",
    manual_confirmation_path: str = "manual_confirmation.json",
    sandbox_dir: str = "artifacts\\acceptance_sandbox",
    output_dir: str = "artifacts\\acceptance_reports",
) -> str:
    return " ".join(
        [
            "python -m mcp.acceptance.acceptance_runner",
            "--scenario",
            _quote(scenario_path),
            "--probe-result",
            _quote(probe_result_path),
            "--manual-confirmation",
            _quote(manual_confirmation_path),
            "--sandbox-dir",
            _quote(sandbox_dir),
            "--output-dir",
            _quote(output_dir),
            "--dry-run-only true",
            "--enable-real-writeback false",
            "--real-com-mode false",
            "--verification-mode manual_review",
        ]
    )


def build_real_sandbox_acceptance_command(
    scenario_path: str,
    probe_result_path: str,
    manual_confirmation_path: str,
    sandbox_dir: str,
    output_dir: str,
) -> str:
    return " ".join(
        [
            "python -m mcp.acceptance.acceptance_runner",
            "--scenario",
            _quote(scenario_path),
            "--probe-result",
            _quote(probe_result_path),
            "--manual-confirmation",
            _quote(manual_confirmation_path),
            "--sandbox-dir",
            _quote(sandbox_dir),
            "--output-dir",
            _quote(output_dir),
            "--dry-run-only false",
            "--enable-real-writeback true",
            "--real-com-mode true",
            "--verification-mode reread_dwg",
        ]
    )


def _quote(path: str) -> str:
    escaped = str(path).replace('"', '\\"')
    return f'"{escaped}"'
