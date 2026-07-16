"""纯离线 Product Adapter 与 Backend 静态能力注册表。

本模块只包含不可变合同和选择规则，不导入 COM、CAD bridge 或真实执行器。
Manifest 只能请求已有合同，不能通过自述字段提升 backend availability。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from runtime.contracts import ICadProductAdapter, RuntimeMode
from runtime.errors import SkillRuntimeError

from .generic_autocad import GenericAutoCadAdapter
from .original_redraw_skill_adapter import OriginalRedrawSkillAdapter
from .product_adapter import ProductAdapter
from .tianzheng_hvac import TianzhengHvacAdapter
from .tianzheng_water import TianzhengWaterAdapter


class AdapterStatus(str, Enum):
    OFFLINE_PLANNING_IMPLEMENTED = "OFFLINE_PLANNING_IMPLEMENTED"
    READ_INTERFACE_PARTIALLY_IMPLEMENTED = "READ_INTERFACE_PARTIALLY_IMPLEMENTED"
    IMPLEMENTED = "IMPLEMENTED"


class BackendAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    AVAILABLE_FOR_OFFLINE_PLANNING = "AVAILABLE_FOR_OFFLINE_PLANNING"
    AVAILABLE_FOR_MOCK = "AVAILABLE_FOR_MOCK"
    DISABLED_CONTRACT_ONLY = "DISABLED_CONTRACT_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class RegistryError(SkillRuntimeError):
    """带结构化细节的 fail-closed registry 错误。"""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: Mapping[str, Any] | None = None,
        suggested_action: str = "选择已注册的离线或 Mock 能力",
    ) -> None:
        super().__init__(message)
        self.field = field
        self.details = dict(details or {})
        self.suggested_action = suggested_action

    def to_error(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": str(self),
                "field": self.field,
                "source": "static_capability_registry",
                "details": self.details,
                "suggested_action": self.suggested_action,
            },
        }


class ProductModeConflict(RegistryError):
    code = "PRODUCT_MODE_CONFLICT"


class ProductCapabilityUnavailable(RegistryError):
    code = "PRODUCT_CAPABILITY_UNAVAILABLE"


class BackendNotAvailable(RegistryError):
    code = "BACKEND_NOT_AVAILABLE"


class BackendConflict(RegistryError):
    code = "BACKEND_CONFLICT"


class BackendOverrideForbidden(RegistryError):
    code = "CONFIG_BACKEND_OVERRIDE_FORBIDDEN"


class OfflineAnalysisAdapter(ProductAdapter):
    """不接触 CAD 文件的离线分析适配器。"""

    mode = RuntimeMode.OFFLINE_ANALYSIS
    # ``unknown``/``offline`` remain accepted S2 input aliases.  S3 contracts
    # always publish the canonical ProductProfile identifier below.
    PRODUCT_NAMES = frozenset({"unknown", "offline", "offline_analysis"})
    STATUS = AdapterStatus.IMPLEMENTED.value

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "adapter": type(self).__name__,
            "mode": self.mode.value,
            "runtime_mode": self.mode.value,
            "product": "offline_analysis",
            "status": self.STATUS,
            "read_supported": True,
            "write_supported": False,
            "real_backend_status": "NOT_IMPLEMENTED",
            "supported_capabilities": [
                "offline_document_comparison",
                "offline_capability_audit",
                "manifest_validation",
                "deterministic_plan_build",
            ],
            "unsupported_capabilities": ["real_cad_read", "real_cad_write"],
            "required_backends": ["offline"],
            "required_approval": "L0_READ_ONLY",
            "workflow_candidates": [
                "offline_document_comparison",
                "offline_capability_audit",
            ],
            "limitations": ["不读取真实 CAD 文件", "不提供真实执行能力"],
            "verification_requirements": ["visual_review_required"],
        }


@dataclass(frozen=True)
class ProductAdapterSelection:
    runtime_mode: str
    product: str
    adapter: str
    status: str
    supported_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    required_backends: tuple[str, ...]
    required_approval: str
    workflow_candidates: tuple[str, ...]
    limitations: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    real_backend_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductAdapterRegistry:
    """按已确定 runtime mode 返回唯一产品适配器。"""

    _EXPECTED_PRODUCT = {
        RuntimeMode.PLAIN_AUTOCAD: "generic_autocad",
        RuntimeMode.TIANZHENG_WATER: "tianzheng_water",
        RuntimeMode.TIANZHENG_HVAC: "tianzheng_hvac",
        RuntimeMode.OFFLINE_ANALYSIS: "offline_analysis",
    }
    _PRODUCT_ALIASES = {
        "autocad": "generic_autocad",
        "unknown": "offline_analysis",
        "offline": "offline_analysis",
        "offline_analysis": "offline_analysis",
    }

    def __init__(self, adapters: Iterable[ICadProductAdapter] | None = None) -> None:
        selected = tuple(
            adapters
            or (
                GenericAutoCadAdapter(),
                TianzhengWaterAdapter(),
                TianzhengHvacAdapter(),
                OfflineAnalysisAdapter(),
            )
        )
        self._by_mode = {adapter.mode: adapter for adapter in selected}
        if len(self._by_mode) != len(selected):
            raise ValueError("每个 runtime mode 只能注册一个 Product Adapter")
        self._compatibility_adapters: tuple[ProductAdapter, ...] = (
            OriginalRedrawSkillAdapter(),
        )

    @staticmethod
    def _runtime_mode(value: str | RuntimeMode) -> RuntimeMode:
        try:
            mode = value if isinstance(value, RuntimeMode) else RuntimeMode(str(value))
        except ValueError as exc:
            raise ProductModeConflict(
                f"未知 runtime mode: {value}", field="runtime.runtime_mode"
            ) from exc
        if mode is RuntimeMode.AUTO_DETECT:
            raise ProductModeConflict(
                "auto_detect 必须先完成离线路由，不能直接选择 Product Adapter",
                field="runtime.runtime_mode",
            )
        return mode

    def get(
        self,
        runtime_mode: str | RuntimeMode,
        requested_product: str | None = None,
    ) -> ICadProductAdapter:
        mode = self._runtime_mode(runtime_mode)
        adapter = self._by_mode.get(mode)
        if adapter is None:
            raise ProductCapabilityUnavailable(
                f"runtime mode {mode.value} 没有已注册的离线 Product Adapter",
                field="runtime.runtime_mode",
            )
        expected = self._EXPECTED_PRODUCT[mode]
        if requested_product not in (None, ""):
            normalized = self._PRODUCT_ALIASES.get(str(requested_product), str(requested_product))
            if normalized != expected:
                raise ProductModeConflict(
                    f"runtime mode {mode.value} 与产品 {requested_product} 冲突",
                    field="product.requested_product",
                    details={"runtime_mode": mode.value, "expected_product": expected},
                )
        return adapter

    def list(self) -> tuple[ICadProductAdapter, ...]:
        return tuple(self._by_mode[mode] for mode in self._EXPECTED_PRODUCT)

    def list_contracts(self) -> tuple[dict[str, Any], ...]:
        """返回标准产品与兼容适配器的可审计静态合同。"""
        adapters = (*self.list(), *self._compatibility_adapters)
        return tuple(adapter.contract() for adapter in adapters)


class ProductCapabilityResolver:
    """将适配器静态合同与 Manifest 的 required capabilities 对照。"""

    def __init__(self, registry: ProductAdapterRegistry | None = None) -> None:
        self.registry = registry or ProductAdapterRegistry()

    def resolve(
        self,
        runtime_mode: str | RuntimeMode,
        *,
        requested_product: str | None = None,
        required_capabilities: Iterable[str] = (),
    ) -> ProductAdapterSelection:
        adapter = self.registry.get(runtime_mode, requested_product)
        contract = dict(adapter.capabilities())
        supported = tuple(sorted(set(contract.get("supported_capabilities", ()))))
        required = tuple(sorted(set(required_capabilities)))
        missing = tuple(item for item in required if item not in supported)
        declared_unsupported = tuple(contract.get("unsupported_capabilities", ()))
        return ProductAdapterSelection(
            runtime_mode=str(contract["runtime_mode"]),
            product=str(contract["product"]),
            adapter=str(contract["adapter"]),
            status=str(contract["status"]),
            supported_capabilities=supported,
            unsupported_capabilities=tuple(sorted(set(declared_unsupported + missing))),
            required_backends=tuple(contract.get("required_backends", ())),
            required_approval=str(contract.get("required_approval", "L0_READ_ONLY")),
            workflow_candidates=tuple(contract.get("workflow_candidates", ())),
            limitations=tuple(contract.get("limitations", ())),
            verification_requirements=tuple(contract.get("verification_requirements", ())),
            real_backend_status=str(contract.get("real_backend_status", "NOT_IMPLEMENTED")),
        )

    def require(
        self,
        runtime_mode: str | RuntimeMode,
        *,
        requested_product: str | None = None,
        required_capabilities: Iterable[str] = (),
    ) -> ProductAdapterSelection:
        required = tuple(sorted(set(required_capabilities)))
        result = self.resolve(
            runtime_mode,
            requested_product=requested_product,
            required_capabilities=required,
        )
        missing = tuple(item for item in required if item not in result.supported_capabilities)
        if missing:
            raise ProductCapabilityUnavailable(
                "所选 Product Adapter 缺少必需能力",
                field="product.required_capabilities",
                details={"missing": list(missing), "adapter": result.adapter},
            )
        return result


@dataclass(frozen=True)
class BackendContract:
    backend_id: str
    availability_status: str
    support_level: str
    selection_available: bool
    offline_planning_supported: bool
    mock_supported: bool
    real_execution_supported: bool
    limitations: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendSelectionResult:
    backend: str
    availability_status: str
    support_level: str
    selected: bool
    offline_planning_supported: bool
    mock_supported: bool
    real_execution_supported: bool
    require_real_execution: bool
    available_alternatives: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BackendRegistry:
    """不可由 Manifest 覆盖的 backend 能力真值表。"""

    _CONTRACTS = (
        BackendContract(
            "offline", BackendAvailability.AVAILABLE.value, "IMPLEMENTED", True,
            True, False, False, ("仅离线规划、验证和报告",),
        ),
        BackendContract(
            "original_redraw_adapter",
            BackendAvailability.AVAILABLE_FOR_OFFLINE_PLANNING.value,
            "PARTIALLY_IMPLEMENTED", True, True, False, False,
            ("只映射原始工作流", "Real COM execution disabled"),
            ("original-redraw-adapter",),
        ),
        BackendContract(
            "nextgen_mock", BackendAvailability.AVAILABLE_FOR_MOCK.value,
            "IMPLEMENTED_BASELINE", True, False, True, False,
            ("Mock-only", "NextGen control plane partially implemented"),
            ("nextgen-mock",),
        ),
        BackendContract(
            "legacy_contract_disabled", BackendAvailability.DISABLED_CONTRACT_ONLY.value,
            "DISABLED_CONTRACT_ONLY", False, False, False, False,
            ("仅合同存在", "禁止执行"), ("legacy-contract-disabled",),
        ),
        BackendContract(
            "legacy_com", BackendAvailability.NOT_AVAILABLE.value,
            "NOT_IMPLEMENTED", False, False, False, False,
            ("Legacy/COM 不可用",), ("legacy-com",),
        ),
        BackendContract(
            "nextgen_real", BackendAvailability.NOT_AVAILABLE.value,
            "NOT_IMPLEMENTED", False, False, False, False,
            ("NextGen Real backend 未实现",), ("nextgen-real",),
        ),
        BackendContract(
            "autocad_dotnet_plugin", BackendAvailability.NOT_AVAILABLE.value,
            "NOT_IMPLEMENTED", False, False, False, False,
            ("AutoCAD 进程内 .NET 插件未实现",), ("autocad-dotnet-plugin",),
        ),
        BackendContract(
            "tianzheng_water_real", BackendAvailability.NOT_AVAILABLE.value,
            "NOT_IMPLEMENTED", False, False, False, False,
            ("天正给排水 Real backend 未实现",), ("tianzheng-water-real",),
        ),
        BackendContract(
            "tianzheng_hvac_real", BackendAvailability.NOT_AVAILABLE.value,
            "NOT_IMPLEMENTED", False, False, False, False,
            ("天正暖通 Real backend 未实现",), ("tianzheng-hvac-real",),
        ),
    )

    def __init__(self) -> None:
        self._by_id = {contract.backend_id: contract for contract in self._CONTRACTS}
        self._aliases = {
            alias: contract.backend_id
            for contract in self._CONTRACTS
            for alias in contract.aliases
        }

    def canonical_id(self, backend_id: str) -> str:
        normalized = str(backend_id).strip()
        return self._aliases.get(normalized, normalized)

    def get(self, backend_id: str) -> BackendContract:
        canonical = self.canonical_id(backend_id)
        try:
            return self._by_id[canonical]
        except KeyError as exc:
            raise BackendNotAvailable(
                f"未注册 backend: {backend_id}",
                field="backend.preferred_backend",
                details={"available_alternatives": list(self.available_ids())},
            ) from exc

    def list(self) -> tuple[BackendContract, ...]:
        return self._CONTRACTS

    def available_ids(self, *, mock_allowed: bool = True) -> tuple[str, ...]:
        return tuple(
            contract.backend_id
            for contract in self._CONTRACTS
            if contract.selection_available and (mock_allowed or not contract.mock_supported)
        )


class BackendSelector:
    """只依据注册表选择离线/Mock backend，所有 Real 请求均 fail-closed。"""

    _FORBIDDEN_OVERRIDE_FIELDS = frozenset(
        {
            "available",
            "availability",
            "availability_status",
            "support_level",
            "execution_allowed",
            "real_execution_supported",
            "capabilities",
        }
    )

    def __init__(self, registry: BackendRegistry | None = None) -> None:
        self.registry = registry or BackendRegistry()

    def select(
        self,
        preferred_backend: str = "offline",
        *,
        fallback_backends: Iterable[str] = (),
        require_real_execution: bool = False,
        mock_allowed: bool = True,
    ) -> BackendSelectionResult:
        contract = self.registry.get(preferred_backend)
        fallback_ids = tuple(self.registry.canonical_id(item) for item in fallback_backends)
        unknown_fallbacks = tuple(
            item for item in fallback_ids if item not in {c.backend_id for c in self.registry.list()}
        )
        if unknown_fallbacks:
            raise BackendConflict(
                "fallback_backends 包含未注册 backend",
                field="backend.fallback_backends",
                details={"unknown": list(unknown_fallbacks)},
            )
        alternatives = self.registry.available_ids(mock_allowed=mock_allowed)
        if require_real_execution:
            raise BackendNotAvailable(
                "当前没有可用的 Real backend；不得回退到 Mock 并声称真实执行",
                field="backend.require_real_execution",
                details={
                    "requested_backend": contract.backend_id,
                    "available_alternatives": list(alternatives),
                    "real_backend_available": False,
                },
                suggested_action="关闭 require_real_execution，仅生成离线或 Mock 计划",
            )
        if contract.mock_supported and not mock_allowed:
            raise BackendNotAvailable(
                "Manifest 禁止 Mock，但请求了 nextgen_mock",
                field="backend.mock_allowed",
                details={"requested_backend": contract.backend_id},
            )
        if not contract.selection_available:
            raise BackendNotAvailable(
                f"backend {contract.backend_id} 当前状态为 {contract.availability_status}",
                field="backend.preferred_backend",
                details={
                    "requested_backend": contract.backend_id,
                    "availability_status": contract.availability_status,
                    "available_alternatives": list(alternatives),
                    "fallbacks_not_auto_executed": list(fallback_ids),
                },
            )
        return BackendSelectionResult(
            backend=contract.backend_id,
            availability_status=contract.availability_status,
            support_level=contract.support_level,
            selected=True,
            offline_planning_supported=contract.offline_planning_supported,
            mock_supported=contract.mock_supported,
            real_execution_supported=False,
            require_real_execution=False,
            available_alternatives=alternatives,
            limitations=contract.limitations,
        )

    def select_from_manifest(self, manifest: Mapping[str, Any]) -> BackendSelectionResult:
        raw = manifest.get("backend", {})
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise BackendConflict("backend 必须为对象", field="backend")
        forbidden = sorted(self._FORBIDDEN_OVERRIDE_FIELDS.intersection(raw))
        if forbidden:
            raise BackendOverrideForbidden(
                "Manifest 不得覆盖 backend 静态能力状态",
                field="backend",
                details={"forbidden_fields": forbidden},
            )
        preferred = str(
            raw.get("preferred_backend")
            or manifest.get("preferred_backend")
            or "offline"
        )
        fallback = raw.get("fallback_backends", manifest.get("fallback_backend", ()))
        if isinstance(fallback, str):
            fallback = (fallback,)
        if isinstance(fallback, Mapping) or not isinstance(fallback, Iterable):
            raise BackendConflict(
                "fallback_backends 必须为数组", field="backend.fallback_backends"
            )
        return self.select(
            preferred,
            fallback_backends=fallback,
            require_real_execution=bool(
                raw.get(
                    "require_real_execution",
                    manifest.get("require_real_execution", False),
                )
            ),
            mock_allowed=bool(
                raw.get("mock_allowed", manifest.get("mock_allowed", True))
            ),
        )


__all__ = [
    "AdapterStatus",
    "BackendAvailability",
    "BackendConflict",
    "BackendContract",
    "BackendNotAvailable",
    "BackendOverrideForbidden",
    "BackendRegistry",
    "BackendSelectionResult",
    "BackendSelector",
    "OfflineAnalysisAdapter",
    "ProductAdapterRegistry",
    "ProductAdapterSelection",
    "ProductCapabilityResolver",
    "ProductCapabilityUnavailable",
    "ProductModeConflict",
    "RegistryError",
]
