from __future__ import annotations

import pytest

from adapters import (
    GenericAutoCadAdapter,
    OriginalRedrawSkillAdapter,
    ProductAdapter,
    ProductAdapterRegistry,
    TianzhengHvacAdapter,
    TianzhengWaterAdapter,
)
from adapters.registry import OfflineAnalysisAdapter


@pytest.mark.parametrize(
    "adapter_type,expected_product",
    [
        (GenericAutoCadAdapter, "generic_autocad"),
        (TianzhengWaterAdapter, "tianzheng_water"),
        (TianzhengHvacAdapter, "tianzheng_hvac"),
        (OriginalRedrawSkillAdapter, "generic_autocad"),
        (OfflineAnalysisAdapter, "offline_analysis"),
    ],
)
def test_s3_all_adapters_expose_unified_offline_contract(adapter_type, expected_product):
    adapter = adapter_type()
    assert isinstance(adapter, ProductAdapter)
    contract = adapter.contract()
    assert contract["product"] == expected_product
    assert contract["inspect_available"] is True
    assert contract["plan_available"] is True
    assert contract["validate_available"] is True
    assert contract["execute_available"] is False
    assert contract["real_cad_access"] is False
    assert contract["real_execution"] is False


@pytest.mark.parametrize(
    "adapter_type",
    [GenericAutoCadAdapter, TianzhengWaterAdapter, TianzhengHvacAdapter, OriginalRedrawSkillAdapter],
)
def test_s3_execute_never_runs_real_cad(adapter_type):
    result = adapter_type().execute({"backend": "offline"})
    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert result["code"] == "REAL_CAD_EXECUTION_BLOCKED"
    assert result["real_cad_access"] is False
    assert result["com_connection"] is False


def test_s3_mock_execute_is_only_a_contract():
    result = GenericAutoCadAdapter().execute({"backend": "nextgen_mock"})
    assert result["executed"] is False
    assert result["status"] == "MOCK_CONTRACT"
    assert result["code"] == "MOCK_EXECUTION_CONTRACT_ONLY"
    assert result["real_cad_access"] is False


def test_s3_real_backend_request_is_invalid_and_blocked():
    adapter = TianzhengWaterAdapter()
    validation = adapter.validate({"backend": "tianzheng_water_real"})
    result = adapter.execute({"backend": "tianzheng_water_real"})
    assert validation["valid"] is False
    assert validation["code"] == "BACKEND_NOT_AVAILABLE"
    assert result["status"] == "BLOCKED"
    assert result["executed"] is False


def test_s3_hvac_keeps_interface_only_write_status():
    contract = TianzhengHvacAdapter().contract()
    assert contract["write_supported"] is False
    assert contract["write_support_level"] == "INTERFACE_ONLY"
    assert contract["real_backend_status"] == "NOT_IMPLEMENTED"


def test_s3_registry_exposes_original_compatibility_contract_without_replacing_product_route():
    registry = ProductAdapterRegistry()
    contracts = registry.list_contracts()
    names = {item["adapter_id"] for item in contracts}
    assert "OriginalRedrawSkillAdapter" in names
    assert registry.get("plain_autocad").__class__.__name__ == "GenericAutoCadAdapter"
