@echo off
REM Read-only probe. Does not write CAD.
python -m mcp.t30_writeback.manual_probe_runner --output "artifacts\t30_probe_result.json" --target-dwg "artifactsreal.test.001\target.dwg"
pause
