"""Professional-domain adapters independent from CAD execution backends."""

from .registry import DomainRegistry, build_default_domain_registry

__all__ = ["DomainRegistry", "build_default_domain_registry"]
