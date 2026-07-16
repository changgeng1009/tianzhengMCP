from adapters.product_adapter import ProductAdapter
from runtime.contracts import RuntimeMode, SupportLevel


class TianzhengHvacAdapter(ProductAdapter):
    mode = RuntimeMode.TIANZHENG_HVAC
    PRODUCT_NAMES = frozenset({"tianzheng_hvac"})
    WATER_CALLS_ALLOWED = False
    WRITE_SUPPORT = SupportLevel.INTERFACE_ONLY
    READ_STATUS = "PARTIALLY_IMPLEMENTED"
    REAL_BACKEND_STATUS = "NOT_IMPLEMENTED"

    def capabilities(self):
        return {
            "adapter": type(self).__name__,
            "mode": self.mode.value,
            "runtime_mode": self.mode.value,
            "product": "tianzheng_hvac",
            "status": "READ_INTERFACE_PARTIALLY_IMPLEMENTED",
            "read_status": self.READ_STATUS,
            "product_detection": SupportLevel.INTERFACE_ONLY.value,
            "read_scan": SupportLevel.INTERFACE_ONLY.value,
            "geometry_fallback": SupportLevel.IMPLEMENTED.value,
            "write_supported": False,
            "write_support_level": self.WRITE_SUPPORT.value,
            "real_backend_status": self.REAL_BACKEND_STATUS,
            "supported_capabilities": [
                "tianzheng_hvac_scan_plan",
                "generic_autocad_geometry_fallback",
                "tianzheng_hvac_write_contract",
            ],
            "unsupported_capabilities": [
                "real_cad_read",
                "real_cad_write",
                "native_topology_verified",
                "engineering_semantics_verified",
            ],
            "required_backends": ["offline"],
            "required_approval": "L0_READ_ONLY",
            "workflow_candidates": [
                "tianzheng_hvac_scan_plan",
                "tianzheng_hvac_write_placeholder",
            ],
            "limitations": [
                "只读接口部分实现",
                "写入仅接口占位",
                "Real backend 未实现",
            ],
            "verification_requirements": [
                "object_type_verified",
                "display_environment_verified",
                "visual_review_verified",
                "engineering_review_required",
            ],
            "object_interfaces": [
                "Room", "Duct", "HydronicPipe", "Equipment", "AirTerminal", "Annotation"
            ],
            "command_registry": SupportLevel.INTERFACE_ONLY.value,
        }
