from __future__ import annotations

from pathlib import Path
import site


def _append_external_mcp_sdk_path() -> None:
    current_path = Path(__file__).resolve().parent
    candidates: list[str] = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass

    for candidate in candidates:
        sdk_path = Path(candidate) / "mcp"
        if sdk_path.exists() and sdk_path.resolve() != current_path:
            path_text = str(sdk_path)
            if path_text not in __path__:
                __path__.append(path_text)


_append_external_mcp_sdk_path()

