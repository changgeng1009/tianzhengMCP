"""S10 capability registry: what the Tianzheng native backend can ACTUALLY do.

The central idea is that three different facts get confused with one another, and S10 paid for
learning the difference one object family at a time:

    runtime_available          the RX class is registered in the live process
    manual_creation_available  a human can make one through Tianzheng's own UI
    automation_available       MCP can make one deterministically, without a human

A valve is the cautionary case: ``TDbPipeValve`` resolves, a human can place one, and every
attempt to drive FMFJ from managed code stalls in its interactive input surface. Reporting
that as "valve capability available" because the class exists would be a lie that only shows
up in a real drawing.

Only ``automation_available`` may turn into a usable public capability. The flat
``{name: status}`` snapshot the planner consumes is DERIVED from the family table below, so
the two can never drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_VERSION = "s10.1"

# --------------------------------------------------------------------------- statuses

#: Usable: the backend can really do this today, within the stated scope.
AVAILABLE_SANDBOX_MVP = "AVAILABLE_SANDBOX_MVP"

#: The thing is understood but no working implementation is exposed.
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

#: The capability NAME describes something that does not exist for this object family.
#: This is not "unfinished" - it is a category error, and saying NOT_IMPLEMENTED would
#: wrongly imply that finishing it is the plan.
NOT_APPLICABLE = "NOT_APPLICABLE"

#: Statuses that mean "you may actually use this". Mirrors s9.planner.USABLE_STATUSES.
USABLE_STATUSES = frozenset({AVAILABLE_SANDBOX_MVP, "IMPLEMENTED_BASELINE", "AVAILABLE"})

# --------------------------------------------------------------------------- capability names

CAP_PIPE_CREATE = "tianzheng_native_pipe_create"
CAP_PIPE_QUERY = "tianzheng_native_pipe_query"
CAP_PIPE_IDENTITY = "tianzheng_native_pipe_identity_validation"
CAP_PIPE_PERSISTENCE = "tianzheng_native_pipe_persistence"
CAP_PIPE_IDEMPOTENCY = "tianzheng_native_pipe_idempotency"

CAP_PUMP_CREATE = "tianzheng_native_pump_create"
CAP_EQUIPMENT_CREATE = "tianzheng_native_equipment_create"
CAP_EQUIPMENT_QUERY = "tianzheng_native_equipment_query"

CAP_ANNOTATION_CONTROL = "tianzheng_pipe_annotation_control"
CAP_DIAMETER_ANNOTATION = "tianzheng_pipe_diameter_annotation"

CAP_VALVE_CREATE = "tianzheng_native_valve_create"
CAP_FITTING_CREATE = "tianzheng_native_fitting_create"

#: Deliberately NOT_APPLICABLE rather than NOT_IMPLEMENTED. The settled S10.4 evidence is that
#: diameter annotation creates no DBObject at all, so there is no annotation entity to create.
CAP_ANNOTATION_CREATE = "tianzheng_native_annotation_create"

#: Equipment is a family, not a single object. A capability that is available for pumps says
#: nothing about water tanks, and the planner must consult this list rather than assume.
SUPPORTED_EQUIPMENT_TYPES: tuple[str, ...] = ("pump",)

#: Storage models a native "annotation" may use.
MODEL_A_SEPARATE_OBJECT = "MODEL_A_SEPARATE_OBJECT"
MODEL_B_PIPE_OWNED_STATE = "MODEL_B_PIPE_OWNED_STATE"

#: The XData application Tianzheng writes onto a TDbPipe when DGGJ annotates its diameter.
#: Measured, not guessed: absent before, present after, across three adapter-driven runs.
PIPE_LABEL_XDATA_APPLICATION = "TG_PIPELABEL_THICK_SHOW"


# --------------------------------------------------------------------------- interaction profile


class CommandInteractionProfile:
    """How a Tianzheng command asks for its input.

    This is adapter METADATA, recording what S10 measured. It is not a command-execution
    framework and nothing dispatches on it: its job is to stop the next adapter from reusing
    a driver that was already proven wrong for a given prompt shape.
    """

    #: An ordinary AutoCAD point prompt. A queued coordinate is read as a point.
    STANDARD_POINT = "STANDARD_POINT"

    #: An ordinary AutoCAD selection prompt that honours normal selection mechanisms.
    STANDARD_SELECTION = "STANDARD_SELECTION"

    #: A selection prompt Tianzheng services itself. Managed SelectionSets are ignored and a
    #: typed coordinate becomes a window corner rather than a pick.
    NATIVE_SELECTION = "NATIVE_SELECTION"

    #: The command holds the input device in its own loop (jig/sampler-like).
    INTERACTIVE_SAMPLER = "INTERACTIVE_SAMPLER"

    #: More than one of the above in sequence.
    MIXED = "MIXED"

    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CommandProfile:
    """One measured command, with the evidence that fixed its profile."""

    command: str
    label: str
    profile: str
    automatable: bool
    evidence: str
    termination: str = "not_established"

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command, "label": self.label, "profile": self.profile,
            "automatable": self.automatable, "evidence": self.evidence,
            "termination": self.termination,
        }


#: Every Tianzheng command S10 actually drove, and what it turned out to be.
COMMAND_PROFILES: dict[str, CommandProfile] = {
    "HZGX": CommandProfile(
        "HZGX", "绘制管线", CommandInteractionProfile.STANDARD_POINT, True,
        "two queued coordinates create one TDbPipe plus its endpoint fittings",
        termination="completes on its own"),
    "HZSB": CommandProfile(
        "HZSB", "绘制水泵", CommandInteractionProfile.MIXED, True,
        "a queued coordinate places the pump; the command then continues prompting, so the "
        "adapter appends an owned cancel",
        termination="owned document-queue cancel"),
    "DGGJ": CommandProfile(
        "DGGJ", "单管管径", CommandInteractionProfile.STANDARD_POINT, True,
        "a typed coordinate is accepted as the point; Tianzheng hit-tests it against the pipe "
        "itself, so the target must be framed in the current view first",
        termination="its own 退出 Enter-default, with a trailing cancel to absorb the "
                    "command-repeat that an Enter causes at an idle prompt"),
    "GJBZ": CommandProfile(
        "GJBZ", "管径标注", CommandInteractionProfile.NATIVE_SELECTION, False,
        "a managed SelectionSet was not consumed and a typed coordinate became a crossing-window "
        "corner; two matched probes exhausted",
        termination="not reached"),
    "FMFJ": CommandProfile(
        "FMFJ", "阀门附件", CommandInteractionProfile.INTERACTIVE_SAMPLER, False,
        "the command holds the input device in its own loop; queued input did not advance it. "
        "The profile names the OBSERVED behaviour, not a claim about which internal class "
        "implements it",
        termination="not reached"),
    "DXJT": CommandProfile(
        "DXJT", "多线绘制", CommandInteractionProfile.NATIVE_SELECTION, False,
        "selection-based, and it rejected TDbPipe outright - an object-family mismatch rather "
        "than an input-surface problem",
        termination="not reached"),
    "GXLJ": CommandProfile(
        "GXLJ", "管线连接", CommandInteractionProfile.NATIVE_SELECTION, False,
        "selection-based and blocked on a missing prerequisite capability",
        termination="not reached"),
}

#: Documented constraint, learned the hard way in S10.4.
EDITOR_COMMAND_IS_BLOCKING = (
    "Editor.Command blocks until the command it launched completes. A Tianzheng command that "
    "stops in its own input loop therefore never returns control, so code placed AFTER the "
    "call cannot terminate that same command. Adapters must drive such commands through the "
    "document queue instead. This is a constraint to respect, not a reason to introduce "
    "multi-threaded or arbitrary command machinery."
)


# --------------------------------------------------------------------------- object families


@dataclass(frozen=True)
class ObjectFamilyCapability:
    """The three-layer truth about one native object family."""

    family: str
    runtime_class: str
    dxf_name: str
    runtime_available: bool
    manual_creation_available: bool
    automation_available: bool
    public_capabilities: tuple[str, ...] = ()
    blocker: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "runtime_class": self.runtime_class,
            "dxf_name": self.dxf_name,
            "runtime_available": self.runtime_available,
            "manual_creation_available": self.manual_creation_available,
            "automation_available": self.automation_available,
            "public_capabilities": list(self.public_capabilities),
            "blocker": self.blocker,
            "note": self.note,
        }


OBJECT_FAMILIES: dict[str, ObjectFamilyCapability] = {
    "pipe": ObjectFamilyCapability(
        family="pipe", runtime_class="TDbPipe", dxf_name="TCH_PIPE",
        runtime_available=True, manual_creation_available=True, automation_available=True,
        public_capabilities=(CAP_PIPE_CREATE, CAP_PIPE_QUERY, CAP_PIPE_IDENTITY,
                             CAP_PIPE_PERSISTENCE, CAP_PIPE_IDEMPOTENCY),
        note="S8: creation, persistence and idempotency all verified end to end"),

    "valve": ObjectFamilyCapability(
        family="valve", runtime_class="TDbPipeValve", dxf_name="TCH_PIPEVALVE",
        runtime_available=True, manual_creation_available=True, automation_available=False,
        public_capabilities=(),
        blocker="BLOCKED_BY_INTERACTIVE_INPUT_SURFACE",
        note="the class resolves and a human can place one; FMFJ holds the input device in "
             "its own loop, so no deterministic automation exists"),

    "fitting": ObjectFamilyCapability(
        family="fitting", runtime_class="TDbPipeFitting", dxf_name="TCH_PIPEFITTING",
        runtime_available=True, manual_creation_available=True, automation_available=False,
        public_capabilities=(),
        blocker="ACTIVE_CREATION_NOT_AVAILABLE",
        note="endpoint fittings DO appear, but only as a side effect of HZGX creating a pipe. "
             "DXJT is an object-family mismatch and GXLJ needs a prerequisite capability that "
             "does not exist, so there is no way to insert a fitting deliberately"),

    "equipment_pump": ObjectFamilyCapability(
        family="equipment_pump", runtime_class="TDbPump", dxf_name="TCH_PUMP",
        runtime_available=True, manual_creation_available=True, automation_available=True,
        public_capabilities=(CAP_PUMP_CREATE, CAP_EQUIPMENT_CREATE, CAP_EQUIPMENT_QUERY),
        note="S10.3: HZSB adapter with an owned cancel. position is the only caller-controlled "
             "field; rotation, pump type, base size, inlet/outlet elevation and pump height "
             "are NOT exposed because they are not implemented"),

    "pipe_annotation": ObjectFamilyCapability(
        family="pipe_annotation", runtime_class="TDbPipe", dxf_name="TCH_PIPE",
        runtime_available=True, manual_creation_available=True, automation_available=True,
        public_capabilities=(CAP_ANNOTATION_CONTROL, CAP_DIAMETER_ANNOTATION),
        note="S10.4: MODEL_B_PIPE_OWNED_STATE. DGGJ creates no object; it writes XData "
             f"{PIPE_LABEL_XDATA_APPLICATION} onto the TDbPipe, which draws its own label. "
             "The runtime class named here is the CARRIER of the state, not an annotation class"),
}

#: The published capability table. Derived below so it cannot drift from OBJECT_FAMILIES.
_EXPLICIT_STATUSES: dict[str, str] = {
    CAP_VALVE_CREATE: NOT_IMPLEMENTED,
    CAP_FITTING_CREATE: NOT_IMPLEMENTED,
    CAP_ANNOTATION_CREATE: NOT_APPLICABLE,
}


def native_capability_registry() -> dict[str, str]:
    """The flat ``{capability: status}`` table, derived from the family table."""
    registry: dict[str, str] = {}
    for family in OBJECT_FAMILIES.values():
        if not family.automation_available:
            continue
        for name in family.public_capabilities:
            registry[name] = AVAILABLE_SANDBOX_MVP
    registry.update(_EXPLICIT_STATUSES)
    return registry


def capability_status(name: str) -> str:
    return native_capability_registry().get(name, NOT_IMPLEMENTED)


def is_usable(name: str) -> bool:
    return capability_status(name) in USABLE_STATUSES


def equipment_type_supported(equipment_type: str) -> bool:
    """Whether this specific equipment type can be created.

    ``tianzheng_native_equipment_create`` being available does NOT mean every equipment type
    works. Only pumps have an adapter; anything else must block rather than be quietly routed
    to the pump one.
    """
    return str(equipment_type).strip().lower() in SUPPORTED_EQUIPMENT_TYPES


def capability_report() -> dict[str, Any]:
    """Everything a caller needs to reason honestly about the native backend."""
    return {
        "schema_version": SCHEMA_VERSION,
        "capabilities": native_capability_registry(),
        "supported_equipment_types": list(SUPPORTED_EQUIPMENT_TYPES),
        "object_families": {k: v.to_dict() for k, v in OBJECT_FAMILIES.items()},
        "command_profiles": {k: v.to_dict() for k, v in COMMAND_PROFILES.items()},
        "annotation_storage_model": MODEL_B_PIPE_OWNED_STATE,
        "annotation_xdata_application": PIPE_LABEL_XDATA_APPLICATION,
        "known_constraints": {"editor_command_is_blocking": EDITOR_COMMAND_IS_BLOCKING},
    }


def merge_snapshot(raw: Mapping[str, Any] | None) -> dict[str, str]:
    """Overlay a live backend capability report onto the registry defaults.

    A live report may only ever make the picture MORE conservative in the sense that it is the
    authority for what this particular process supports; the registry supplies the names the
    planner knows about so an absent key never silently reads as "available".
    """
    snapshot = native_capability_registry()
    if not raw:
        return snapshot
    source = raw
    if "capabilities" in raw and isinstance(raw["capabilities"], Mapping):
        source = raw["capabilities"]
    for key, value in source.items():
        if isinstance(value, str):
            snapshot[str(key)] = value
        elif isinstance(value, bool):
            snapshot[str(key)] = AVAILABLE_SANDBOX_MVP if value else NOT_IMPLEMENTED
    return snapshot
