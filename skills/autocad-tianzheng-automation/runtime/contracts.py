from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class RuntimeMode(str, Enum):
    PLAIN_AUTOCAD = "plain_autocad"
    TIANZHENG_WATER = "tianzheng_water"
    TIANZHENG_HVAC = "tianzheng_hvac"
    AUTO_DETECT = "auto_detect"
    OFFLINE_ANALYSIS = "offline_analysis"


class SupportLevel(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    INTERFACE_ONLY = "INTERFACE_ONLY"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNSAFE = "UNSAFE"


@dataclass(frozen=True)
class RuntimeSelection:
    mode: RuntimeMode
    product: str
    source: str


@dataclass(frozen=True)
class RoutingTraceEntry:
    source: str
    field: str
    value: Any
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "field": self.field,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RuntimeSelectionResult:
    mode: RuntimeMode
    product: str
    source: str
    trace: tuple[RoutingTraceEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.mode.value,
            "product": self.product,
            "source": self.source,
            "trace": [item.to_dict() for item in self.trace],
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    workflow_type: str
    status: str
    supported_runtime_modes: tuple[str, ...]
    supported_products: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    required_backend_types: tuple[str, ...]
    minimum_approval_level: str
    real_execution_required: bool
    stages: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    recovery_requirements: tuple[str, ...]
    expected_artifacts: tuple[str, ...] = ()
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "status": self.status,
            "supported_runtime_modes": list(self.supported_runtime_modes),
            "supported_products": list(self.supported_products),
            "required_capabilities": list(self.required_capabilities),
            "required_backend_types": list(self.required_backend_types),
            "minimum_approval_level": self.minimum_approval_level,
            "real_execution_required": self.real_execution_required,
            "stages": list(self.stages),
            "verification_requirements": list(self.verification_requirements),
            "recovery_requirements": list(self.recovery_requirements),
            "expected_artifacts": list(self.expected_artifacts),
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class WorkflowSelectionResult:
    definition: WorkflowDefinition
    selected: bool
    executable_currently: bool
    blocked_reasons: tuple[str, ...] = ()
    trace: tuple[RoutingTraceEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition": self.definition.to_dict(),
            "selected": self.selected,
            "executable_currently": self.executable_currently,
            "blocked_reasons": list(self.blocked_reasons),
            "trace": [item.to_dict() for item in self.trace],
        }


class ICadWorkflow(ABC):
    @abstractmethod
    def build_plan(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ICadProductAdapter(ABC):
    mode: RuntimeMode

    @abstractmethod
    def capabilities(self) -> Mapping[str, Any]: ...


class ICadBackend(ABC):
    name: str

    @abstractmethod
    def build_plan(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ICapabilityRegistry(ABC):
    @abstractmethod
    def list_capabilities(self, mode: RuntimeMode) -> list[Mapping[str, Any]]: ...


class IDocumentGuard(ABC):
    @abstractmethod
    def verify(self, expected: Mapping[str, Any], observed: Mapping[str, Any]) -> None: ...


class IApprovalGate(ABC):
    @abstractmethod
    def authorize(self, approval: Mapping[str, Any], context: Mapping[str, Any]) -> None: ...


class IJobRunner(ABC):
    @abstractmethod
    def run(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]: ...


class IVerificationProvider(ABC):
    @abstractmethod
    def verify(self, evidence: Mapping[str, Any]) -> Mapping[str, Any]: ...
