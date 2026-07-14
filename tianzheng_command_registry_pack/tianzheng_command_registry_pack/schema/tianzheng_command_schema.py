from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Domain = Literal["plumbing", "hvac", "architecture", "electrical", "generic"]
DangerLevel = Literal["low", "sandbox_safe", "review", "dangerous", "forbidden"]


@dataclass(frozen=True)
class CommandSafety:
    danger_level: DangerLevel
    allow_dry_run: bool = True
    allow_sandbox: bool = False
    allow_production: bool = False
    requires_visual_review: bool = True
    notes: str = ""


@dataclass(frozen=True)
class CommandValidationStatus:
    source_status: str = "unknown"
    dry_run: str = "not_started"
    sandbox: str = "not_started"
    production: str = "forbidden"


@dataclass(frozen=True)
class TianzhengCommand:
    id: str
    domain: Domain
    module: str
    label_zh: str
    primary_command: str
    aliases: list[str] = field(default_factory=list)
    all_invocation_names: list[str] = field(default_factory=list)
    category: str = "misc"
    expected_inputs: list[dict[str, Any]] = field(default_factory=list)
    interactive: bool = True
    creates_or_edits: list[str] = field(default_factory=list)
    safety: CommandSafety = field(default_factory=lambda: CommandSafety("review"))
    validation_status: CommandValidationStatus = field(default_factory=CommandValidationStatus)
    source_ids: list[str] = field(default_factory=list)
    notes: str = ""


def command_from_dict(data: dict[str, Any]) -> TianzhengCommand:
    safety = CommandSafety(**data["safety"])
    validation = CommandValidationStatus(**data.get("validation_status", {}))
    return TianzhengCommand(
        id=data["id"],
        domain=data["domain"],
        module=data.get("module", ""),
        label_zh=data["label_zh"],
        primary_command=data["primary_command"],
        aliases=data.get("aliases", []),
        all_invocation_names=data.get("all_invocation_names", []),
        category=data.get("category", "misc"),
        expected_inputs=data.get("expected_inputs", []),
        interactive=data.get("interactive", True),
        creates_or_edits=data.get("creates_or_edits", []),
        safety=safety,
        validation_status=validation,
        source_ids=data.get("source_ids", []),
        notes=data.get("notes", ""),
    )
