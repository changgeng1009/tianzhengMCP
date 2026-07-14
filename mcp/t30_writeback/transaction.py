from __future__ import annotations

from pathlib import Path
from shutil import copy2
from uuid import uuid4

from mcp.t30_writeback.models import T30Transaction, T30WritebackAction
from mcp.t30_writeback.object_factory import T30ObjectFactory
from mcp.t30_writeback.verifier import verify_created_entities


class T30WritebackTransactionEngine:
    def __init__(self, object_factory: T30ObjectFactory | None = None) -> None:
        self.object_factory = object_factory or T30ObjectFactory(fake_mode=True)

    def plan_transaction(
        self,
        session_id: str,
        original_dwg_path: str,
        sandbox_dwg_path: str,
        backup_path: str,
        actions: list[T30WritebackAction],
    ) -> T30Transaction:
        tx = T30Transaction(
            transaction_id=f"t30tx_{uuid4().hex}",
            session_id=session_id,
            sandbox_dwg_path=sandbox_dwg_path,
            original_dwg_path=original_dwg_path,
            backup_path=backup_path,
            actions=list(actions),
            status="planned",
        )
        tx.transaction_log.append({"stage": "planned", "status": "success", "action_count": len(actions)})
        return tx

    def validate_transaction(self, transaction: T30Transaction) -> T30Transaction:
        if transaction.status != "planned":
            return self._fail(transaction, "validate_requires_planned")
        for action in transaction.actions:
            if not action.ready_to_execute:
                transaction.errors.append(f"action_not_ready:{action.action_id}")
        if transaction.errors:
            transaction.status = "failed"
            transaction.transaction_log.append({"stage": "validated", "status": "failed", "errors": list(transaction.errors)})
            return transaction
        transaction.status = "validated"
        transaction.transaction_log.append({"stage": "validated", "status": "success"})
        return transaction

    def execute_transaction(self, transaction: T30Transaction) -> T30Transaction:
        if transaction.status != "validated":
            return self._fail(transaction, "execute_requires_validated")
        executed: list[dict] = []
        failed: list[dict] = []
        created: list[dict] = []
        for action in transaction.actions:
            result = self.object_factory.create_by_object_type(action.object_type, action.parameters)
            record = {"action": action.to_dict(), "result": result}
            executed.append(record)
            if result.get("success"):
                created.append(result)
            else:
                failed.append(record)
        transaction.metadata["executed_actions"] = executed
        transaction.metadata["failed_actions"] = failed
        transaction.metadata["created_entities"] = created
        transaction.status = "executed" if not failed else "failed"
        transaction.transaction_log.append({"stage": "executed", "status": transaction.status, "created_count": len(created)})
        return transaction

    def verify_transaction(self, transaction: T30Transaction) -> T30Transaction:
        if transaction.status != "executed":
            return self._fail(transaction, "verify_requires_executed")
        verification = verify_created_entities(transaction)
        transaction.metadata["verification"] = verification
        if verification["valid"]:
            transaction.status = "verified"
            transaction.transaction_log.append({"stage": "verified", "status": "success"})
        else:
            transaction.status = "failed"
            transaction.errors.extend(verification["errors"])
            transaction.transaction_log.append({"stage": "verified", "status": "failed", "errors": verification["errors"]})
        return transaction

    def commit_transaction(self, transaction: T30Transaction) -> T30Transaction:
        if transaction.status != "verified":
            return self._fail(transaction, "commit_requires_verified")
        transaction.status = "committed"
        transaction.transaction_log.append({"stage": "committed", "status": "success", "sandbox_only": True})
        return transaction

    def rollback_transaction(self, transaction: T30Transaction) -> T30Transaction:
        try:
            backup = Path(transaction.backup_path)
            sandbox = Path(transaction.sandbox_dwg_path)
            if backup.exists():
                copy2(backup, sandbox)
            transaction.status = "rolled_back"
            transaction.transaction_log.append({"stage": "rolled_back", "status": "success"})
        except Exception as exc:
            transaction.status = "failed"
            transaction.errors.append(str(exc))
            transaction.transaction_log.append({"stage": "rolled_back", "status": "failed", "error": str(exc)})
        return transaction

    def _fail(self, transaction: T30Transaction, error: str) -> T30Transaction:
        transaction.status = "failed"
        transaction.errors.append(error)
        transaction.transaction_log.append({"stage": transaction.status, "status": "failed", "error": error})
        return transaction

