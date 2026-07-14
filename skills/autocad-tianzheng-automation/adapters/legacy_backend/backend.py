from typing import Any, Mapping

from runtime.contracts import ICadBackend
from runtime.errors import UnsafeOperation
from runtime.planner import build_offline_plan


class OfflineBackend(ICadBackend):
    name = "offline"

    def build_plan(self, manifest: Mapping[str, Any]):
        return build_offline_plan(manifest)


class LegacyAdapter(ICadBackend):
    name = "legacy-contract-disabled"
    support_level = "DISABLED_CONTRACT_ONLY"
    execution_allowed = False

    def build_plan(self, manifest: Mapping[str, Any]):
        return {
            "status": self.support_level,
            "backend": self.name,
            "execution_allowed": False,
            "reason": "LegacyAdapter 仅保留合同，本阶段禁止执行",
        }

    def execute(self, *_):
        raise UnsafeOperation("LegacyAdapter=DISABLED_CONTRACT_ONLY")


class LegacyScriptBackend(ICadBackend):
    name = "legacy-script"

    def build_plan(self, manifest: Mapping[str, Any]):
        plan = build_offline_plan(manifest)
        plan.update({"backend": self.name, "execution_allowed": False})
        return plan

    def execute(self, *_):
        raise UnsafeOperation("离线 Skill 阶段不执行 Legacy Script")


class LegacyComBackend(LegacyScriptBackend):
    name = "legacy-com"

    def execute(self, *_):
        raise UnsafeOperation("离线 Skill 阶段禁止连接 AutoCAD COM")
