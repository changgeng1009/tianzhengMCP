"""S3 产品档案与独立运行时的静态、离线合同。

本模块不导入 CAD bridge、COM 或任何文件扫描器。产品描述“做什么”，
执行运行时描述“在哪里运行”；两者的兼容性与当前可用性必须分别表达。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from .errors import (
    ProductCapabilityUnavailable,
    ProductModeConflict,
    RealExecutionNotAvailable,
)


class ProductId(str, Enum):
    GENERIC_AUTOCAD = "generic_autocad"
    TIANZHENG_WATER = "tianzheng_water"
    TIANZHENG_HVAC = "tianzheng_hvac"
    OFFLINE_ANALYSIS = "offline_analysis"


class ExecutionRuntime(str, Enum):
    OFFLINE = "offline"
    MOCK = "mock"
    COM = "com"
    OBJECTARX = "objectarx"


class ProductRuntimeUnavailable(RealExecutionNotAvailable):
    """产品与运行时组合当前没有可用的安全实现。"""

    code = "PRODUCT_RUNTIME_NOT_AVAILABLE"


_PRODUCT_ALIASES = {
    "autocad": ProductId.GENERIC_AUTOCAD.value,
    "generic_autocad": ProductId.GENERIC_AUTOCAD.value,
    "offline": ProductId.OFFLINE_ANALYSIS.value,
    "unknown": ProductId.OFFLINE_ANALYSIS.value,
    "offline_analysis": ProductId.OFFLINE_ANALYSIS.value,
}


def normalize_product_id(value: object) -> str | None:
    """归一化 S2 兼容别名；未知值留给 Registry fail-closed。"""

    if value in (None, ""):
        return None
    identifier = value.value if isinstance(value, ProductId) else str(value)
    return _PRODUCT_ALIASES.get(identifier, identifier)


@dataclass(frozen=True)
class ProductProfile:
    product_id: ProductId
    cad_platform: str
    professional_domain: str
    support_status: str
    capabilities: tuple[str, ...]
    required_backends: tuple[str, ...]
    compatible_runtimes: tuple[ExecutionRuntime, ...]
    currently_available_runtimes: tuple[ExecutionRuntime, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["product_id"] = self.product_id.value
        payload["capabilities"] = list(self.capabilities)
        payload["required_backends"] = list(self.required_backends)
        payload["compatible_runtimes"] = [item.value for item in self.compatible_runtimes]
        payload["currently_available_runtimes"] = [
            item.value for item in self.currently_available_runtimes
        ]
        payload["limitations"] = list(self.limitations)
        return payload


@dataclass(frozen=True)
class ProductRuntimeSelection:
    product: str
    execution_runtime: str
    product_status: str
    runtime_status: str
    required_backends: tuple[str, ...]
    capabilities: tuple[str, ...]
    execution_allowed: bool
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductProfileRegistry:
    """产品真值表；Manifest 不能覆盖其状态或能力。"""

    _PROFILES = (
        ProductProfile(
            ProductId.GENERIC_AUTOCAD,
            "AutoCAD",
            "generic_cad",
            "OFFLINE_PLANNING_IMPLEMENTED",
            (
                "inspect_drawing",
                "analyze_reference",
                "redraw_from_reference_plan",
                "compare_drawings",
                "visual_review_plan",
            ),
            ("offline", "original_redraw_adapter"),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK, ExecutionRuntime.COM, ExecutionRuntime.OBJECTARX),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK),
            ("真实 AutoCAD backend 未实现", "COM/ObjectARX 当前 NOT_AVAILABLE"),
        ),
        ProductProfile(
            ProductId.TIANZHENG_WATER,
            "AutoCAD + Tianzheng Water",
            "water_supply_and_drainage",
            "OFFLINE_PLANNING_IMPLEMENTED",
            (
                "tianzheng_water_scan_plan",
                "tianzheng_water_missing_detection_plan",
                "tianzheng_water_completion_plan",
                "generic_autocad_geometry_fallback",
            ),
            ("offline",),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK, ExecutionRuntime.COM, ExecutionRuntime.OBJECTARX),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK),
            ("天正 Water Real backend 未实现", "原生拓扑和工程语义未验证"),
        ),
        ProductProfile(
            ProductId.TIANZHENG_HVAC,
            "AutoCAD + Tianzheng HVAC",
            "hvac",
            "INTERFACE_ONLY",
            (
                "tianzheng_hvac_scan_plan",
                "generic_autocad_geometry_fallback",
                "tianzheng_hvac_write_contract",
            ),
            ("offline",),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK, ExecutionRuntime.COM, ExecutionRuntime.OBJECTARX),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK),
            ("暖通写入仅接口占位", "天正 HVAC Real backend 未实现"),
        ),
        ProductProfile(
            ProductId.OFFLINE_ANALYSIS,
            "none",
            "offline_analysis",
            "IMPLEMENTED",
            (
                "offline_document_comparison",
                "offline_capability_audit",
                "manifest_validation",
                "deterministic_plan_build",
            ),
            ("offline",),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK),
            (ExecutionRuntime.OFFLINE, ExecutionRuntime.MOCK),
            ("不读取真实 CAD 文件", "不提供真实 CAD 执行能力"),
        ),
    )

    def __init__(self) -> None:
        self._by_id = {profile.product_id.value: profile for profile in self._PROFILES}

    def get(self, product: str | ProductId) -> ProductProfile:
        identifier = normalize_product_id(product)
        try:
            return self._by_id[identifier]
        except KeyError as exc:
            raise ProductCapabilityUnavailable(
                f"未注册 ProductProfile: {identifier}",
                field="product.profile",
                details={"allowed_products": list(self._by_id)},
            ) from exc

    def list(self) -> tuple[ProductProfile, ...]:
        return self._PROFILES


class ProductRuntimeRouter:
    """只选择静态离线/Mock 合同；Real runtime 一律 fail-closed。"""

    def __init__(self, registry: ProductProfileRegistry | None = None) -> None:
        self.registry = registry or ProductProfileRegistry()

    def select(
        self,
        product: str | ProductId,
        execution_runtime: str | ExecutionRuntime = ExecutionRuntime.OFFLINE,
    ) -> ProductRuntimeSelection:
        profile = self.registry.get(product)
        try:
            runtime = (
                execution_runtime
                if isinstance(execution_runtime, ExecutionRuntime)
                else ExecutionRuntime(str(execution_runtime))
            )
        except ValueError as exc:
            raise ProductRuntimeUnavailable(
                f"未知 execution runtime: {execution_runtime}",
                field="runtime.execution_runtime",
                details={"allowed_runtimes": [item.value for item in ExecutionRuntime]},
            ) from exc
        if runtime not in profile.compatible_runtimes:
            details = {"product": profile.product_id.value, "runtime": runtime.value}
            if runtime in {ExecutionRuntime.COM, ExecutionRuntime.OBJECTARX}:
                details.update(
                    {"runtime_status": "NOT_AVAILABLE", "real_backend": "NOT_IMPLEMENTED"}
                )
            raise ProductRuntimeUnavailable(
                f"Product {profile.product_id.value} 不兼容 runtime {runtime.value}",
                field="runtime.execution_runtime",
                details=details,
                suggested_action="选择 offline 或 mock，仅生成离线/Mock 计划",
            )
        if runtime not in profile.currently_available_runtimes:
            raise ProductRuntimeUnavailable(
                f"runtime {runtime.value} 当前 NOT_AVAILABLE，不能选择为执行环境",
                field="runtime.execution_runtime",
                details={
                    "product": profile.product_id.value,
                    "runtime": runtime.value,
                    "runtime_status": "NOT_AVAILABLE",
                    "real_backend": "NOT_IMPLEMENTED",
                },
                suggested_action="选择 offline 或 mock，仅生成离线/Mock 计划",
            )
        return ProductRuntimeSelection(
            product=profile.product_id.value,
            execution_runtime=runtime.value,
            product_status=profile.support_status,
            runtime_status=("IMPLEMENTED_BASELINE" if runtime is ExecutionRuntime.MOCK else "IMPLEMENTED"),
            required_backends=profile.required_backends,
            capabilities=profile.capabilities,
            execution_allowed=False,
            limitations=profile.limitations,
        )

    def select_from_manifest(self, manifest: Mapping[str, Any]) -> ProductRuntimeSelection:
        product_block = manifest.get("product")
        runtime_block = manifest.get("runtime")
        product_mapping = product_block if isinstance(product_block, Mapping) else {}
        runtime_mapping = runtime_block if isinstance(runtime_block, Mapping) else {}
        profile = normalize_product_id(product_mapping.get("profile"))
        requested = normalize_product_id(product_mapping.get("requested_product"))
        if profile and requested and profile != requested:
            raise ProductModeConflict(
                "product.profile 与兼容字段 product.requested_product 冲突",
                field="product.profile",
                details={"profile": profile, "requested_product": requested},
                suggested_action="使用同一产品声明，或仅保留 S3 profile 字段",
            )
        product = profile or requested
        if not product:
            raise ProductCapabilityUnavailable("Manifest 缺少产品声明", field="product.profile")
        legacy_mode = runtime_mapping.get("runtime_mode")
        legacy_expected = {
            "plain_autocad": ProductId.GENERIC_AUTOCAD.value,
            "tianzheng_water": ProductId.TIANZHENG_WATER.value,
            "tianzheng_hvac": ProductId.TIANZHENG_HVAC.value,
            "offline_analysis": ProductId.OFFLINE_ANALYSIS.value,
        }.get(str(legacy_mode))
        if legacy_expected and product != legacy_expected:
            raise ProductModeConflict(
                "S3 product.profile 与 S2 runtime_mode 冲突",
                field="runtime.runtime_mode",
                details={
                    "profile": product,
                    "runtime_mode": legacy_mode,
                    "expected_product": legacy_expected,
                },
                suggested_action="使用与产品一致的 runtime_mode，或迁移到 execution_runtime",
            )
        runtime = runtime_mapping.get("execution_runtime", ExecutionRuntime.OFFLINE.value)
        return self.select(str(product), str(runtime))


__all__ = [
    "ExecutionRuntime",
    "ProductId",
    "ProductProfile",
    "ProductProfileRegistry",
    "ProductRuntimeRouter",
    "ProductRuntimeSelection",
    "ProductRuntimeUnavailable",
    "normalize_product_id",
]
