"""有界、带 TTL 的 request_id / idempotency replay guard。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import time
from typing import Any

from .policy import LocalTransportPolicy


class ReplayDecision(str, Enum):
    NEW = "NEW"
    DUPLICATE_SAME = "DUPLICATE_SAME"


class ReplayConflictError(ValueError):
    pass


@dataclass(frozen=True)
class _ReplayRecord:
    request_id: str
    idempotency_key: str
    payload_hash: str
    expires_at: float


class InMemoryReplayGuard:
    """仅用于单进程 transport 基线；持久化 replay 由后续 job 层实现。"""

    def __init__(self, policy: LocalTransportPolicy | None = None):
        self.policy = policy or LocalTransportPolicy()
        self._by_request: OrderedDict[str, _ReplayRecord] = OrderedDict()
        self._by_idempotency: dict[str, _ReplayRecord] = {}

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _prune(self, now: float) -> None:
        expired = [key for key, record in self._by_request.items() if record.expires_at <= now]
        for request_id in expired:
            record = self._by_request.pop(request_id)
            if self._by_idempotency.get(record.idempotency_key) == record:
                self._by_idempotency.pop(record.idempotency_key, None)
        while len(self._by_request) >= self.policy.max_pending_requests:
            _, record = self._by_request.popitem(last=False)
            if self._by_idempotency.get(record.idempotency_key) == record:
                self._by_idempotency.pop(record.idempotency_key, None)

    def check_and_record(
        self,
        request_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        *,
        now: float | None = None,
    ) -> ReplayDecision:
        if not request_id or not idempotency_key:
            raise ValueError("request_id 和 idempotency_key 均不能为空")
        current = time.monotonic() if now is None else now
        self._prune(current)
        payload_hash = self._payload_hash(payload)
        request_record = self._by_request.get(request_id)
        key_record = self._by_idempotency.get(idempotency_key)
        existing = request_record or key_record
        if existing:
            if (
                existing.request_id == request_id
                and existing.idempotency_key == idempotency_key
                and existing.payload_hash == payload_hash
            ):
                return ReplayDecision.DUPLICATE_SAME
            raise ReplayConflictError("request_id 或 idempotency_key 已用于不同请求")
        record = _ReplayRecord(
            request_id=request_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            expires_at=current + self.policy.replay_ttl_seconds,
        )
        self._by_request[request_id] = record
        self._by_idempotency[idempotency_key] = record
        return ReplayDecision.NEW
