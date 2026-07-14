from __future__ import annotations


def test_command_builder_defaults_do_not_real_write_and_quote_paths() -> None:
    from mcp.acceptance_pack.command_builder import (
        build_dry_acceptance_command,
        build_probe_command,
    )

    probe = build_probe_command("C:\\Project Dir\\artifacts\\t30_probe_result.json")
    dry = build_dry_acceptance_command(
        scenario_path="C:\\Project Dir\\scenario.json",
        probe_result_path="C:\\Project Dir\\artifacts\\t30_probe_result.json",
        manual_confirmation_path="C:\\Project Dir\\manual confirmation.json",
        sandbox_dir="C:\\Project Dir\\sandbox",
        output_dir="C:\\Project Dir\\reports",
    )

    assert '"C:\\Project Dir\\artifacts\\t30_probe_result.json"' in probe
    assert "--dry-run-only true" in dry
    assert "--enable-real-writeback false" in dry
    assert "--real-com-mode false" in dry
    assert '"C:\\Project Dir\\manual confirmation.json"' in dry


def test_real_sandbox_command_requires_explicit_real_flags() -> None:
    from mcp.acceptance_pack.command_builder import build_real_sandbox_acceptance_command

    command = build_real_sandbox_acceptance_command(
        scenario_path="scenario.json",
        probe_result_path="artifacts\\t30_probe_result.json",
        manual_confirmation_path="artifacts\\manual_confirmation.json",
        sandbox_dir="artifacts\\sandbox",
        output_dir="artifacts\\reports",
    )

    assert "--dry-run-only false" in command
    assert "--enable-real-writeback true" in command
    assert "--real-com-mode true" in command
    assert "--verification-mode reread_dwg" in command
    assert "sandbox" in command

