from runtime.contracts import ICadProductAdapter, RuntimeMode, SupportLevel


class TianzhengHvacAdapter(ICadProductAdapter):
    mode = RuntimeMode.TIANZHENG_HVAC
    PRODUCT_NAMES = frozenset({"tianzheng_hvac"})
    WATER_CALLS_ALLOWED = False
    WRITE_SUPPORT = SupportLevel.INTERFACE_ONLY

    def capabilities(self):
        return {
            "mode": self.mode.value,
            "product_detection": SupportLevel.INTERFACE_ONLY.value,
            "read_scan": SupportLevel.INTERFACE_ONLY.value,
            "geometry_fallback": SupportLevel.IMPLEMENTED.value,
            "write_supported": False,
            "write_support_level": self.WRITE_SUPPORT.value,
            "object_interfaces": [
                "Room", "Duct", "HydronicPipe", "Equipment", "AirTerminal", "Annotation"
            ],
            "command_registry": SupportLevel.INTERFACE_ONLY.value,
        }

