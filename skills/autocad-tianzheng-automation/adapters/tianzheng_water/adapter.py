from runtime.contracts import ICadProductAdapter, RuntimeMode


class TianzhengWaterAdapter(ICadProductAdapter):
    mode = RuntimeMode.TIANZHENG_WATER
    PRODUCT_NAMES = frozenset({"tianzheng_water"})
    HVAC_CALLS_ALLOWED = False
    STATUS = "OFFLINE_PLANNING_IMPLEMENTED"
    REAL_BACKEND_STATUS = "NOT_IMPLEMENTED"

    def capabilities(self):
        return {
            "adapter": type(self).__name__,
            "mode": self.mode.value,
            "runtime_mode": self.mode.value,
            "product": "tianzheng_water",
            "status": self.STATUS,
            "read_supported": True,
            "write_supported": False,
            "real_backend_status": self.REAL_BACKEND_STATUS,
            "supported_capabilities": [
                "tianzheng_water_scan_plan",
                "tianzheng_water_missing_detection_plan",
                "tianzheng_water_completion_plan",
                "generic_autocad_geometry_fallback",
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
                "tianzheng_water_scan_plan",
                "tianzheng_water_completion_plan",
            ],
            "limitations": [
                "Real backend 未实现",
                "原生拓扑未验证",
                "工程语义完整性未验证",
            ],
            "verification_requirements": [
                "object_type_verified",
                "display_environment_verified",
                "visual_review_verified",
                "engineering_review_required",
            ],
            "object_families": [
                "TDb/TCH", "Pipe", "DoubleLinePipe", "Valve", "Fitting",
                "Equipment", "Tank", "Pump", "ProfessionalAnnotation",
            ],
            "systems": ["water_supply", "drainage", "hydrant", "sprinkler"],
            "native_topology_verified": "NOT_VERIFIED",
            "engineering_semantic_completeness_verified": "NOT_VERIFIED",
            "engineering_review_status": "MANUAL_REVIEW_REQUIRED",
        }
