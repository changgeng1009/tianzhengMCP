from __future__ import annotations


def _ready_action():
    from mcp.t30_writeback.models import T30WritebackAction

    return T30WritebackAction(
        action_id="t30_pipe_1",
        source_repair_action_id="repair_pipe_1",
        object_type="TDbPipe",
        method_name="Insert",
        parameters={"geometry": {"start": [0, 0, 0], "end": [100, 0, 0]}, "system": "给水", "dn": "DN50", "layer": "PIPE"},
        geometry={"start": [0, 0, 0], "end": [100, 0, 0]},
        system="给水",
        dn="DN50",
        layer="PIPE",
        confidence=0.91,
        capability_status="confirmed",
        ready_to_execute=True,
    )


def test_transaction_validate_execute_verify_commit_flow(tmp_path, synthetic_cad_factory) -> None:
    from mcp.t30_writeback.object_factory import T30ObjectFactory
    from mcp.t30_writeback.transaction import T30WritebackTransactionEngine

    sandbox = tmp_path / "sandbox.dwg"
    backup = tmp_path / "backup.dwg"
    synthetic_cad_factory(sandbox)
    synthetic_cad_factory(backup)
    engine = T30WritebackTransactionEngine(object_factory=T30ObjectFactory(fake_mode=True))

    transaction = engine.plan_transaction(
        session_id="sess1",
        original_dwg_path=str(tmp_path / "original.dwg"),
        sandbox_dwg_path=str(sandbox),
        backup_path=str(backup),
        actions=[_ready_action()],
    )
    transaction = engine.validate_transaction(transaction)
    transaction = engine.execute_transaction(transaction)
    transaction = engine.verify_transaction(transaction)
    transaction = engine.commit_transaction(transaction)

    assert transaction.status == "committed"
    assert transaction.metadata["created_entities"][0]["handle"].startswith("FAKE-")
    assert [entry["stage"] for entry in transaction.transaction_log] == ["planned", "validated", "executed", "verified", "committed"]


def test_transaction_rollback_restores_backup(tmp_path, synthetic_cad_factory) -> None:
    from mcp.t30_writeback.object_factory import T30ObjectFactory
    from mcp.t30_writeback.transaction import T30WritebackTransactionEngine

    sandbox = tmp_path / "sandbox.dwg"
    backup = tmp_path / "backup.dwg"
    synthetic_cad_factory(sandbox)
    synthetic_cad_factory(backup)
    expected_backup = backup.read_bytes()
    engine = T30WritebackTransactionEngine(object_factory=T30ObjectFactory(fake_mode=True))
    transaction = engine.plan_transaction("sess1", "original.dwg", str(sandbox), str(backup), [_ready_action()])

    rolled_back = engine.rollback_transaction(transaction)

    assert rolled_back.status == "rolled_back"
    assert sandbox.read_bytes() == expected_backup
