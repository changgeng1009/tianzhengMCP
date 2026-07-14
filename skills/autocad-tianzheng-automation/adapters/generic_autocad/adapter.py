from runtime.contracts import ICadProductAdapter, RuntimeMode


class GenericAutoCadAdapter(ICadProductAdapter):
    mode = RuntimeMode.PLAIN_AUTOCAD
    PRODUCT_NAMES = frozenset({"autocad"})
    TIANZHENG_CALLS_ALLOWED = False

    def capabilities(self):
        return {
            "mode": self.mode.value,
            "read_supported": True,
            "write_supported": False,
            "object_types": [
                "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline",
                "AcDbArc", "AcDbCircle", "AcDbText", "AcDbMText",
                "AcDbBlockReference", "AcDbDimension", "AcDbHatch", "AcDbTable",
                "Layer", "Linetype", "TextStyle", "DimStyle", "Layout", "Viewport", "Xref",
            ],
            "limitation": "当前统一入口仅离线规划；对象级支持需由所选 Legacy 执行器证据确认",
        }

