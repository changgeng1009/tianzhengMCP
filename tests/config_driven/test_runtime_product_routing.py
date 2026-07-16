from __future__ import annotations

import pytest

from runtime.errors import ProductModeConflict, RuntimeModeConflict
from runtime.routing import RuntimeRouter


@pytest.mark.parametrize(
    ("requirement", "mode", "product"),
    [
        (35, "plain_autocad", "generic_autocad"),
        (36, "tianzheng_water", "tianzheng_water"),
        (37, "tianzheng_hvac", "tianzheng_hvac"),
        (38, "offline_analysis", "unknown"),
    ],
)
def test_req_035_to_038_explicit_runtime(canonical_manifest, requirement, mode, product):
    assert requirement in range(35, 39)
    canonical_manifest["runtime"]["runtime_mode"] = mode
    canonical_manifest["product"]["requested_product"] = product
    canonical_manifest["product"]["prohibited_products"] = []
    result = RuntimeRouter().select(canonical_manifest)
    assert result.mode.value == mode
    assert result.product == product
    assert result.trace


def test_req_039_auto_detect_uses_explicit_metadata(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "auto_detect"
    canonical_manifest["product"]["requested_product"] = "tianzheng_water"
    canonical_manifest["product"]["prohibited_products"] = []
    result = RuntimeRouter().select(canonical_manifest)
    assert result.mode.value == "tianzheng_water"
    assert result.source == "explicit_metadata_detection"


def test_req_040_runtime_product_conflict_fails_closed(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "plain_autocad"
    canonical_manifest["product"]["requested_product"] = "tianzheng_water"
    canonical_manifest["product"]["prohibited_products"] = []
    with pytest.raises(ProductModeConflict):
        RuntimeRouter().select(canonical_manifest)


def test_req_041_prohibited_product_fails_closed(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "tianzheng_hvac"
    canonical_manifest["product"]["requested_product"] = "tianzheng_hvac"
    canonical_manifest["product"]["prohibited_products"] = ["tianzheng_hvac"]
    with pytest.raises(ProductModeConflict):
        RuntimeRouter().select(canonical_manifest)


def test_req_042_ambiguous_auto_detect_fails_closed(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "auto_detect"
    canonical_manifest["runtime"]["offline_only"] = False
    canonical_manifest["product"]["requested_product"] = "unknown"
    canonical_manifest["product"]["prohibited_products"] = []
    with pytest.raises(RuntimeModeConflict):
        RuntimeRouter().select(canonical_manifest)


def test_s3_profile_conflict_is_checked_by_legacy_runtime_router(canonical_manifest):
    canonical_manifest["product"]["profile"] = "tianzheng_water"
    with pytest.raises(ProductModeConflict):
        RuntimeRouter().select(canonical_manifest)


def test_s3_profile_is_checked_against_runtime_mode_by_legacy_router(canonical_manifest):
    canonical_manifest["product"].pop("requested_product")
    canonical_manifest["product"]["profile"] = "tianzheng_water"
    canonical_manifest["runtime"]["runtime_mode"] = "plain_autocad"
    with pytest.raises(ProductModeConflict):
        RuntimeRouter().select(canonical_manifest)
