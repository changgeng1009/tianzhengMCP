"""S5 真实 AutoCAD 启动测试的显式门禁。

此文件本身不启动进程、不导入 COM，也不读取 CAD 文件。实际 Launcher/实体
闭环只能由受控集成运行器在登记当前 job 的 synthetic Sandbox 后调用。
"""

from __future__ import annotations

import os

import pytest


pytestmark = [
    pytest.mark.external_integration,
    pytest.mark.autocad_required,
    pytest.mark.com_required,
    pytest.mark.synthetic_cad,
]


def test_s5_real_autocad_launch_requires_explicit_integration_opt_in() -> None:
    if os.environ.get("CAD_S5_AUTOCAD_INTEGRATION") != "1":
        pytest.skip("未设置 CAD_S5_AUTOCAD_INTEGRATION=1；禁止真实 AutoCAD 集成")
    assert os.environ["CAD_S5_AUTOCAD_INTEGRATION"] == "1"
