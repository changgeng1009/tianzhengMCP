"""S7.3/S7.5 backend, mapping, router and MCP-route tests. No AutoCAD is started."""
from __future__ import annotations

import pytest

from mcp_nextgen.backends.autocad_plugin import (
    UNSUPPORTED_OPERATION_ERROR,
    AutoCadPluginBackend,
    PluginBackendError,
    _map_batch_results,
    classify_plugin_error,
    map_plan,
    plan_supported,
)
from mcp_nextgen.backends.capability_router import (
    COM_BACKEND,
    MOCK_BACKEND,
    PLUGIN_BACKEND,
    BackendOffer,
    CapabilityRouter,
    RoutingRequest,
    com_offer,
    mock_offer,
)
from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, EntitySpec, LayerSpec
from mcp_nextgen.s7.plugin_route import build_plan_from_structured_request, build_plugin_route_service

LAYER = "CADAGENT_S6_MVP"


def line_op(oid="op-line"):
    return CadOperation(oid, "CREATE_LINE", entity=EntitySpec(
        "line", {"start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}}, layer=LAYER))


def circle_op(oid="op-circle", radius=5.0):
    return CadOperation(oid, "CREATE_CIRCLE", entity=EntitySpec(
        "circle", {"center": {"x": 10, "y": 10}, "radius": radius}, layer=LAYER))


def polyline_op(oid="op-poly"):
    return CadOperation(oid, "CREATE_POLYLINE", entity=EntitySpec(
        "polyline", {"vertices": [{"x": 0, "y": 0}, {"x": 5, "y": 5}]}, layer=LAYER))


def text_op(oid="op-text"):
    return CadOperation(oid, "CREATE_TEXT", entity=EntitySpec(
        "text", {"text": "hello", "insertion_point": {"x": 0, "y": 0}, "height": 10}, layer=LAYER))


def layer_op(oid="op-layer"):
    return CadOperation(oid, "ENSURE_LAYER", parameters={"layer": LayerSpec(name=LAYER).to_dict()})


def plan(*operations, job_id="job-1", dry_run=False):
    return CadOperationPlan(
        job_id=job_id, document_token="tok-1", operations=tuple(operations),
        batch_policy="all_or_nothing", dry_run=dry_run)


# ------------------------------------------------------------------ mapping


def test_supported_operations_map_to_plugin_operations():
    mapping = map_plan(plan(layer_op(), line_op(), circle_op(), polyline_op()))
    assert [op["operation_type"] for op in mapping.operations] == [
        "create_layer", "create_line", "create_circle", "create_polyline"]


def test_line_geometry_maps_to_plugin_points():
    op = map_plan(plan(line_op())).operations[0]
    assert op["parameters"]["start"] == [0.0, 0.0, 0.0]
    assert op["parameters"]["end"] == [100.0, 0.0, 0.0]
    assert op["parameters"]["layer"] == LAYER


def test_circle_and_polyline_geometry_map():
    circle = map_plan(plan(circle_op(radius=7.5))).operations[0]
    assert circle["parameters"]["radius"] == 7.5
    poly = map_plan(plan(polyline_op())).operations[0]
    assert poly["parameters"]["vertices"] == [[0.0, 0.0, 0.0], [5.0, 5.0, 0.0]]
    assert poly["parameters"]["closed"] is False


def test_query_operations_are_separated_from_the_write_batch():
    mapping = map_plan(plan(line_op(), CadOperation("op-q", "QUERY_ENTITIES")))
    assert len(mapping.operations) == 1
    assert len(mapping.query_operations) == 1


def test_a_mixed_plan_with_an_unsupported_operation_is_rejected_entirely():
    """No partial execution: an unsupported op rejects the whole plan before sending."""
    with pytest.raises(PluginBackendError) as exc:
        map_plan(plan(line_op(), circle_op(), text_op()))
    assert exc.value.error_code == UNSUPPORTED_OPERATION_ERROR
    assert exc.value.retryable is False


def test_plan_supported_probe_is_non_throwing():
    assert plan_supported(plan(line_op()))[0] is True
    supported, blocker = plan_supported(plan(line_op(), text_op()))
    assert supported is False and blocker


@pytest.mark.parametrize("operation,extra", [
    ("MOVE_ENTITY", {"displacement": {"x": 1, "y": 1, "z": 0}}),
    ("COPY_ENTITY", {"displacement": {"x": 1, "y": 1, "z": 0}}),
    ("ROTATE_ENTITY", {"base_point": {"x": 0, "y": 0, "z": 0}, "angle": 1.0}),
    ("SCALE_ENTITY", {"base_point": {"x": 0, "y": 0, "z": 0}, "scale": 2.0}),
    ("DELETE_ENTITY", {}),
])
def test_unimplemented_transform_operations_are_unsupported(operation, extra):
    from mcp_nextgen.s6.contracts import EntitySelector

    operation_value = CadOperation(
        "op-x", operation, selector=EntitySelector(layer=LAYER), parameters=extra)
    assert plan_supported(plan(operation_value))[0] is False


@pytest.mark.parametrize("operation,params", [
    ("ENSURE_TEXT_STYLE", {"text_style": {"name": "STYLE_A"}}),
    ("ENSURE_DIMENSION_STYLE", {"dimension_style": {"name": "DIM_A"}}),
])
def test_unimplemented_style_operations_are_unsupported(operation, params):
    assert plan_supported(plan(CadOperation("op-x", operation, parameters=params)))[0] is False


@pytest.mark.parametrize("entity_type,geometry", [
    ("arc", {"center": {"x": 0, "y": 0}, "radius": 5, "start_angle": 0.0, "end_angle": 1.5}),
    ("rectangle", {"corner_a": {"x": 0, "y": 0}, "corner_b": {"x": 10, "y": 10}}),
    ("mtext", {"content": "x", "insertion_point": {"x": 0, "y": 0}, "height": 10, "width": 100}),
])
def test_unimplemented_entity_types_are_unsupported(entity_type, geometry):
    operation = CadOperation(
        "op-x", f"CREATE_{entity_type.upper()}",
        entity=EntitySpec(entity_type, geometry, layer=LAYER))
    assert plan_supported(plan(operation))[0] is False


# ------------------------------------------------------------------ result semantics


def test_rolled_back_operations_never_map_to_success():
    """A discarded effect must not look committed to any upper layer."""
    batch = {"operation_results": [
        {"operation_id": "a", "success": False, "entity_status": "ROLLED_BACK", "entities": []},
        {"operation_id": "b", "success": False, "entity_status": "FAILED",
         "error_code": "INVALID_GEOMETRY", "entities": []},
    ]}
    results = _map_batch_results(batch)

    assert all(item.status == "FAILED" for item in results)
    assert results[0].error_code == "BATCH_ROLLED_BACK"
    assert results[0].entities == ()
    assert results[1].error_code == "INVALID_GEOMETRY"


def test_committed_operations_map_to_success_with_handles():
    batch = {"operation_results": [
        {"operation_id": "a", "success": True, "entity_status": "CREATED",
         "entities": [{"handle": "80", "entity_type": "line", "layer": LAYER, "geometry": {}}]},
    ]}
    results = _map_batch_results(batch)
    assert results[0].status == "CREATED"
    assert results[0].entities[0].handle == "80"


# ------------------------------------------------------------------ error taxonomy


@pytest.mark.parametrize("code,expected_category", [
    ("AUTH_FAILED", "authentication"),
    ("INCOMPATIBLE_PROTOCOL_VERSION", "protocol"),
    ("DOCUMENT_NOT_JOB_OWNED", "ownership"),
    ("BATCH_ROLLED_BACK", "execution"),
    ("INVALID_GEOMETRY", "validation"),
    ("IDEMPOTENCY_CONFLICT", "idempotency"),
    ("CONNECTION_REFUSED", "transport"),
    ("UNKNOWN_OPERATION", "unsupported"),
])
def test_errors_are_categorised_not_collapsed(code, expected_category):
    retryable, category = classify_plugin_error(code)
    assert category == expected_category
    assert isinstance(retryable, bool)


def test_unknown_error_codes_are_conservatively_non_retryable():
    retryable, category = classify_plugin_error("SOMETHING_NEW")
    assert retryable is False and category == "unknown"


@pytest.mark.parametrize("code", ["CONNECTION_REFUSED", "TIMEOUT", "CONNECTION_RESET", "DOCUMENT_LOCK_FAILED"])
def test_transport_level_errors_are_retryable(code):
    assert classify_plugin_error(code)[0] is True


@pytest.mark.parametrize("code", [
    "AUTH_FAILED", "UNKNOWN_OPERATION", "DOCUMENT_NOT_JOB_OWNED",
    "IDEMPOTENCY_CONFLICT", "INVALID_GEOMETRY", "PLUGIN_EXECUTION_OUTCOME_UNKNOWN",
])
def test_dangerous_errors_are_never_auto_retryable(code):
    assert classify_plugin_error(code)[0] is False


# ------------------------------------------------------------------ router


def plugin_available_offer(plan_value, *, supports=True, atomic=True, available=True):
    return BackendOffer(PLUGIN_BACKEND, available=available, supports_plan=supports,
                        atomic_batch=atomic, sandbox_only=True,
                        unsupported_reason=None if supports else "unsupported by plugin")


def router(plugin=None, *, com_available=False, mock_available=True):
    providers = {
        MOCK_BACKEND: lambda p: mock_offer(p, available=mock_available),
        COM_BACKEND: lambda p: com_offer(p, available=com_available),
    }
    if plugin is not None:
        providers[PLUGIN_BACKEND] = plugin
    return CapabilityRouter(providers)


def test_case_a_plugin_is_selected_for_supported_entities():
    decision = router(lambda p: plugin_available_offer(p)).route(
        RoutingRequest(plan=plan(line_op(), circle_op(), polyline_op()), require_atomic_batch=True))

    assert decision.status == "selected"
    assert decision.selected_backend == PLUGIN_BACKEND
    assert decision.actual_backend_used == PLUGIN_BACKEND


def test_case_b_plugin_is_not_selected_for_text():
    decision = router(lambda p: plugin_available_offer(p, supports=False)).route(
        RoutingRequest(plan=plan(line_op(), text_op()), require_atomic_batch=True))

    assert decision.selected_backend != PLUGIN_BACKEND


def test_case_c_unavailable_plugin_never_appears_to_have_run():
    decision = router(lambda p: plugin_available_offer(p, available=False)).route(
        RoutingRequest(plan=plan(line_op()), require_atomic_batch=True))

    assert decision.selected_backend != PLUGIN_BACKEND
    assert decision.actual_backend_used != PLUGIN_BACKEND
    offers = {o.backend_id: o for o in decision.candidates}
    assert offers[PLUGIN_BACKEND].available is False


def test_case_d_com_is_preserved_and_reported_when_chosen():
    decision = router(None, com_available=True).route(RoutingRequest(
        plan=plan(line_op()), require_atomic_batch=False,
        approval_granted=True, preferred_backend=COM_BACKEND))

    assert decision.selected_backend == COM_BACKEND
    assert decision.actual_backend_used == COM_BACKEND


def test_com_is_rejected_when_atomicity_is_required():
    """COM has no database transaction; that difference is enforced, not hidden."""
    decision = router(None, com_available=True, mock_available=False).route(
        RoutingRequest(plan=plan(line_op()), require_atomic_batch=True, approval_granted=True))

    assert decision.status == "blocked"
    assert "atomic" in decision.reason


def test_com_requires_explicit_approval():
    decision = router(None, com_available=True, mock_available=False).route(
        RoutingRequest(plan=plan(line_op()), require_atomic_batch=False, approval_granted=False))
    assert decision.status == "blocked"


def test_mock_and_com_remain_registered_alongside_the_plugin():
    assert router(lambda p: plugin_available_offer(p)).registered_backends == (
        MOCK_BACKEND, COM_BACKEND, PLUGIN_BACKEND)


def test_preferred_backend_is_never_silently_replaced():
    decision = router(lambda p: plugin_available_offer(p, supports=False)).route(
        RoutingRequest(plan=plan(line_op()), preferred_backend=PLUGIN_BACKEND, allow_fallback=False))

    assert decision.status == "blocked"
    assert decision.actual_backend_used is None


def test_probe_failure_marks_the_backend_unavailable_rather_than_crashing():
    def exploding(_plan):
        raise RuntimeError("probe blew up")

    decision = router(exploding).route(RoutingRequest(plan=plan(line_op())))
    offers = {o.backend_id: o for o in decision.candidates}
    assert offers[PLUGIN_BACKEND].available is False


# ------------------------------------------------------------------ MCP route


def test_structured_request_builds_a_valid_s6_plan():
    built = build_plan_from_structured_request({
        "job_id": "j1", "layer": LAYER,
        "entities": [
            {"type": "line", "geometry": {"start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}}},
            {"type": "circle", "geometry": {"center": {"x": 5, "y": 5}, "radius": 2}},
        ],
    })
    assert isinstance(built, CadOperationPlan)
    assert [op.operation for op in built.operations] == ["ENSURE_LAYER", "CREATE_LINE", "CREATE_CIRCLE"]
    assert built.batch_policy == "all_or_nothing"


def test_structured_request_rejects_missing_fields():
    from mcp_nextgen.s7.plugin_route import PluginRouteError

    for payload in ({"layer": LAYER, "entities": [{}]}, {"job_id": "j", "entities": [{}]},
                    {"job_id": "j", "layer": LAYER, "entities": []}):
        with pytest.raises(PluginRouteError):
            build_plan_from_structured_request(payload)


def test_mcp_route_exposes_no_raw_protocol_surface():
    """There must be no way to send a raw plugin request from the MCP layer."""
    import mcp_nextgen.s7.plugin_route as route

    forbidden = ("plugin_send", "raw_socket", "send_autocad_command",
                 "plugin_request", "arbitrary_operation", "send_command")
    exported = dir(route)
    for name in forbidden:
        assert not any(name in item.lower() for item in exported), f"{name} must not be exposed"


def test_blocked_routing_executes_nothing():
    service = build_plugin_route_service(plugin_backend=None, mock_available=False, com_available=False)
    result = service.execute(plan(line_op()), session_id="s1")

    assert result.status == "blocked"
    assert result.actual_backend_used is None
    assert result.execution == {}


def test_route_reports_delegation_rather_than_faking_plugin_execution():
    service = build_plugin_route_service(plugin_backend=None, mock_available=True)
    result = service.execute(plan(line_op()), session_id="s1", require_atomic_batch=True)

    assert result.status == "delegated"
    assert result.actual_backend_used == MOCK_BACKEND
    assert result.actual_backend_used != PLUGIN_BACKEND
