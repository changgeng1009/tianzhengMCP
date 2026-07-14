from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DomainAdapter(Protocol):
    domain_id: str
    status: str

    def capability_requirements(self, task: dict[str, Any]) -> list[str]: ...

    def enrich_task(self, task: dict[str, Any]) -> dict[str, Any]: ...

    def validate_task(self, task: dict[str, Any]) -> tuple[bool, list[str]]: ...
