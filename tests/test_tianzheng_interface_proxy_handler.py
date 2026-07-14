"""测试 tianzheng_interface.proxy_handler — 纯数据分类。

Phase 1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
- 不访问 target.dwg
"""

import pytest
from tianzheng_interface.proxy_handler import (
    ProxyObjectHandler,
    ProxyClassification,
    KNOWN_TIANZHENG_NAMES,
)


class TestKnownTianzhengTypes:
    def test_tdbpipe(self):
        result = ProxyObjectHandler.classify("TDbPipe")
        assert result.classification == "known_tianzheng"
        assert result.is_tianzheng is True
        assert result.is_basic_cad is False

    def test_tdbpipevalve(self):
        result = ProxyObjectHandler.classify("TDbPipeValve")
        assert result.classification == "known_tianzheng"

    def test_tdbpipefitting(self):
        result = ProxyObjectHandler.classify("TDbPipeFitting")
        assert result.classification == "known_tianzheng"

    def test_tdbdimension2(self):
        result = ProxyObjectHandler.classify("TDbDimension2")
        assert result.classification == "known_tianzheng"


class TestBasicCADTypes:
    def test_acdbline(self):
        result = ProxyObjectHandler.classify("AcDbLine")
        assert result.classification == "basic_cad"
        assert result.is_basic_cad is True
        assert result.is_tianzheng is False

    def test_acdbpolyline(self):
        result = ProxyObjectHandler.classify("AcDbPolyline")
        assert result.classification == "basic_cad"

    def test_acdbcircle(self):
        result = ProxyObjectHandler.classify("AcDbCircle")
        assert result.classification == "basic_cad"

    def test_acdbarc(self):
        result = ProxyObjectHandler.classify("AcDbArc")
        assert result.classification == "basic_cad"

    def test_acdbtext(self):
        result = ProxyObjectHandler.classify("AcDbText")
        assert result.classification == "basic_cad"

    def test_acdbmtext(self):
        result = ProxyObjectHandler.classify("AcDbMText")
        assert result.classification == "basic_cad"

    def test_acdbblockreference(self):
        result = ProxyObjectHandler.classify("AcDbBlockReference")
        assert result.classification == "basic_cad"

    def test_acdbdimension(self):
        result = ProxyObjectHandler.classify("AcDbRotatedDimension")
        assert result.classification == "basic_cad"


class TestUnknownTypes:
    def test_empty_name(self):
        result = ProxyObjectHandler.classify("")
        assert result.classification == "unknown_custom"

    def test_tianzheng_candidate(self):
        result = ProxyObjectHandler.classify("TDbUnknownThing")
        assert result.classification == "unknown_tianzheng_candidate"

    def test_unknown_acdb(self):
        result = ProxyObjectHandler.classify("AcDbWeirdShape")
        assert result.classification == "unknown_custom"

    def test_completely_unknown(self):
        result = ProxyObjectHandler.classify("SomeRandomType")
        assert result.classification == "unknown_proxy"
        assert len(result.warnings) > 0


class TestIsModifiable:
    def test_always_false_phase1(self):
        assert ProxyObjectHandler.is_modifiable("TDbPipe") is False
        assert ProxyObjectHandler.is_modifiable("AcDbLine") is False
        assert ProxyObjectHandler.is_modifiable("") is False
        assert ProxyObjectHandler.is_modifiable() is False

    def test_all_known_types_not_modifiable(self):
        for name in KNOWN_TIANZHENG_NAMES:
            assert ProxyObjectHandler.is_modifiable(name) is False, (
                f"{name} should not be modifiable in Phase 1"
            )


class TestBatchClassify:
    def test_empty_list(self):
        results = ProxyObjectHandler.classify_batch([])
        assert results == []

    def test_mixed_entities(self):
        entities = [
            {"object_name": "TDbPipe", "layer": "PIPE-给水", "handle": "A1"},
            {"object_name": "AcDbLine", "layer": "0", "handle": "B2"},
            {"object_name": "WeirdObject", "layer": "UNKNOWN", "handle": "C3"},
        ]
        results = ProxyObjectHandler.classify_batch(entities)
        assert len(results) == 3
        assert results[0].classification == "known_tianzheng"
        assert results[1].classification == "basic_cad"
        assert results[2].classification == "unknown_proxy"

    def test_handles_various_key_names(self):
        entities = [
            {"ObjectName": "TDbPipe", "Layer": "PIPE", "Handle": "H1"},
            {"object_name": "AcDbLine", "Layer": "0", "handle": "H2"},
        ]
        results = ProxyObjectHandler.classify_batch(entities)
        assert len(results) == 2
        assert results[0].classification == "known_tianzheng"
        assert results[1].classification == "basic_cad"


class TestProxyClassificationToDict:
    def test_to_dict(self):
        pc = ProxyClassification(
            handle="H001",
            object_name="TDbPipe",
            layer="PIPE",
            classification="known_tianzheng",
            classification_reason="matched",
            is_tianzheng=True,
        )
        d = pc.to_dict()
        assert d["handle"] == "H001"
        assert d["is_tianzheng"] is True
        assert d["is_modifiable"] is False


class TestNoRealCADAccess:
    """验证 Phase 1 安全性: 无 win32com 导入。"""

    def test_no_win32com(self):
        from tianzheng_interface import proxy_handler

        assert "win32com" not in proxy_handler.__dict__, "proxy_handler 不应导入 win32com"

    def test_no_pywin32(self):
        import sys
        assert "pywin32" not in sys.modules, "不应导入 pywin32"
