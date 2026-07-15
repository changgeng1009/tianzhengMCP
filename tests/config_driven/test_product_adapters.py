from __future__ import annotations

import pytest

from adapters.registry import (
    ProductAdapterRegistry,
    ProductCapabilityResolver,
    ProductModeConflict,
)


@pytest.mark.parametrize(
    ("requirement", "mode", "product", "adapter"),
    [
        (35, "plain_autocad", "generic_autocad", "GenericAutoCadAdapter"),
        (36, "tianzheng_water", "tianzheng_water", "TianzhengWaterAdapter"),
        (37, "tianzheng_hvac", "tianzheng_hvac", "TianzhengHvacAdapter"),
        (38, "offline_analysis", "unknown", "OfflineAnalysisAdapter"),
    ],
)
def test_req_035_to_038_product_adapter_selection(requirement, mode, product, adapter):
    assert requirement in range(35, 39)
    result = ProductCapabilityResolver().resolve(mode, requested_product=product)
    assert result.adapter == adapter
    assert result.real_backend_status == "NOT_IMPLEMENTED"


def test_req_040_runtime_product_conflict():
    with pytest.raises(ProductModeConflict):
        ProductAdapterRegistry().get("plain_autocad", "tianzheng_water")


def test_hvac_and_water_contracts_are_not_interchangeable():
    water = ProductCapabilityResolver().resolve("tianzheng_water")
    hvac = ProductCapabilityResolver().resolve("tianzheng_hvac")
    assert water.adapter != hvac.adapter
    assert water.supported_capabilities != hvac.supported_capabilities
