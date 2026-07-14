@echo off
REM Acceptance command. Review flags before running.
REM DANGER: this command enables sandbox real writeback only after checklist approval
python -m mcp.acceptance.acceptance_runner --scenario "scenario_template.json" --probe-result "artifacts\t30_probe_result.json" --manual-confirmation "manual_confirmation.json" --sandbox-dir "artifacts\acceptance_sandbox" --output-dir "artifacts\acceptance_reports" --dry-run-only false --enable-real-writeback true --real-com-mode true --verification-mode reread_dwg
pause
