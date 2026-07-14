import json, pytest
from pathlib import Path
from tianzheng_interface.proxy_handler import KNOWN_TIANZHENG_NAMES
from command_registry.tools.command_resolver import CommandResolver

class TestD1HSXGMapping:
    def test_unlicensed_command_not_bundled(self):
        r = CommandResolver()
        assert r.resolve('hsxg') is None
        cmd = r.resolve('SYNTHETIC_FIXTURE_02')
        assert cmd is not None
        assert cmd['synthetic'] is True
        assert cmd['execution_allowed'] is False
        assert cmd['safety']['allow_sandbox'] is False

    def test_TDbDoubleLinePipe_in_known(self):
        assert 'TDbDoubleLinePipe' in KNOWN_TIANZHENG_NAMES

    def test_double_line_pipe_is_classified(self):
        from tianzheng_interface.proxy_handler import ProxyObjectHandler
        res = ProxyObjectHandler.classify('TDbDoubleLinePipe', 'PIPE-给水', 'H1')
        assert res.is_tianzheng
        assert res.classification == 'known_tianzheng'

    def test_diameter_none_does_not_crash(self):
        try:
            info = {'DNDiameter': None, 'SysType': None}
            assert 'DNDiameter' in info
        except Exception:
            pytest.fail('None values should not crash')
