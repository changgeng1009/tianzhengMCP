"""Native-object identity rules for the S8 Tianzheng backend.

The point of this module is to make "is it really a native Tianzheng object?" a decision
with explicit, testable rules rather than a judgement call made while staring at a screen.
Everything here is pure: it takes database snapshots and returns a verdict, so it can be
exercised without AutoCAD or Tianzheng running.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: Ordinary AutoCAD entities. Creating one of these NEVER counts as native success -
#: faking a Tianzheng object with a line or polyline is exactly what S8 forbids.
ORDINARY_CLASSES = frozenset({
    "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline",
    "AcDbCircle", "AcDbArc", "AcDbSpline", "AcDbBlockReference",
    "AcDbMText", "AcDbText", "AcDbSolid", "AcDbHatch",
})

#: A proxy/zombie means the real class was NOT available - the object is a placeholder,
#: not a live native object, so it cannot prove native identity either.
PROXY_CLASS_PREFIXES = ("AcDbProxy", "AcDbZombie")

#: A genuine Tianzheng database object must ultimately derive from AcDbObject.
REQUIRED_ANCESTOR = "AcDbObject"


def _handle(obj: Mapping[str, Any]) -> str:
    return str(obj.get("handle") or obj.get("Handle") or "")


def _runtime_class(obj: Mapping[str, Any]) -> str:
    return str(obj.get("runtime_class") or obj.get("RuntimeClass") or "")


def _ancestry(obj: Mapping[str, Any]) -> list[str]:
    raw = obj.get("ancestry") or obj.get("Ancestry") or []
    return [str(a) for a in raw]


def diff_objects(
    before: Iterable[Mapping[str, Any]],
    after: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Objects present after but not before, matched on database handle.

    Handles are stable within a drawing, which makes them the right identity key; object
    ids are pointers and are not comparable across a scan boundary.
    """
    seen = {_handle(o) for o in before if _handle(o)}
    fresh: list[dict[str, Any]] = []
    for obj in after:
        handle = _handle(obj)
        if not handle or handle in seen:
            continue
        fresh.append(dict(obj))
    return fresh


def is_proxy(runtime_class: str) -> bool:
    return runtime_class.startswith(PROXY_CLASS_PREFIXES)


def classify(obj: Mapping[str, Any], target_class: str) -> tuple[bool, str]:
    """Decide whether one object satisfies native identity, with the reason."""
    runtime_class = _runtime_class(obj)
    if not runtime_class:
        return False, "no runtime class reported"
    if is_proxy(runtime_class):
        return False, f"{runtime_class} is a proxy/zombie, not a live native object"
    if runtime_class in ORDINARY_CLASSES:
        return False, f"{runtime_class} is an ordinary AutoCAD entity"
    if runtime_class != target_class:
        return False, f"runtime class is {runtime_class}, not {target_class}"
    if REQUIRED_ANCESTOR not in _ancestry(obj):
        return False, f"{runtime_class} does not derive from {REQUIRED_ANCESTOR}"
    return True, "runtime class matches and derives from AcDbObject"


def confirm_native_identity(
    new_objects: Sequence[Mapping[str, Any]],
    target_class: str = "TDbPipe",
) -> dict[str, Any]:
    """Verdict over the whole set of newly created objects.

    Tianzheng creates a pipe together with nodes and helper objects, so the set is
    evaluated as a set: the presence of extra objects is expected and is not a failure,
    but at least one object must genuinely BE the target class.
    """
    matches: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for obj in new_objects:
        ok, reason = classify(obj, target_class)
        record = {
            "handle": _handle(obj),
            "runtime_class": _runtime_class(obj),
            "dxf_name": str(obj.get("dxf_name") or obj.get("DxfName") or ""),
            "reason": reason,
        }
        (matches if ok else rejected).append(record)

    confirmed = len(matches) > 0
    if confirmed:
        summary = f"{len(matches)} object(s) confirmed as {target_class}"
    elif not new_objects:
        summary = "no new objects were created"
    else:
        summary = f"no new object had runtime class {target_class}"

    return {
        "native_identity_confirmed": confirmed,
        "target_class": target_class,
        "match_count": len(matches),
        "matches": matches,
        "rejected": rejected,
        "companion_classes": sorted({r["runtime_class"] for r in rejected if r["runtime_class"]}),
        "summary": summary,
    }


def properties_actually_read(obj: Mapping[str, Any]) -> dict[str, Any]:
    """Only values the object itself reported. Absent values stay absent.

    This deliberately does not fall back to the creation request: echoing a requested
    diameter back as if it had been read would make the evidence worthless.
    """
    out: dict[str, Any] = {}
    for key, alias in (("start_point", "StartPoint"), ("end_point", "EndPoint"), ("length", "Length")):
        value = obj.get(key, obj.get(alias))
        if value is not None:
            out[key] = value
    note = obj.get("property_read_note") or obj.get("PropertyReadNote")
    if note:
        out["note"] = note
    out["not_readable_from_managed_code"] = [
        name for name in ("diameter", "system", "elevation") if name not in out
    ]
    return out
