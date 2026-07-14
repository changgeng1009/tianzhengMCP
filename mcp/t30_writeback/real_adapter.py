from __future__ import annotations

from uuid import uuid4

from mcp.t30_writeback.action_translator import translate_repair_plan_to_t30_actions
from mcp.t30_writeback.com_probe import T30COMProbe
from mcp.t30_writeback.models import T30WritebackResult
from mcp.t30_writeback.object_factory import T30ObjectFactory
from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry, build_fake_schema_registry
from mcp.t30_writeback.sandbox import create_dwg_sandbox
from mcp.t30_writeback.transaction import T30WritebackTransactionEngine


class RealT30WritebackAdapter:
    def __init__(
        self,
        real_com_mode: bool = False,
        schema_registry: T30ParameterSchemaRegistry | None = None,
        capability_probe: T30COMProbe | None = None,
    ) -> None:
        self.real_com_mode = bool(real_com_mode)
        self.schema_registry = schema_registry or build_fake_schema_registry()
        self.capability_probe = capability_probe

    def apply_repair_plan_v2(
        self,
        repair_plan_v2: dict,
        original_dwg_path: str,
        options: dict | None = None,
    ) -> T30WritebackResult:
        options = dict(options or {})
        transaction_id = f"t30tx_{uuid4().hex}"
        if options.get("dry_run_only", True):
            return T30WritebackResult(
                transaction_id=transaction_id,
                status="dry_run",
                executed_actions=[],
                failed_actions=[],
                skipped_actions=list(repair_plan_v2.get("actions", [])),
                created_entities=[],
                verification={"valid": True, "dry_run_only": True},
                rollback_available=False,
                warnings=["dry_run_only"],
                metadata={"mode": "real" if self.real_com_mode else "fake"},
            )

        sandbox = create_dwg_sandbox(original_dwg_path, options.get("sandbox_dir"))
        if sandbox["status"] != "success":
            return T30WritebackResult(
                transaction_id=transaction_id,
                status="failed",
                executed_actions=[],
                failed_actions=[],
                skipped_actions=[],
                created_entities=[],
                verification={"valid": False},
                rollback_available=False,
                errors=list(sandbox.get("errors", [])),
                metadata={"sandbox": sandbox, "mode": "real" if self.real_com_mode else "fake"},
            )

        probe_result = self._probe_if_needed()
        capabilities = {
            f"{cap.object_type}.{cap.method_name}": cap.available and cap.probe_status == "confirmed"
            for cap in probe_result
        }
        actions = translate_repair_plan_to_t30_actions(repair_plan_v2, self.schema_registry, options)
        factory = T30ObjectFactory(
            fake_mode=not self.real_com_mode,
            com_environment=getattr(self.capability_probe, "com_environment", None) if self.capability_probe else None,
            confirmed_capabilities=capabilities,
        )
        engine = T30WritebackTransactionEngine(object_factory=factory)
        transaction = engine.plan_transaction(
            session_id=str(options.get("session_id") or "standalone"),
            original_dwg_path=original_dwg_path,
            sandbox_dwg_path=sandbox["sandbox_dwg_path"],
            backup_path=sandbox["backup_path"],
            actions=actions,
        )
        transaction.transaction_id = transaction_id
        transaction = engine.validate_transaction(transaction)
        if transaction.status == "failed":
            transaction = engine.rollback_transaction(transaction)
            return _result_from_transaction(transaction, "failed", sandbox, self.real_com_mode)
        transaction = engine.execute_transaction(transaction)
        if transaction.status == "failed":
            transaction = engine.rollback_transaction(transaction)
            return _result_from_transaction(transaction, "failed", sandbox, self.real_com_mode)
        transaction = engine.verify_transaction(transaction)
        if transaction.status == "failed":
            transaction = engine.rollback_transaction(transaction)
            return _result_from_transaction(transaction, "failed", sandbox, self.real_com_mode)
        transaction = engine.commit_transaction(transaction)
        return _result_from_transaction(transaction, transaction.status, sandbox, self.real_com_mode)

    def _probe_if_needed(self):
        if not self.real_com_mode:
            probe = T30COMProbe(com_environment=_FakeAllT30Environment(), fake_mode=True)
            return probe.probe_insert_methods()
        probe = self.capability_probe or T30COMProbe()
        probe.probe_environment()
        return probe.probe_insert_methods()


class _FakeT30Object:
    def Insert(self, parameters):  # noqa: N802
        return {"Handle": "FAKE"}


class _FakeAllT30Environment:
    ActiveDocument = object()
    TDbPipe = _FakeT30Object()
    TDbPipeValve = _FakeT30Object()
    TDbPipeFitting = _FakeT30Object()
    TDbSprinkler = _FakeT30Object()


def _result_from_transaction(transaction, status: str, sandbox: dict, real_com_mode: bool) -> T30WritebackResult:
    failed_actions = list(transaction.metadata.get("failed_actions", []))
    executed_actions = list(transaction.metadata.get("executed_actions", []))
    created_entities = list(transaction.metadata.get("created_entities", []))
    return T30WritebackResult(
        transaction_id=transaction.transaction_id,
        status=status,
        executed_actions=executed_actions,
        failed_actions=failed_actions,
        skipped_actions=[],
        created_entities=created_entities,
        verification=dict(transaction.metadata.get("verification", {"valid": status == "committed"})),
        rollback_available=bool(sandbox.get("backup_path")),
        warnings=list(transaction.warnings),
        errors=list(transaction.errors),
        metadata={
            "mode": "real" if real_com_mode else "fake",
            "sandbox": sandbox,
            "transaction": transaction.to_dict(),
        },
    )

