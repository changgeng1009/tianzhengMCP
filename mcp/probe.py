from __future__ import annotations

from typing import Any


CAPABILITY_KEYS = (
    "TDbPipe.Insert",
    "TDbValve.Insert",
    "TDbSprinkler.Insert",
    "TDbPipeFitting.Insert",
)


def probe_t30_capabilities(capability_source: Any | None = None) -> dict[str, Any]:
    if capability_source is None:
        result = {key: False for key in CAPABILITY_KEYS}
        result.update(
            {
                "source": "no_capability_source",
                "notes": "未提供真实 T30 COM 能力源；不假设 Insert 可用。",
            }
        )
        return result

    if isinstance(capability_source, dict):
        result = {key: bool(capability_source.get(key, False)) for key in CAPABILITY_KEYS}
        result.update(
            {
                "source": "provided_capability_source",
                "notes": "能力来自显式传入的 capability source。",
            }
        )
        return result

    result = {
        key: _has_insert_method(capability_source, key.split(".")[0])
        for key in CAPABILITY_KEYS
    }
    result.update(
        {
            "source": "com_object_probe",
            "notes": "通过对象属性探测 Insert 方法，仅表示当前对象可见性。",
        }
    )
    return result


def _has_insert_method(source: Any, object_name: str) -> bool:
    try:
        target = getattr(source, object_name)
    except Exception:
        return False
    try:
        return callable(getattr(target, "Insert"))
    except Exception:
        return False

