from __future__ import annotations

from pathlib import Path
from shutil import copy2
from uuid import uuid4


def create_dwg_sandbox(original_dwg_path: str, sandbox_dir: str | None = None) -> dict:
    original = Path(original_dwg_path)
    result = {
        "status": "failed",
        "original_dwg_path": str(original),
        "sandbox_dwg_path": "",
        "backup_path": "",
        "warnings": [],
        "errors": [],
    }
    if not original.exists():
        result["errors"].append(f"original DWG not found: {original}")
        return result
    if not original.is_file():
        result["errors"].append(f"original DWG is not a file: {original}")
        return result

    try:
        root = Path(sandbox_dir) if sandbox_dir else original.parent / ".t30_writeback_sandbox"
        run_dir = root / f"tx_{uuid4().hex}"
        run_dir.mkdir(parents=True, exist_ok=False)
        sandbox_path = run_dir / original.name
        backup_path = run_dir / f"{original.stem}.backup{original.suffix}"
        copy2(original, sandbox_path)
        copy2(original, backup_path)
        result.update(
            {
                "status": "success",
                "sandbox_dwg_path": str(sandbox_path),
                "backup_path": str(backup_path),
            }
        )
        return result
    except Exception as exc:
        result["errors"].append(str(exc))
        return result

