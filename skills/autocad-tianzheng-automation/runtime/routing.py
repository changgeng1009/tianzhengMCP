from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from adapters.registry import ProductAdapterSelection, ProductCapabilityResolver

from .contracts import RoutingTraceEntry, RuntimeMode, RuntimeSelectionResult
from .errors import ProductModeConflict, RuntimeModeConflict


_PRODUCT_ALIASES = {
    "autocad": "generic_autocad",
    "offline": "unknown",
    "offline_analysis": "unknown",
    "auto": "unknown",
}
_MODE_PRODUCT = {
    RuntimeMode.PLAIN_AUTOCAD: "generic_autocad",
    RuntimeMode.TIANZHENG_WATER: "tianzheng_water",
    RuntimeMode.TIANZHENG_HVAC: "tianzheng_hvac",
    RuntimeMode.OFFLINE_ANALYSIS: "unknown",
}
_PRODUCT_MODE = {value: key for key, value in _MODE_PRODUCT.items() if value != "unknown"}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mode(value: object, *, allow_auto: bool = True) -> RuntimeMode | None:
    if value in (None, ""):
        return None
    try:
        parsed = RuntimeMode(str(value))
    except ValueError as exc:
        raise RuntimeModeConflict(
            f"未知运行模式: {value}", field="runtime.runtime_mode"
        ) from exc
    if parsed is RuntimeMode.AUTO_DETECT and not allow_auto:
        return None
    return parsed


def _product(value: object) -> str:
    text = str(value or "unknown")
    return _PRODUCT_ALIASES.get(text, text)


class RuntimeConflictDetector:
    def validate(
        self,
        mode: RuntimeMode,
        *,
        requested_product: str,
        prohibited_products: tuple[str, ...],
        document_products: tuple[str, ...],
    ) -> None:
        expected = _MODE_PRODUCT[mode]
        if requested_product != "unknown" and requested_product != expected:
            raise ProductModeConflict(
                f"runtime mode {mode.value} 与产品 {requested_product} 冲突",
                field="product.requested_product",
                details={"runtime_mode": mode.value, "expected_product": expected},
            )
        if expected in prohibited_products:
            raise ProductModeConflict(
                f"所选产品 {expected} 位于 prohibited_products",
                field="product.prohibited_products",
            )
        conflicts = sorted({item for item in document_products if item != expected})
        if conflicts:
            raise ProductModeConflict(
                "文档 expected_product 与所选 runtime/product 冲突",
                field="documents",
                details={"expected_product": expected, "conflicts": conflicts},
            )


class RuntimeRouter:
    """仅依据 Manifest/显式离线元数据路由，不读取任何文档。"""

    def __init__(self, detector: RuntimeConflictDetector | None = None) -> None:
        self.detector = detector or RuntimeConflictDetector()

    def select(
        self,
        manifest: Mapping[str, object],
        *,
        user_mode: str | None = None,
        context_mode: str | None = None,
        detected_product: str | None = None,
    ) -> RuntimeSelectionResult:
        runtime = _mapping(manifest.get("runtime"))
        product_config = _mapping(manifest.get("product"))
        declared_mode = runtime.get("runtime_mode", manifest.get("runtime_mode"))
        requested_product = _product(
            product_config.get("requested_product", manifest.get("product"))
        )
        prohibited = tuple(
            sorted(_product(item) for item in product_config.get("prohibited_products", ()))
        )
        document_products = self._document_products(manifest)
        trace: list[RoutingTraceEntry] = []

        candidates = (
            ("explicit_run_override", "runtime.runtime_mode", user_mode),
            ("project_manifest", "runtime.runtime_mode", declared_mode),
            ("explicit_context", "runtime.runtime_mode", context_mode),
        )
        selected: RuntimeMode | None = None
        source = ""
        for candidate_source, field, value in candidates:
            parsed = _mode(value)
            if parsed is None:
                continue
            trace.append(RoutingTraceEntry(candidate_source, field, value, "按固定优先级采用"))
            if parsed is not RuntimeMode.AUTO_DETECT:
                selected, source = parsed, candidate_source
                break

        detection_product = _product(detected_product) if detected_product else "unknown"
        evidence_products = [
            item for item in (requested_product, detection_product, *document_products)
            if item != "unknown"
        ]
        if selected is None:
            unique = sorted(set(evidence_products))
            if len(unique) > 1:
                raise RuntimeModeConflict(
                    "auto_detect 离线证据包含多个产品",
                    field="runtime.runtime_mode",
                    details={"products": unique},
                )
            if len(unique) == 1 and unique[0] in _PRODUCT_MODE:
                selected = _PRODUCT_MODE[unique[0]]
                source = "explicit_metadata_detection"
                trace.append(
                    RoutingTraceEntry(source, "product/document metadata", unique[0], "唯一离线产品证据")
                )
            elif bool(runtime.get("offline_only")):
                selected = RuntimeMode.OFFLINE_ANALYSIS
                source = "offline_metadata"
                trace.append(
                    RoutingTraceEntry(source, "runtime.offline_only", True, "无产品证据时选择纯离线分析")
                )
            else:
                raise RuntimeModeConflict(
                    "没有足够的显式离线证据唯一选择运行模式",
                    field="runtime.runtime_mode",
                    suggested_action="在 Manifest 中明确 runtime_mode 或 requested_product",
                )

        self.detector.validate(
            selected,
            requested_product=requested_product,
            prohibited_products=prohibited,
            document_products=document_products,
        )
        return RuntimeSelectionResult(
            selected,
            _MODE_PRODUCT[selected],
            source,
            tuple(trace),
        )

    @staticmethod
    def _document_products(manifest: Mapping[str, object]) -> tuple[str, ...]:
        documents = _mapping(manifest.get("documents"))
        found: set[str] = set()
        for category in ("reference_documents", "target_documents", "auxiliary_documents"):
            values = documents.get(category, ())
            if not isinstance(values, (list, tuple)):
                continue
            for document in values:
                if isinstance(document, Mapping):
                    product = _product(document.get("expected_product"))
                    if product != "unknown":
                        found.add(product)
        return tuple(sorted(found))


def select_product(
    manifest: Mapping[str, Any],
    runtime: RuntimeSelectionResult,
    *,
    resolver: ProductCapabilityResolver | None = None,
) -> ProductAdapterSelection:
    product = _mapping(manifest.get("product"))
    return (resolver or ProductCapabilityResolver()).require(
        runtime.mode,
        requested_product=str(product.get("requested_product") or runtime.product),
        required_capabilities=tuple(product.get("required_capabilities") or ()),
    )
