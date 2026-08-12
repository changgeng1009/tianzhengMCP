"""Persistence and idempotency verdicts for native Tianzheng pipes.

Pure functions over snapshots, so the rules that decide "did this object survive the round
trip?" and "did the replay create a duplicate?" can be tested without AutoCAD or Tianzheng.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mcp_nextgen.s8.native_identity import PROXY_CLASS_PREFIXES, is_proxy

#: Structured failure codes, mirroring TianzhengErrorCodes on the plugin side.
PIPE_NOT_FOUND = "TIANZHENG_PIPE_NOT_FOUND"
NATIVE_IDENTITY_MISMATCH = "TIANZHENG_PIPE_NATIVE_IDENTITY_MISMATCH"
PROPERTY_UNAVAILABLE = "TIANZHENG_PIPE_PROPERTY_UNAVAILABLE"
SAVE_FAILED = "TIANZHENG_PIPE_SAVE_FAILED"
REOPEN_FAILED = "TIANZHENG_PIPE_REOPEN_FAILED"
PERSISTENCE_FAILED = "TIANZHENG_PIPE_PERSISTENCE_FAILED"
IDEMPOTENCY_CONFLICT = "TIANZHENG_PIPE_IDEMPOTENCY_CONFLICT"

#: Marker used when a property has no readable route on the current surface.
NOT_READABLE = "NOT_READABLE_WITH_CURRENT_SURFACE"

DEFAULT_TOLERANCE = 1e-6


def _get(snapshot: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in snapshot:
            return snapshot[name]
    return default


def build_signature(snapshot: Mapping[str, Any],
                    tolerance: float = DEFAULT_TOLERANCE) -> dict[str, Any]:
    """Minimum identity of a pipe: native class plus geometry.

    Readable properties join the signature only when they were actually readable — an
    unavailable property is recorded as such rather than folded in as a null that would
    silently compare equal to another null.
    """
    properties = _get(snapshot, "properties", "Properties", default={}) or {}
    readable: dict[str, Any] = {}
    unavailable: list[str] = []
    for name in ("diameter", "system", "elevation"):
        entry = properties.get(name)
        if not isinstance(entry, Mapping):
            unavailable.append(name)
            continue
        if entry.get("source") == NOT_READABLE or entry.get("value") is None:
            unavailable.append(name)
        else:
            readable[name] = entry.get("value")

    return {
        "native_runtime_class": _get(snapshot, "runtime_class", "RuntimeClass", default=""),
        "start": _get(snapshot, "start", "Start"),
        "end": _get(snapshot, "end", "End"),
        "geometry_tolerance": tolerance,
        "readable_properties": readable,
        "unavailable_properties": unavailable,
    }


def _points_match(a: Sequence[float] | None, b: Sequence[float] | None, tolerance: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if len(a) != len(b):
        return False
    return all(abs(float(x) - float(y)) <= tolerance for x, y in zip(a, b))


def compare_roundtrip(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Decide whether the pipe survived save -> close -> reopen as a native object."""
    class_before = _get(before, "runtime_class", "RuntimeClass", default="")
    class_after = _get(after, "runtime_class", "RuntimeClass", default="")
    handle_before = _get(before, "primary_handle", "PrimaryHandle", "handle", default="")
    handle_after = _get(after, "primary_handle", "PrimaryHandle", "handle", default="")

    sig_before = build_signature(before, tolerance)
    sig_after = build_signature(after, tolerance)

    reasons: list[str] = []
    error_code: str | None = None

    if not class_after:
        reasons.append("no object found after reopen")
        error_code = PIPE_NOT_FOUND
    elif is_proxy(class_after):
        # A proxy means the defining module was absent in the session that read it back.
        # That is an environment problem, not proof the object was destroyed.
        reasons.append(
            f"object came back as {class_after}: the Tianzheng module was not loaded in the "
            "reading session, so this is not a valid persistence result")
        error_code = NATIVE_IDENTITY_MISMATCH
    elif class_after != class_before:
        reasons.append(f"runtime class changed {class_before} -> {class_after}")
        error_code = NATIVE_IDENTITY_MISMATCH

    geometry_preserved = (
        _points_match(sig_before["start"], sig_after["start"], tolerance)
        and _points_match(sig_before["end"], sig_after["end"], tolerance)
    )
    if not geometry_preserved:
        reasons.append("geometry differs after reopen")
        error_code = error_code or PERSISTENCE_FAILED

    # Only properties that were readable on BOTH sides can be compared.
    comparable = set(sig_before["readable_properties"]) & set(sig_after["readable_properties"])
    property_mismatches = [
        name for name in sorted(comparable)
        if sig_before["readable_properties"][name] != sig_after["readable_properties"][name]
    ]
    if property_mismatches:
        reasons.append(f"readable properties changed: {', '.join(property_mismatches)}")
        error_code = error_code or PERSISTENCE_FAILED

    handle_stable = bool(handle_before) and handle_before == handle_after
    native_preserved = not reasons

    return {
        "native_class_before": class_before,
        "native_class_after": class_after,
        "handle_before": handle_before,
        "handle_after": handle_after,
        "handle_stable": handle_stable,
        "geometry_before": {"start": sig_before["start"], "end": sig_before["end"],
                            "length": _get(before, "length", "Length")},
        "geometry_after": {"start": sig_after["start"], "end": sig_after["end"],
                           "length": _get(after, "length", "Length")},
        "geometry_preserved": geometry_preserved,
        "signature_before": sig_before,
        "signature_after": sig_after,
        "properties_compared": sorted(comparable),
        "property_mismatches": property_mismatches,
        "properties_not_comparable": sorted(
            set(sig_before["unavailable_properties"]) | set(sig_after["unavailable_properties"])),
        "native_identity_preserved": native_preserved,
        "error_code": error_code,
        "reasons": reasons or ["native class, geometry and readable properties all match"],
    }


