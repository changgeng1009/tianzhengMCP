"""Command Registry Resolver - Phase C1 seed intake.

Resolve commands by id, primary_command, or alias.
Pure data resolver, no AutoCAD, no real execution.
"""

import json
from pathlib import Path
from typing import Any

_REGISTRY_DIR = Path(__file__).resolve().parent.parent
_WATER_REGISTRY = _REGISTRY_DIR / "water" / "plumbing_commands.seed.json"
_HVAC_REGISTRY = _REGISTRY_DIR / "hvac" / "hvac_commands.seed.json"
_SEED_REGISTRY = _REGISTRY_DIR / "tianzheng_commands.seed.json"

class CommandResolver:
    """Resolve Tianzheng commands from seed registry."""

    def __init__(self):
        self.commands: list[dict[str, Any]] = []
        self.by_id: dict[str, dict] = {}
        self.by_primary: dict[str, dict] = {}
        self.by_alias: dict[str, dict] = {}
        self._load()

    def _load(self):
        path = _SEED_REGISTRY if _SEED_REGISTRY.exists() else _WATER_REGISTRY
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.commands = data.get("commands", [])
        for c in self.commands:
            self.by_id[c["id"]] = c
            if c.get("primary_command"):
                self.by_primary[c["primary_command"].lower()] = c
            for a in c.get("aliases", []):
                if a:
                    self.by_alias.setdefault(a.lower(), c)

    def resolve(self, query: str) -> dict | None:
        """Resolve by id, primary_command, or alias (case-insensitive)."""
        q = query.strip().lower()
        if q in self.by_id:
            return self.by_id[q]
        if q in self.by_primary:
            return self.by_primary[q]
        if q in self.by_alias:
            return self.by_alias[q]
        return None

    def list_by_domain(self, domain: str) -> list[dict]:
        return [c for c in self.commands if c.get("domain") == domain]

    def list_by_danger_level(self, level: str) -> list[dict]:
        return [c for c in self.commands if c.get("safety", {}).get("danger_level") == level]

    def count_by_domain(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for c in self.commands:
            d = c.get("domain", "unknown")
            result[d] = result.get(d, 0) + 1
        return result

    def get_stats(self) -> dict[str, Any]:
        return {
            "total": len(self.commands),
            "by_domain": self.count_by_domain(),
            "dangerous": len(self.list_by_danger_level("dangerous")),
            "review": len(self.list_by_danger_level("review")),
            "sandbox_safe": len(self.list_by_danger_level("sandbox_safe")),
            "production_allowed": sum(1 for c in self.commands if c.get("safety", {}).get("allow_production")),
        }
