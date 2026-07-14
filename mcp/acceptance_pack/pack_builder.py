from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.acceptance_pack.command_builder import (
    build_dry_acceptance_command,
    build_probe_command,
    build_real_sandbox_acceptance_command,
)


def build_acceptance_pack(
    output_dir: str,
    project_name: str | None = None,
    options: dict | None = None,
) -> dict:
    options = dict(options or {})
    root = Path(output_dir)
    files: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    project = project_name or "T30真实验收"
    try:
        root.mkdir(parents=True, exist_ok=True)
        contents = _pack_contents(project, options)
        for name, content in contents.items():
            path = root / name
            try:
                path.write_text(content, encoding="utf-8")
                files.append({"name": name, "path": str(path), "bytes": path.stat().st_size})
            except Exception as exc:
                warnings.append(f"file write failed: {name}: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    return {
        "status": "failed" if errors else ("warning" if warnings else "success"),
        "output_dir": str(root),
        "files": files,
        "warnings": warnings,
        "errors": errors,
    }


def _pack_contents(project_name: str, options: dict) -> dict[str, str]:
    scenario = {
        "scenarios": [
            {
                "scenario_id": "first_real_acceptance",
                "name": project_name,
                "reference_sources": [
                    {"type": "png", "role": "reference", "path": "PATH_TO_REFERENCE.png"}
                ],
                "target_dwg_path": "PATH_TO_TARGET_UNFINISHED.dwg",
                "expected_missing": [],
                "manual_anchor_pairs": [],
                "options": {},
            }
        ]
    }
    manual = {
        "TDbPipe.Insert": {
            "confirmed": False,
            "object_type": "TDbPipe",
            "method_name": "Insert",
            "parameters": [],
            "notes": "Fill this only after manual T30 COM verification",
        },
        "TDbPipeValve.Insert": {
            "confirmed": False,
            "object_type": "TDbPipeValve",
            "method_name": "Insert",
            "parameters": [],
        },
        "TDbPipeFitting.Insert": {
            "confirmed": False,
            "object_type": "TDbPipeFitting",
            "method_name": "Insert",
            "parameters": [],
        },
        "TDbSprinkler.Insert": {
            "confirmed": False,
            "object_type": "TDbSprinkler",
            "method_name": "Insert",
            "parameters": [],
        },
    }
    dry_command = build_dry_acceptance_command(
        scenario_path="scenario_template.json",
        probe_result_path="artifacts\\t30_probe_result.json",
        manual_confirmation_path="manual_confirmation.json",
        sandbox_dir="artifacts\\acceptance_sandbox",
        output_dir="artifacts\\acceptance_reports",
    )
    real_command = build_real_sandbox_acceptance_command(
        scenario_path="scenario_template.json",
        probe_result_path="artifacts\\t30_probe_result.json",
        manual_confirmation_path="manual_confirmation.json",
        sandbox_dir="artifacts\\acceptance_sandbox",
        output_dir="artifacts\\acceptance_reports",
    )
    return {
        "scenario_template.json": json.dumps(scenario, ensure_ascii=False, indent=2),
        "manual_confirmation_template.example.json": json.dumps(manual, ensure_ascii=False, indent=2),
        "run_probe.bat": _bat(build_probe_command("artifacts\\t30_probe_result.json"), readonly=True),
        "run_dry_acceptance.bat": _bat(dry_command, readonly=False),
        "run_real_sandbox_acceptance.bat": _bat(
            "REM DANGER: this command enables sandbox real writeback only after checklist approval\r\n" + real_command,
            readonly=False,
        ),
        "checklist.md": _checklist_md(),
        "README.md": _readme_md(project_name),
    }


def _bat(command: str, readonly: bool) -> str:
    note = "REM Read-only probe. Does not write CAD." if readonly else "REM Acceptance command. Review flags before running."
    return f"@echo off\r\n{note}\r\n{command}\r\npause\r\n"


def _readme_md(project_name: str) -> str:
    return f"""# {project_name} Acceptance Pack

## 使用前提

- 必须在真实 AutoCAD + 天正给排水 T30 V1.0 环境运行。
- 第一步运行 `run_probe.bat`，该步骤只读，不写 CAD。
- 第二步根据 probe 结果填写 `manual_confirmation.json`。
- 第三步运行 `run_dry_acceptance.bat`。
- 第四步按 `checklist.md` 完成人工确认。
- 第五步才允许运行 `run_real_sandbox_acceptance.bat`。

原始 DWG 不会被修改。所有真实写回必须进入 sandbox DWG。

只有 sandbox writeback + re-read verification 通过后，才可声明真实补图成功。
"""


def _checklist_md() -> str:
    items = [
        "AutoCAD 已打开",
        "天正给排水 T30 V1.0 已加载",
        "target DWG 是可复制文件",
        "sandbox_dir 已设置",
        "probe_result 已生成",
        "manual_confirmation 已填写",
        "confirmed schema 已生成",
        "dry-run report 已通过人工检查",
        "enable_real_writeback=true 是用户主动开启",
        "real_com_mode=true 是用户主动开启",
        "dry_run_only=false 是用户主动开启",
        "verification_mode=reread_dwg",
        "原始 DWG 不会被修改",
    ]
    return "# 真实写回前 Checklist\n\n" + "\n".join(f"- [ ] {item}" for item in items) + "\n"

