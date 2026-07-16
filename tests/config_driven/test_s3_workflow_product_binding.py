"""S3 工作流—ProductProfile 绑定的纯离线合同测试。"""

from __future__ import annotations

import json
from pathlib import Path

from adapters.registry import BackendSelector, ProductCapabilityResolver
from runtime.product_profile import ExecutionRuntime, ProductProfileRegistry, ProductRuntimeRouter
from runtime.routing import RuntimeRouter
from runtime.workflow_registry import WorkflowRegistry, canonical_product_id


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"
MATRIX_PATH = SKILL_ROOT / "capabilities" / "product_workflow_matrix.json"


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_s3_product_workflow_matrix_covers_every_registered_workflow():
    matrix = _matrix()
    bindings = matrix["workflow_bindings"]
    workflow_ids = {item.workflow_id for item in WorkflowRegistry().list()}
    bound_ids = {item["workflow_id"] for item in bindings}

    assert matrix["matrix_id"] == "s3_product_workflow_binding"
    assert bound_ids == workflow_ids
    assert len(bindings) == 11


def test_s3_workflow_bindings_match_explicit_product_profiles():
    matrix = _matrix()
    known_profiles = {profile.product_id.value for profile in ProductProfileRegistry().list()}
    registry = WorkflowRegistry()

    for binding in matrix["workflow_bindings"]:
        assert binding["product_id"] in known_profiles
        definition = registry.get(binding["workflow_id"])
        assert binding["product_id"] in {
            canonical_product_id(product) for product in definition.supported_products
        }
        assert binding["execution_runtime"] in {"offline", "mock"}


def test_s3_product_binding_preserves_legacy_offline_adapter_selection(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "offline_analysis"
    canonical_manifest["product"]["requested_product"] = "unknown"
    canonical_manifest["product"]["prohibited_products"] = []
    canonical_manifest["backend"]["preferred_backend"] = "offline"
    canonical_manifest["workflow"]["workflow_id"] = "offline_capability_audit"

    runtime = RuntimeRouter().select(canonical_manifest)
    product = ProductCapabilityResolver().resolve(
        runtime.mode, requested_product="unknown"
    )
    backend = BackendSelector().select("offline")
    selection = WorkflowRegistry().select(
        canonical_manifest, runtime=runtime, product=product, backend=backend
    )

    assert selection.selected is True
    assert selection.definition.workflow_id == "offline_capability_audit"
    assert canonical_product_id(product.product) == "offline_analysis"


def test_s3_trace_keeps_runtime_product_and_backend_as_independent_evidence(canonical_manifest):
    runtime = RuntimeRouter().select(canonical_manifest)
    product = ProductCapabilityResolver().resolve(
        runtime.mode, requested_product="generic_autocad"
    )
    backend = BackendSelector().select("offline")
    selection = WorkflowRegistry().select(
        canonical_manifest, runtime=runtime, product=product, backend=backend
    )

    trace = {(item.source, item.field) for item in selection.trace}
    assert ("runtime_router", "runtime.runtime_mode") in trace
    assert ("product_adapter_registry", "product.requested_product") in trace
    assert ("project_manifest", "workflow.workflow_id") in trace
    assert ("backend_registry", "backend.preferred_backend") in trace


def test_s3_nextgen_mock_binding_declares_offline_product_and_mock_runtime(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "offline_analysis"
    canonical_manifest["runtime"]["execution_runtime"] = "mock"
    canonical_manifest["product"]["requested_product"] = "offline_analysis"
    canonical_manifest["product"]["profile"] = "offline_analysis"
    canonical_manifest["product"]["prohibited_products"] = []
    canonical_manifest["backend"]["preferred_backend"] = "nextgen_mock"
    canonical_manifest["backend"]["mock_allowed"] = True
    canonical_manifest["workflow"]["workflow_id"] = "nextgen_mock_job_simulation"

    product_runtime = ProductRuntimeRouter().select_from_manifest(canonical_manifest)
    runtime = RuntimeRouter().select(canonical_manifest)
    product = ProductCapabilityResolver().resolve(
        runtime.mode, requested_product="offline_analysis"
    )
    backend = BackendSelector().select("nextgen_mock")
    selection = WorkflowRegistry().select(
        canonical_manifest, runtime=runtime, product=product, backend=backend
    )

    assert product_runtime.product == "offline_analysis"
    assert product_runtime.execution_runtime == ExecutionRuntime.MOCK.value
    assert product_runtime.execution_allowed is False
    assert backend.backend == "nextgen_mock"
    assert backend.real_execution_supported is False
    assert selection.executable_currently is True
