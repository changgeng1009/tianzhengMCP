from __future__ import annotations

from collections import defaultdict
from typing import Any


class T30ObjectFactory:
    def __init__(self, fake_mode: bool = True, com_environment: Any | None = None, confirmed_capabilities: dict | None = None) -> None:
        self.fake_mode = bool(fake_mode)
        self.com_environment = com_environment
        self.confirmed_capabilities = dict(confirmed_capabilities or {})
        self._counters: dict[str, int] = defaultdict(int)

    def create_pipe(self, parameters: dict) -> dict:
        return self._create("pipe", "TDbPipe", parameters)

    def create_valve(self, parameters: dict) -> dict:
        return self._create("valve", "TDbPipeValve", parameters)

    def create_sprinkler(self, parameters: dict) -> dict:
        return self._create("sprinkler", "TDbSprinkler", parameters)

    def create_fitting(self, parameters: dict) -> dict:
        return self._create("fitting", "TDbPipeFitting", parameters)

    def create_by_object_type(self, object_type: str, parameters: dict) -> dict:
        if object_type == "TDbPipe":
            return self.create_pipe(parameters)
        if object_type == "TDbPipeValve":
            return self.create_valve(parameters)
        if object_type == "TDbSprinkler":
            return self.create_sprinkler(parameters)
        if object_type == "TDbPipeFitting":
            return self.create_fitting(parameters)
        return {"status": "failed", "success": False, "errors": [f"unsupported object type: {object_type}"]}

    def _create(self, kind: str, object_type: str, parameters: dict) -> dict:
        missing = [field for field in ("geometry", "system", "layer") if not parameters.get(field)]
        if object_type == "TDbPipe" and not parameters.get("dn"):
            missing.append("dn")
        if missing:
            return {"status": "failed", "success": False, "object_type": object_type, "errors": [f"missing parameter: {field}" for field in missing]}

        if self.fake_mode:
            self._counters[kind] += 1
            return {
                "status": "created",
                "success": True,
                "mode": "fake",
                "object_type": object_type,
                "handle": f"FAKE-{kind.upper()}-{self._counters[kind]:04d}",
                "parameters": dict(parameters),
            }

        if not self.confirmed_capabilities.get(f"{object_type}.Insert"):
            return {"status": "failed", "success": False, "object_type": object_type, "errors": ["capability_not_confirmed"]}
        try:
            obj = getattr(self.com_environment, object_type)
            created = obj.Insert(parameters)
            return {
                "status": "created",
                "success": True,
                "mode": "real",
                "object_type": object_type,
                "handle": str(getattr(created, "Handle", "")) or None,
                "parameters": dict(parameters),
            }
        except Exception as exc:
            return {"status": "failed", "success": False, "object_type": object_type, "errors": [str(exc)]}

