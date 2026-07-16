"""产品与后端适配器。"""

from .generic_autocad import GenericAutoCadAdapter
from .original_redraw_skill_adapter import OriginalRedrawSkillAdapter
from .product_adapter import ProductAdapter
from .registry import (
    BackendAvailability,
    BackendConflict,
    BackendNotAvailable,
    BackendOverrideForbidden,
    BackendRegistry,
    BackendSelector,
    OfflineAnalysisAdapter,
    ProductAdapterRegistry,
    ProductCapabilityResolver,
    ProductCapabilityUnavailable,
    ProductModeConflict,
    RegistryError,
)
from .tianzheng_hvac import TianzhengHvacAdapter
from .tianzheng_water import TianzhengWaterAdapter

__all__ = [
    "BackendAvailability",
    "BackendConflict",
    "BackendNotAvailable",
    "BackendOverrideForbidden",
    "BackendRegistry",
    "BackendSelector",
    "GenericAutoCadAdapter",
    "OriginalRedrawSkillAdapter",
    "ProductAdapter",
    "OfflineAnalysisAdapter",
    "ProductAdapterRegistry",
    "ProductCapabilityResolver",
    "ProductCapabilityUnavailable",
    "ProductModeConflict",
    "RegistryError",
    "TianzhengHvacAdapter",
    "TianzhengWaterAdapter",
]
