from __future__ import annotations


def test_t30_models_are_json_serializable() -> None:
    from mcp.t30_writeback.models import (
        T30Capability,
        T30ParameterSchema,
        T30Transaction,
        T30WritebackAction,
        T30WritebackResult,
    )

    capability = T30Capability(
        capability_id="cap_pipe_insert",
        object_type="TDbPipe",
        method_name="Insert",
        available=True,
        confidence=1.0,
        signature={"parameters": ["start", "end", "dn"]},
        probe_status="confirmed",
    )
    schema = T30ParameterSchema(
        object_type="TDbPipe",
        method_name="Insert",
        parameters={"start": "point3d", "end": "point3d", "dn": "int"},
        required_fields=["start", "end", "dn", "system", "layer"],
        optional_fields=[],
        defaults={"layer": "0"},
        confidence=1.0,
        source="fake_com",
    )
    action = T30WritebackAction(
        action_id="t30_a1",
        source_repair_action_id="repair_a1",
        object_type="TDbPipe",
        method_name="Insert",
        parameters={"start": [0, 0, 0], "end": [100, 0, 0], "dn": "DN50", "system": "给水", "layer": "PIPE"},
        geometry={"start": [0, 0, 0], "end": [100, 0, 0]},
        system="给水",
        dn="DN50",
        layer="PIPE",
        confidence=0.92,
        capability_status="confirmed",
        ready_to_execute=True,
    )
    transaction = T30Transaction(
        transaction_id="tx1",
        session_id="sess1",
        sandbox_dwg_path="sandbox.dwg",
        original_dwg_path="original.dwg",
        backup_path="backup.dwg",
        actions=[action],
        status="planned",
    )
    result = T30WritebackResult(
        transaction_id="tx1",
        status="committed",
        executed_actions=[action.to_dict()],
        failed_actions=[],
        skipped_actions=[],
        created_entities=[{"handle": "FAKE-1"}],
        verification={"valid": True},
        rollback_available=True,
    )

    assert capability.to_dict()["probe_status"] == "confirmed"
    assert schema.to_dict()["source"] == "fake_com"
    assert transaction.to_dict()["actions"][0]["ready_to_execute"] is True
    assert result.to_dict()["created_entities"][0]["handle"] == "FAKE-1"

