"""产品与后端适配器。"""

from .generic_autocad import GenericAutoCadAdapter
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
    "OfflineAnalysisAdapter",
    "ProductAdapterRegistry",
    "ProductCapabilityResolver",
    "ProductCapabilityUnavailable",
    "ProductModeConflict",
    "RegistryError",
    "TianzhengHvacAdapter",
    "TianzhengWaterAdapter",
]
