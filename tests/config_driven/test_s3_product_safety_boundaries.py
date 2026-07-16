"""S3 产品统一层的 fail-closed 安全合同回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters import OriginalRedrawSkillAdapter, TianzhengHvacAdapter, TianzhengWaterAdapter
from runtime.product_profile import ProductProfileRegistry, ProductRuntimeRouter, ProductRuntimeUnavailable


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"


def test_s3_product_profiles_publish_only_four_canonical_ids():
    profiles = ProductProfileRegistry().list()
    assert {profile.product_id.value for profile in profiles} == {
        "generic_autocad",
        "tianzheng_water",
        "tianzheng_hvac",
        "offline_analysis",
    }
    assert all(profile.currently_available_runtimes for profile in profiles)


@pytest.mark.parametrize("product", [profile.product_id.value for profile in ProductProfileRegistry().list()])
@pytest.mark.parametrize("runtime", ["com", "objectarx"])
def test_s3_real_runtime_is_fail_closed_for_every_product(product, runtime):
    with pytest.raises(ProductRuntimeUnavailable) as caught:
        ProductRuntimeRouter().select(product, runtime)
    assert caught.value.code == "PRODUCT_RUNTIME_NOT_AVAILABLE"
    assert caught.value.details["real_backend"] == "NOT_IMPLEMENTED"


def test_s3_original_skill_adapter_emits_canonical_product_but_only_maps_workflow():
    adapter = OriginalRedrawSkillAdapter()
    patch = adapter.to_manifest_patch("redraw_from_reference")
    assert patch["product"] == "generic_autocad"
    assert patch["preferred_backend"] == "offline"
    assert patch["production_allowed"] is False
    result = adapter.execute({"backend": "offline"})
    assert result["executed"] is False
    assert result["real_cad_access"] is False


def test_s3_tianzheng_adapters_cannot_promote_real_read_or_write():
    water = TianzhengWaterAdapter().contract()
    hvac = TianzhengHvacAdapter().contract()
    for contract in (water, hvac):
        assert contract["write_supported"] is False
        assert contract["real_backend_status"] == "NOT_IMPLEMENTED"
        assert contract["real_cad_access"] is False
        assert contract["real_execution"] is False
    assert hvac["write_support_level"] == "INTERFACE_ONLY"


def test_s3_product_workflow_matrix_keeps_all_real_and_production_permissions_false():
    matrix_path = SKILL_ROOT / "capabilities" / "product_workflow_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    safety = matrix["safety_boundary"]
    assert safety == {
        "production_allowed": False,
        "production_d1_allowed": False,
        "real_cad_access": False,
        "real_backend": False,
    }
    assert all(
        profile["real_backend_status"] == "NOT_IMPLEMENTED"
        for profile in matrix["product_profiles"]
    )
