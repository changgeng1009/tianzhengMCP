"""天正给排水接口层 — Proxy / Custom Object 处理器

Phase 1: 纯基于 ObjectName / Layer / Handle 的数据分类。
不访问真实 COM 对象，不导入 win32com。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 已知天正对象 ObjectName
KNOWN_TIANZHENG_NAMES = frozenset({
    "TDbPipe",
    "TDbPipeValve",
    "TDbPipeFitting",
    "TDbDimension2",
    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",
    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",
})

# 基础 AutoCAD 对象 ObjectName 前缀
BASIC_CAD_PREFIXES = frozenset({
    "AcDbLine",
    "AcDbPolyline",
    "AcDb2dPolyline",
    "AcDb3dPolyline",
    "AcDbCircle",
    "AcDbArc",
    "AcDbText",
    "AcDbMText",
    "AcDbBlockReference",
    "AcDbDimension",
    "AcDbRotatedDimension",
    "AcDbAlignedDimension",
    "AcDbRadialDimension",
    "AcDbDiametricDimension",
})

# 可疑似为天正的关键词 (在 ObjectName 中出现时归类为候选)
TIANZHENG_SUSPICIOUS_KEYWORDS = frozenset({
    "tdb", "tpipe", "tdrain", "tangent", "twt", "tch",
})


@dataclass
class ProxyClassification:
    """Proxy 对象分类结果。"""
    handle: str = ""
    object_name: str = ""
    layer: str = ""
    classification: str = "unknown_custom"
    classification_reason: str = ""
    is_tianzheng: bool = False
    is_basic_cad: bool = False
    is_modifiable: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "object_name": self.object_name,
            "layer": self.layer,
            "classification": self.classification,
            "classification_reason": self.classification_reason,
            "is_tianzheng": self.is_tianzheng,
            "is_basic_cad": self.is_basic_cad,
            "is_modifiable": self.is_modifiable,
            "warnings": list(self.warnings),
        }


class ProxyObjectHandler:
    """Proxy / Custom Object 分类处理器。

    Phase 1: 只做基于 ObjectName 的纯数据分类。
    - 不访问 COM 对象
    - 不导入 win32com
    - is_modifiable() 始终返回 False
    """

    @staticmethod
    def classify(
        object_name: str,
        layer: str = "",
        handle: str = "",
    ) -> ProxyClassification:
        """根据 ObjectName 归类对象类型。

        Returns:
            ProxyClassification with classification in:
            - known_tianzheng (TDbPipe, TDbPipeValve, ...)
            - basic_cad (AcDbLine, AcDbPolyline, ...)
            - unknown_tianzheng_candidate (含 tdb/tpipe/... 关键词)
            - unknown_proxy (其他非 AcDb 对象)
            - unknown_custom (无法归类)
        """
        name = str(object_name or "").strip()
        layer_str = str(layer or "")
        handle_str = str(handle or "")
        warnings: list[str] = []

        result = ProxyClassification(
            handle=handle_str,
            object_name=name,
            layer=layer_str,
            is_tianzheng=False,
            is_basic_cad=False,
            is_modifiable=False,
        )

        if not name:
            result.classification = "unknown_custom"
            result.classification_reason = "ObjectName is empty"
            result.warnings = warnings
            return result

        # 1. 精确匹配已知天正类型
        if name in KNOWN_TIANZHENG_NAMES:
            result.classification = "known_tianzheng"
            result.classification_reason = f"ObjectName matches known Tianzheng type: {name}"
            result.is_tianzheng = True
            result.warnings = warnings
            return result

        # 2. 前缀匹配基础 AutoCAD 类型
        for prefix in BASIC_CAD_PREFIXES:
            if name.startswith(prefix):
                result.classification = "basic_cad"
                result.classification_reason = (
                    f"ObjectName matches basic AutoCAD type prefix: {prefix}"
                )
                result.is_basic_cad = True
                result.warnings = warnings
                return result

        # 3. 含天正可疑关键词
        lowered = name.lower()
        for keyword in TIANZHENG_SUSPICIOUS_KEYWORDS:
            if keyword in lowered:
                result.classification = "unknown_tianzheng_candidate"
                result.classification_reason = (
                    f"ObjectName contains Tianzheng keyword: {keyword}"
                )
                warnings.append(
                    f"对象 {name} 含天正关键词 {keyword}，但不在已知类型列表中"
                )
                result.warnings = warnings
                return result

        # 4. 以 AcDb 开头但不在基础列表中
        if name.startswith("AcDb"):
            result.classification = "unknown_custom"
            result.classification_reason = (
                f"AcDb object not in basic CAD list: {name}"
            )
            result.warnings = warnings
            return result

        # 5. 其他无法归类
        result.classification = "unknown_proxy"
        result.classification_reason = (
            f"ObjectName not recognized: {name}"
        )
        warnings.append(f"无法识别的对象类型: {name}")
        result.warnings = warnings
        return result

    @staticmethod
    def is_modifiable(
        object_name: str = "",
        classification: str = "",
    ) -> bool:
        """Phase 1: 判断对象是否可修改。

        当前阶段始终返回 False。
        """
        return False

    @staticmethod
    def classify_batch(
        entities: list[dict[str, Any]],
    ) -> list[ProxyClassification]:
        """批量分类。"""
        results: list[ProxyClassification] = []
        for entity in entities:
            obj_name = str(entity.get("object_name", "") or entity.get("ObjectName", ""))
            obj_layer = str(entity.get("layer", "") or entity.get("Layer", ""))
            obj_handle = str(entity.get("handle", "") or entity.get("Handle", ""))
            results.append(
                ProxyObjectHandler.classify(obj_name, obj_layer, obj_handle)
            )
        return results
# ════════════════════════════════════════════════════════════════
# Phase M2 增强: 自动发现 + 置信度评分
# ════════════════════════════════════════════════════════════════

# 扩展已知天正类型 (M2: 暖通 + 电气候选)
EXTENDED_TIANZHENG_NAMES = frozenset({
    "TDbPipe", "TDbPipeValve", "TDbPipeFitting", "TDbDimension2",
    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",
    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",
    "TDbAirDuct", "TDbAirDuctValve", "TDbAirDuctFitting",
    "TDbSprinkler", "TDbHeater", "TDbCooler",
    "TDbCableTray", "TDbWire", "TDbLight",
})

# 属性探测提示词 (用于识别未知天正类型)
DISCOVERY_PATTERNS = {
    "TDb": {"confidence": 0.8, "hint": "天正对象前缀"},
    "TCH_": {"confidence": 0.7, "hint": "天正旧版对象前缀"},
    "_TCH": {"confidence": 0.5, "hint": "可能为天正旧版对象后缀"},
}


class ProxyDiscovery:
    """Phase M2: 未知天正类型的自动发现引擎。"""

    @staticmethod
    def discover(object_name: str, properties: dict[str, Any] | None = None) -> ProxyClassification:
        """尝试自动发现未知类型的分类。

        基于:
        1. ObjectName 模式匹配
        2. 属性键名分析 (如包含 DNDiameter/Radius/PipeType 等水管属性)
        3. 扩展已知类型列表
        """
        result = ProxyObjectHandler.classify(
            object_name, layer=properties.get("Layer", "") if properties else "",
            handle=properties.get("Handle", "") if properties else "",
        )

        # 如果已经是已知类型，直接返回
        if result.classification in ("known_tianzheng", "basic_cad"):
            return result

        # 尝试扩展匹配
        name = str(object_name or "").strip()
        lowered = name.lower()

        # 1. 扩展已知列表精确匹配
        if name in EXTENDED_TIANZHENG_NAMES:
            result.classification = "known_tianzheng"
            result.classification_reason = f"ObjectName matches extended Tianzheng type: {name}"
            result.is_tianzheng = True
            return result

        # 2. 模式匹配
        for prefix, info in DISCOVERY_PATTERNS.items():
            if lowered.startswith(prefix.lower()):
                result.classification = "unknown_tianzheng_candidate"
                result.classification_reason = (
                    f"ObjectName 匹配模式 {prefix}: {info['hint']} "
                    f"(置信度 {info['confidence']})"
                )
                result.is_tianzheng = True
                if info["confidence"] < 0.7:
                    result.warnings.append(
                        f"低置信度发现: {name} 匹配 {prefix}，需人工确认"
                    )
                return result

        # 3. 属性探测定
        if properties:
            props = ProxyDiscovery._analyze_properties(properties)
            if props["tianzheng_score"] > 0.5:
                result.classification = "unknown_tianzheng_candidate"
                result.classification_reason = (
                    f"属性分析: 天正得分 {props['tianzheng_score']:.2f}, "
                    f"命中属性: {props['matched_props']}"
                )
                result.is_tianzheng = True

        return result

    @staticmethod
    def _analyze_properties(properties: dict[str, Any]) -> dict[str, Any]:
        """分析对象属性中的天正特征。"""
        tianzheng_keys = {
            "DNDiameter", "Radius", "Diameter", "PipeDN", "DN",
            "SysType", "SystemType", "SElevation", "EElevation",
            "ModelType", "Label", "SysLabel", "DrawLabel",
            "DuctWidth", "DuctHeight", "AirFlow", "CableType",
        }
        all_keys = {str(k) for k in properties.keys()}
        matched = all_keys & tianzheng_keys
        score = len(matched) / max(len(tianzheng_keys), 1) if matched else 0.0
        return {
            "tianzheng_score": score,
            "matched_props": list(matched),
            "total_props": len(all_keys),
        }

    @staticmethod
    def classify_with_confidence(
        object_name: str, properties: dict[str, Any] | None = None
    ) -> tuple[ProxyClassification, float]:
        """分类并返回置信度评分。"""
        result = ProxyDiscovery.discover(object_name, properties)
        if result.classification == "known_tianzheng":
            return result, 1.0
        if result.classification == "basic_cad":
            return result, 1.0
        if result.classification == "unknown_tianzheng_candidate":
            return result, 0.5
        return result, 0.0
