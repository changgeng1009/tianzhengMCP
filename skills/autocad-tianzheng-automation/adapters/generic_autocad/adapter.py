from runtime.contracts import ICadProductAdapter, RuntimeMode


class GenericAutoCadAdapter(ICadProductAdapter):
    mode = RuntimeMode.PLAIN_AUTOCAD
    PRODUCT_NAMES = frozenset({"autocad", "generic_autocad"})
    TIANZHENG_CALLS_ALLOWED = False
    STATUS = "OFFLINE_PLANNING_IMPLEMENTED"
    REAL_BACKEND_STATUS = "NOT_IMPLEMENTED"

    def capabilities(self):
        return {
            "adapter": type(self).__name__,
            "mode": self.mode.value,
            "runtime_mode": self.mode.value,
            "product": "generic_autocad",
            "status": self.STATUS,
            "read_supported": True,
            "write_supported": False,
            "real_backend_status": self.REAL_BACKEND_STATUS,
            "supported_capabilities": [
                "inspect_drawing",
                "analyze_reference",
                "redraw_from_reference_plan",
                "align_drawings_plan",
                "compare_drawings",
                "sandbox_edit_plan",
                "verify_output_plan",
                "visual_review_plan",
            ],
            "unsupported_capabilities": ["real_cad_read", "real_cad_write"],
            "required_backends": ["offline", "original_redraw_adapter"],
            "required_approval": "L0_READ_ONLY",
            "workflow_candidates": [
                "generic_autocad_redraw_offline",
                "generic_autocad_clone_plan",
                "pdf_intermediate_dwg_plan",
                "image_dimension_parametric_redraw_plan",
            ],
            "limitations": [
                "当前统一入口仅离线规划",
                "对象级支持需由未来安全 Real backend 独立验证",
            ],
            "verification_requirements": [
                "geometry_verified",
                "visual_review_verified",
            ],
            "object_types": [
                "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline",
                "AcDbArc", "AcDbCircle", "AcDbText", "AcDbMText",
                "AcDbBlockReference", "AcDbDimension", "AcDbHatch", "AcDbTable",
                "Layer", "Linetype", "TextStyle", "DimStyle", "Layout", "Viewport", "Xref",
            ],
        }
