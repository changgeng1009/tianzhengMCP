"""Mock plugin runtime 的纯数据生命周期模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Any

from mcp_nextgen.protocol.models import DocumentIdentity


class RuntimeState(str, Enum):
    CREATED = "CREATED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    DISPOSED = "DISPOSED"


@dataclass
class DocumentContext:
    context_id: str
    session_id: str
    bound_identity: DocumentIdentity
    current_identity: DocumentIdentity
    active: bool = True
    manual_save_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "session_id": self.session_id,
            "bound_identity": self.bound_identity.to_dict(),
            "current_identity": self.current_identity.to_dict(),
            "active": self.active,
            "manual_save_required": self.manual_save_required,
        }


@dataclass
class CancellationToken:
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()
