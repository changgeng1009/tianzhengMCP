from __future__ import annotations

from .disabled_backend import DisabledBackend
from .models import BackendCapabilities


class TianzhengOfficialApiBackend(DisabledBackend):
    """未来天正官方 API 的禁用契约骨架，不伪造任何创建能力。"""

    backend_id = "tianzheng_api"
    backend_version = "contract-v1"

    def get_capabilities(self) -> BackendCapabilities:
        result = super().get_capabilities()
        result.capability_evidence = {
            "official_api_detected": "false",
            "execution_allowed": "false",
            "create_tdb_pipe": "future contract only",
            "create_tdb_valve": "future contract only",
            "create_tdb_fitting": "future contract only",
            "create_tianzheng_water_equipment": "future contract only",
        }
        return result
