from __future__ import annotations

from collections import defaultdict
from typing import Any

from mcp.probe import CAPABILITY_KEYS, probe_t30_capabilities


DEFAULT_MOCK_CAPABILITIES = {key: True for key in CAPABILITY_KEYS}


class T30WritebackAdapter:
    def __init__(
        self,
        real_com_mode: bool = False,
        capabilities: dict[str, Any] | None = None,
        com_objects: Any | None = None,
    ) -> None:
        self.real_com_mode = bool(real_com_mode)
        self.com_objects = com_objects
        self.capabilities = (
            probe_t30_capabilities(capabilities or com_objects)
            if self.real_com_mode
            else {**DEFAULT_MOCK_CAPABILITIES, "source": "mock", "notes": "mock adapter"}
        )
        self.action_log: list[dict[str, Any]] = []
        self._counters: dict[str, int] = defaultdict(int)

    def insert_pipe(
        self,
        action_id: str,
        start: list[float],
        end: list[float],
        dn: int,
        layer: str,
        system_type: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "start": list(start),
            "end": list(end),
            "dn": int(dn),
            "layer": layer,
            "system_type": system_type,
        }
        return self._insert(action_id, "pipe", "TDbPipe", "TDbPipe.Insert", payload)

    def insert_valve(
        self,
        action_id: str,
        position: list[float],
        on_pipe: str,
        valve_type: str,
        layer: str,
    ) -> dict[str, Any]:
        payload = {
            "position": list(position),
            "on_pipe": on_pipe,
            "valve_type": valve_type,
            "layer": layer,
        }
        return self._insert(action_id, "valve", "TDbValve", "TDbValve.Insert", payload)

    def insert_sprinkler(
        self,
        action_id: str,
        position: list[float],
        layer: str,
        sprinkler_type: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "position": list(position),
            "layer": layer,
            "sprinkler_type": sprinkler_type,
        }
        return self._insert(
            action_id,
            "sprinkler",
            "TDbSprinkler",
            "TDbSprinkler.Insert",
            payload,
        )

    def insert_fitting(
        self,
        action_id: str,
        position: list[float],
        fitting_type: str,
        layer: str,
    ) -> dict[str, Any]:
        payload = {
            "position": list(position),
            "fitting_type": fitting_type,
            "layer": layer,
        }
        return self._insert(
            action_id,
            "fitting",
            "TDbPipeFitting",
            "TDbPipeFitting.Insert",
            payload,
        )

    def _insert(
        self,
        action_id: str,
        kind: str,
        object_type: str,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.real_com_mode and not bool(self.capabilities.get(method, False)):
            result = {
                "success": False,
                "status": "capability_missing",
                "mode": "real",
                "action_id": action_id,
                "object_type": object_type,
                "method": method,
                "payload": payload,
            }
            self._record(action_id, method, "blocked", result)
            return result

        if not self.real_com_mode:
            self._counters[kind] += 1
            handle = f"MOCK-{kind.upper()}-{self._counters[kind]:04d}"
            result = {
                "success": True,
                "status": "inserted",
                "mode": "mock",
                "action_id": action_id,
                "object_type": object_type,
                "method": method,
                "handle": handle,
                "payload": payload,
            }
            self._record(action_id, method, "mock_inserted", result)
            return result

        result = self._insert_real(action_id, object_type, method, payload)
        self._record(action_id, method, "real_inserted" if result["success"] else "failed", result)
        return result

    def _insert_real(
        self,
        action_id: str,
        object_type: str,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.com_objects is None:
            return {
                "success": False,
                "status": "real_com_not_configured",
                "mode": "real",
                "action_id": action_id,
                "object_type": object_type,
                "method": method,
                "payload": payload,
                "error": "real_com_mode=True but no COM object source was provided.",
            }

        try:
            target = getattr(self.com_objects, object_type)
            inserted = target.Insert(payload)
            return {
                "success": True,
                "status": "inserted",
                "mode": "real",
                "action_id": action_id,
                "object_type": object_type,
                "method": method,
                "handle": str(getattr(inserted, "Handle", "")) or None,
                "payload": payload,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "real_insert_failed",
                "mode": "real",
                "action_id": action_id,
                "object_type": object_type,
                "method": method,
                "payload": payload,
                "error": str(exc),
            }

    def _record(
        self,
        action_id: str,
        method: str,
        status: str,
        result: dict[str, Any],
    ) -> None:
        self.action_log.append(
            {
                "action_id": action_id,
                "method": method,
                "status": status,
                "result": result,
            }
        )
