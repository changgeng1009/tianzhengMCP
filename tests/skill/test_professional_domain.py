from __future__ import annotations

from mcp.domains.hvac.placeholder import HvacDomainPlaceholder
from mcp.domains.registry import build_default_domain_registry
from mcp.domains.water_supply_and_drainage.adapter import WaterSupplyAndDrainageDomain


def test_default_domain_registry_marks_water_active_and_hvac_deferred() -> None:
    assert build_default_domain_registry().status() == {
        "hvac": "deferred",
        "water_supply_and_drainage": "active",
    }


def test_water_domain_can_be_registered_and_enriches_system_type() -> None:
    task = WaterSupplyAndDrainageDomain().enrich_task({"object_type": "TDbPipe", "semantic": {"system_type": "drainage"}})
    assert task["professional_domain"] == "water_supply_and_drainage"
    assert task["system_type"] == "drainage"
    assert task["required_capabilities"] == ["create_tdb_pipe", "persistence_qa"]


def test_hvac_placeholder_is_disabled_and_never_executable() -> None:
    adapter = HvacDomainPlaceholder()
    result = adapter.enrich_task({"task_id": "hvac_1", "execution_allowed": True})
    assert adapter.enabled is False
    assert adapter.implementation_completed is False
    assert result["execution_allowed"] is False
    assert result["classification"] == "blocked"