def evaluate_replay(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    replay_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Decide whether replaying the same idempotency key duplicated anything.

    Both the pipe and its related fittings are counted: a replay that left the pipe count
    alone but doubled the fittings would still be a broken idempotency guarantee.
    """
    pipe_before = int(_get(before, "pipe_count", "PipeCount", default=0) or 0)
    pipe_after = int(_get(after, "pipe_count", "PipeCount", default=0) or 0)
    fitting_before = int(_get(before, "fitting_count", "FittingCount", default=0) or 0)
    fitting_after = int(_get(after, "fitting_count", "FittingCount", default=0) or 0)

    status = str(_get(replay_result, "status", "Status", default="") or "")
    duplicate = pipe_after > pipe_before or fitting_after > fitting_before

    accepted = status in {"already_applied", "equivalent"}
    reasons: list[str] = []
    if duplicate:
        reasons.append(
            f"replay created duplicates: pipes {pipe_before}->{pipe_after}, "
            f"fittings {fitting_before}->{fitting_after}")
    if not accepted:
        reasons.append(f"replay status was {status!r}, expected already_applied or equivalent")

    return {
        "pipe_count_before": pipe_before,
        "pipe_count_after": pipe_after,
        "fitting_count_before": fitting_before,
        "fitting_count_after": fitting_after,
        "replay_status": status,
        "duplicate_created": duplicate,
        "idempotent": (not duplicate) and accepted,
        "error_code": IDEMPOTENCY_CONFLICT if (duplicate or not accepted) else None,
        "reasons": reasons or ["replay was recognised and created nothing new"],
    }


__all__ = [
    "PROXY_CLASS_PREFIXES", "NOT_READABLE", "DEFAULT_TOLERANCE",
    "PIPE_NOT_FOUND", "NATIVE_IDENTITY_MISMATCH", "PROPERTY_UNAVAILABLE",
    "SAVE_FAILED", "REOPEN_FAILED", "PERSISTENCE_FAILED", "IDEMPOTENCY_CONFLICT",
    "build_signature", "compare_roundtrip", "evaluate_replay",
]
