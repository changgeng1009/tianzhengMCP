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

