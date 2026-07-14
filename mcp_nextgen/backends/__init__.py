"""NextGen 隔离 backend。"""

from .base import BackendError, BackendUnavailableError, ICadBackend
from .mock import MockCadBackend
from .models import BackendCapability, BackendSession, FailureInjection, MockEntity, ProtectedRegion

__all__ = [
    "BackendCapability", "BackendError", "BackendSession", "BackendUnavailableError",
    "FailureInjection", "ICadBackend", "MockCadBackend", "MockEntity", "ProtectedRegion",
]
