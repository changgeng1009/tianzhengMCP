from __future__ import annotations

import pytest

from config import ConfigMerger, DefaultRegistry, DefaultResolver
from runtime.errors import (
    ConfigApprovalInheritanceForbidden,
    ConfigBackendOverrideForbidden,
    ConfigSecurityDowngradeBlocked,
)


def test_req_011_system_default_is_safe():
    value = DefaultRegistry().system_defaults()
    assert value["safety"]["production_allowed"] is False


def test_req_012_product_default_is_selected():
    value = DefaultRegistry().product_defaults("tianzheng_water")
    assert value["runtime"]["runtime_mode"] == "tianzheng_water"


def test_req_013_workflow_default_precedence():
    result = DefaultResolver().resolve({}, workflow_defaults={"workflow": {"stage_policy": "manifest_declared"}})
    assert result.value["workflow"]["stage_policy"] == "manifest_declared"


def test_req_014_project_override_precedence():
    result = DefaultResolver().resolve({"metadata": {"source": "project"}})
    assert result.value["metadata"]["source"] == "project"


def test_req_015_run_override_precedence():
    result = DefaultResolver().resolve(
        {"metadata": {"source": "project"}},
        run_override={"metadata": {"source": "run"}},
    )
    assert result.value["metadata"]["source"] == "run"


def test_req_016_field_source_trace():
    result = DefaultResolver().resolve({"metadata": {"source": "project"}})
    trace = {item.field: item.source for item in result.source_trace}
    assert trace["metadata.source"] == "project_manifest"


def test_req_017_permission_false_cannot_become_true():
    with pytest.raises(ConfigSecurityDowngradeBlocked):
        ConfigMerger().merge_layers([
            ("system_default", {"safety": {"production_allowed": False}}),
            ("project_manifest", {"safety": {"production_allowed": True}}),
        ])


def test_req_018_source_write_forbidden_cannot_be_disabled():
    with pytest.raises(ConfigSecurityDowngradeBlocked):
        ConfigMerger().merge_layers([
            ("system_default", {"safety": {"source_write_forbidden": True}}),
            ("project_manifest", {"safety": {"source_write_forbidden": False}}),
        ])


def test_req_019_visual_review_cannot_be_disabled():
    with pytest.raises(ConfigSecurityDowngradeBlocked):
        ConfigMerger().merge_layers([
            ("system_default", {"verification": {"visual_review_required": True}}),
            ("run_override", {"verification": {"visual_review_required": False}}),
        ])


def test_req_020_denylist_is_union():
    value, _ = ConfigMerger().merge_layers([
        ("system_default", {"safety": {"operation_denylist": ["erase"]}}),
        ("project_manifest", {"safety": {"operation_denylist": ["purge"]}}),
    ])
    assert value["safety"]["operation_denylist"] == ["erase", "purge"]


def test_req_021_allowlist_is_intersection():
    value, trace = ConfigMerger().merge_layers([
        ("system_default", {"safety": {"operation_allowlist": ["inspect", "report"]}}),
        ("project_manifest", {"safety": {"operation_allowlist": ["inspect", "write"]}}),
    ])
    # 空 trust root 是系统的 fail-closed 起点；后续配置只能做交集，不能自行扩权。
    assert value["safety"]["operation_allowlist"] == []
    assert all(item.policy == "allowlist_intersection" for item in trace)


def test_req_022_protected_regions_are_union():
    a = {"region_id": "a"}
    b = {"region_id": "b"}
    value, _ = ConfigMerger().merge_layers([
        ("system_default", {"safety": {"protected_regions": [a]}}),
        ("project_manifest", {"safety": {"protected_regions": [b]}}),
    ])
    assert value["safety"]["protected_regions"] == [a, b]


def test_req_023_backend_capability_cannot_be_promoted():
    with pytest.raises(ConfigBackendOverrideForbidden):
        ConfigMerger().merge_layers([
            ("project_manifest", {"backend": {"available": True}}),
        ])


def test_req_024_approval_is_not_inherited():
    with pytest.raises(ConfigApprovalInheritanceForbidden):
        ConfigMerger().merge_layers([
            ("workflow_default", {"approval": {"approval_reference": "stale"}}),
        ])
