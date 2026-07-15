from __future__ import annotations

from dataclasses import replace

import pytest

from adapters.registry import BackendSelector, ProductCapabilityResolver
from runtime.errors import WorkflowNotAvailable
from runtime.routing import RuntimeRouter
from runtime.workflow_registry import WorkflowRegistry


@pytest.mark.parametrize(
    ("requirement", "workflow_id"),
    [
        (53, "generic_autocad_redraw_offline"),
        (54, "pdf_intermediate_dwg_plan"),
        (55, "image_dimension_parametric_redraw_plan"),
        (56, "tianzheng_water_scan_plan"),
        (57, "tianzheng_water_completion_plan"),
        (58, "tianzheng_hvac_scan_plan"),
        (59, "tianzheng_hvac_write_placeholder"),
        (60, "nextgen_mock_job_simulation"),
    ],
)
def test_req_053_to_060_required_workflows_are_registered(requirement, workflow_id):
    assert requirement in range(53, 61)
    definition = WorkflowRegistry().get(workflow_id)
    assert definition.workflow_id == workflow_id
    assert definition.stages
    if requirement in {57, 59}:
        assert definition.status == "NOT_EXECUTABLE_CURRENTLY"


def test_req_061_workflow_capability_conflict(canonical_manifest):
    runtime = RuntimeRouter().select(canonical_manifest)
    product = ProductCapabilityResolver().resolve(
        "plain_autocad", requested_product="generic_autocad"
    )
    product = replace(product, supported_capabilities=())
    backend = BackendSelector().select("offline")
    with pytest.raises(WorkflowNotAvailable):
        WorkflowRegistry().select(
            canonical_manifest,
            runtime=runtime,
            product=product,
            backend=backend,
        )


def test_workflow_registry_contains_all_eleven_contracts():
    expected = {
        "generic_autocad_redraw_offline",
        "generic_autocad_clone_plan",
        "pdf_intermediate_dwg_plan",
        "image_dimension_parametric_redraw_plan",
        "tianzheng_water_scan_plan",
        "tianzheng_water_completion_plan",
        "tianzheng_hvac_scan_plan",
        "tianzheng_hvac_write_placeholder",
        "offline_document_comparison",
        "offline_capability_audit",
        "nextgen_mock_job_simulation",
    }
    assert {item.workflow_id for item in WorkflowRegistry().list()} == expected
