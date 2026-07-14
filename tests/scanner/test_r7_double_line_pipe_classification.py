import pytest
from tianzheng_interface.proxy_handler import ProxyObjectHandler, ProxyClassification, KNOWN_TIANZHENG_NAMES

class TestDoubleLinePipeClass:
    def test_known_names(self):
        assert 'TDbDoubleLinePipe' in KNOWN_TIANZHENG_NAMES
        assert 'TDbPump' in KNOWN_TIANZHENG_NAMES
    def test_classify_dlp(self):
        r = ProxyObjectHandler.classify('TDbDoubleLinePipe', 'PIPE-给水', 'H1')
        assert r.classification == 'known_tianzheng'
        assert r.is_tianzheng is True
    def test_classify_pump(self):
        r = ProxyObjectHandler.classify('TDbPump', '0', 'H2')
        assert r.classification == 'known_tianzheng'
    def test_unknown_still_works(self):
        r = ProxyObjectHandler.classify('SomeRandomType', '0', 'H4')
        assert r.classification != 'known_tianzheng'
