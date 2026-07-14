"""Backend-independent CAD execution contracts and implementations."""

from .base import CadBackend
from .registry import BackendRegistry, build_default_registry
from .router import BackendRouter

__all__ = ["CadBackend", "BackendRegistry", "BackendRouter", "build_default_registry"]
