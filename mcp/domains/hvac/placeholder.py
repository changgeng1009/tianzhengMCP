from __future__ import annotations

from typing import Any


class HvacDomainPlaceholder:
    domain_id = "hvac"
    status = "deferred"
    enabled = False
    implementation_completed = False

    def capability_requirements(self, task: dict[str, Any]) -> list[str]:
        return []

    def enrich_task(self, task: dict[str, Any]) -> dict[str, Any]:
        result = dict(task)
        result.update({
            "professional_domain": "hvac",
            "execution_allowed": False,
            "classification": "blocked",
            "required_capabilities": [],
            "block_reason": "HVAC domain is deferred and disabled",
        })
        return result

    def validate_task(self, task: dict[str, Any]) -> tuple[bool, list[str]]:
        return False, ["HVAC domain is deferred and disabled"]
