from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from runtime.errors import ProductModeConflict
from runtime.product_profile import (
    ExecutionRuntime,
    ProductId,
    ProductProfileRegistry,
    ProductRuntimeRouter,
    ProductRuntimeUnavailable,
)


def test_s3_product_profile_registry_contains_only_declared_products():
    profiles = ProductProfileRegistry().list()
    assert {profile.product_id.value for profile in profiles} == {
        "generic_autocad",
        "tianzheng_water",
        "tianzheng_hvac",
        "offline_analysis",
    }
    assert ProductProfileRegistry().get(ProductId.TIANZHENG_HVAC).support_status == "INTERFACE_ONLY"


def test_s3_product_profile_schema_validates_registry_contracts():
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "autocad-tianzheng-automation"
        / "schemas"
        / "product_profile.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for profile in ProductProfileRegistry().list():
        jsonschema.validate(profile.to_dict(), schema)


@pytest.mark.parametrize(
    "product",
    [
        ProductId.GENERIC_AUTOCAD,
        ProductId.TIANZHENG_WATER,
        ProductId.TIANZHENG_HVAC,
        ProductId.OFFLINE_ANALYSIS,
    ],
)
def test_s3_product_and_runtime_are_independent(product):
    selected = ProductRuntimeRouter().select(product, ExecutionRuntime.OFFLINE)
    assert selected.product == product.value
    assert selected.execution_runtime == "offline"
    assert selected.execution_allowed is False


def test_s3_mock_is_not_real_cad_execution():
    selected = ProductRuntimeRouter().select("tianzheng_water", "mock")
    assert selected.runtime_status == "IMPLEMENTED_BASELINE"
    assert selected.execution_allowed is False
    assert "天正 Water Real backend 未实现" in selected.limitations


@pytest.mark.parametrize("runtime", ["com", "objectarx"])
def test_s3_real_runtimes_are_explicitly_not_available(runtime):
    with pytest.raises(ProductRuntimeUnavailable) as caught:
        ProductRuntimeRouter().select("tianzheng_water", runtime)
    assert caught.value.code == "PRODUCT_RUNTIME_NOT_AVAILABLE"
    assert caught.value.details["runtime_status"] == "NOT_AVAILABLE"
    assert caught.value.details["real_backend"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize("runtime", ["com", "objectarx"])
def test_s3_offline_analysis_real_runtime_rejection_has_same_evidence(runtime):
    with pytest.raises(ProductRuntimeUnavailable) as caught:
        ProductRuntimeRouter().select("offline_analysis", runtime)
    assert caught.value.details["runtime_status"] == "NOT_AVAILABLE"
    assert caught.value.details["real_backend"] == "NOT_IMPLEMENTED"


def test_s3_manifest_profile_and_execution_runtime_use_new_contract(canonical_manifest):
    canonical_manifest["runtime"].pop("runtime_mode")
    canonical_manifest["runtime"]["execution_runtime"] = "offline"
    canonical_manifest["product"].pop("requested_product")
    canonical_manifest["product"]["profile"] = "tianzheng_hvac"
    selected = ProductRuntimeRouter().select_from_manifest(canonical_manifest)
    assert selected.product == "tianzheng_hvac"
    assert selected.execution_runtime == "offline"


def test_s3_legacy_manifest_fields_remain_compatible(canonical_manifest):
    selected = ProductRuntimeRouter().select_from_manifest(canonical_manifest)
    assert selected.product == "generic_autocad"
    assert selected.execution_runtime == "offline"


def test_s3_profile_and_legacy_requested_product_conflict_fails_closed(canonical_manifest):
    canonical_manifest["product"]["profile"] = "tianzheng_water"
    with pytest.raises(ProductModeConflict):
        ProductRuntimeRouter().select_from_manifest(canonical_manifest)


def test_s3_profile_and_legacy_runtime_mode_conflict_fails_closed(canonical_manifest):
    canonical_manifest["product"]["profile"] = "tianzheng_water"
    canonical_manifest["product"].pop("requested_product")
    canonical_manifest["runtime"]["runtime_mode"] = "plain_autocad"
    with pytest.raises(ProductModeConflict):
        ProductRuntimeRouter().select_from_manifest(canonical_manifest)
