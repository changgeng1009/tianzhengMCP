from runtime.contracts import ICadProductAdapter, RuntimeMode


class TianzhengWaterAdapter(ICadProductAdapter):
    mode = RuntimeMode.TIANZHENG_WATER
    PRODUCT_NAMES = frozenset({"tianzheng_water"})
    HVAC_CALLS_ALLOWED = False

    def capabilities(self):
        return {
            "mode": self.mode.value,
            "read_supported": True,
            "write_supported": False,
            "object_families": [
                "TDb/TCH", "Pipe", "DoubleLinePipe", "Valve", "Fitting",
                "Equipment", "Tank", "Pump", "ProfessionalAnnotation",
            ],
            "systems": ["water_supply", "drainage", "hydrant", "sprinkler"],
            "native_topology_verified": "NOT_VERIFIED",
            "engineering_semantic_completeness_verified": "MANUAL_REVIEW_REQUIRED",
        }

