@echo off
REM Acceptance command. Review flags before running.
python -m mcp.acceptance.acceptance_runner --scenario "artifactsreal.test.001\scenario_real_test_001.json" --probe-result "artifacts\t30_probe_result.json" --manual-confirmation "manual_confirmation.json" --sandbox-dir "artifacts\acceptance_sandbox" --output-dir "artifacts\acceptance_reports" --dry-run-only true --enable-real-writeback false --real-com-mode false --verification-mode manual_review
pause
