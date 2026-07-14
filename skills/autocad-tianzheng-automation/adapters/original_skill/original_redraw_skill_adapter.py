from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from runtime.errors import UnsafeOperation


class OriginalRedrawSkillAdapter:
    """只映射原始入口；不导入、修改或自动执行原 Skill 脚本。"""

    DEFAULT_ORIGINAL_ROOT = Path(
        "C:/Users/example-user/.agents/skills/autocad-dwg-redraw-skill-main/"
        "autocad-dwg-redraw-skill-main/skills/autocad-dwg-redraw"
    )
    WORKFLOW_MAP = {
        "redraw_from_reference": "04_redraw",
        "analyze_reference": "02_reference_analysis",
        "visual_review": "08_visual_review",
        "compare_drawings": "08_visual_review",
    }

    def locate(self, root: Path | None = None) -> Path:
        candidate = root or self.DEFAULT_ORIGINAL_ROOT
        if not (candidate / "SKILL.md").is_file():
            raise FileNotFoundError(candidate / "SKILL.md")
        return candidate

    def to_manifest_patch(self, task: str) -> dict[str, Any]:
        if task not in self.WORKFLOW_MAP:
            raise ValueError(f"未映射的原始任务: {task}")
        return {
            "runtime_mode": "plain_autocad",
            "product": "autocad",
            "workflow": self.WORKFLOW_MAP[task],
            "preferred_backend": "offline",
            "production_allowed": False,
            "visual_review_required": True,
        }

    def execute_script(self, _: Mapping[str, Any]) -> None:
        raise UnsafeOperation("兼容层默认隔离原始脚本；必须经新安全门和显式后端调用")

