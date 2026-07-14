from __future__ import annotations

from .base import DomainAdapter


class DomainRegistry:
    def __init__(self) -> None:
        self._domains: dict[str, DomainAdapter] = {}

    def register(self, adapter: DomainAdapter) -> None:
        if not isinstance(adapter, DomainAdapter):
            raise TypeError("adapter does not implement DomainAdapter")
        self._domains[adapter.domain_id] = adapter

    def get(self, domain_id: str) -> DomainAdapter:
        return self._domains[domain_id]

    def status(self) -> dict[str, str]:
        return {name: adapter.status for name, adapter in sorted(self._domains.items())}


def build_default_domain_registry() -> DomainRegistry:
    from .hvac.placeholder import HvacDomainPlaceholder
    from .water_supply_and_drainage.adapter import WaterSupplyAndDrainageDomain

    registry = DomainRegistry()
    registry.register(WaterSupplyAndDrainageDomain())
    registry.register(HvacDomainPlaceholder())
    return registry
