"""Rules that decide whether a created object is genuinely a native Tianzheng object.

These run with AutoCAD and Tianzheng launch count = 0. They cover the decision logic only;
the real native creation itself can only be proven by the opt-in run against a live
Tianzheng session, and is deliberately NOT simulated here.
"""
from __future__ import annotations

import json

import pytest

from mcp_nextgen.s8.native_identity import (
    ORDINARY_CLASSES,
    classify,
    confirm_native_identity,
    diff_objects,
    is_proxy,
    properties_actually_read,
)

PIPE_ANCESTRY = [
    "TDbPipePrototype", "TDbCurveEntity", "AcDbCurve",
    "AcDbEntity", "AcDbObject", "AcGiDrawable", "AcRxObject",
]


def obj(handle, runtime_class, ancestry=None, **extra):
    return {
        "handle": handle,
        "runtime_class": runtime_class,
        "dxf_name": extra.pop("dxf_name", ""),
        "ancestry": ancestry if ancestry is not None else ["AcDbEntity", "AcDbObject"],
        **extra,
    }


# --------------------------------------------------------------- database diff

def test_diff_returns_only_objects_absent_before():
    before = [obj("1A", "AcDbLine"), obj("1B", "AcDbCircle")]
    after = [obj("1A", "AcDbLine"), obj("1B", "AcDbCircle"), obj("2F", "TDbPipe", PIPE_ANCESTRY)]

    fresh = diff_objects(before, after)

    assert [o["handle"] for o in fresh] == ["2F"]


def test_diff_is_empty_when_nothing_was_created():
    snapshot = [obj("1A", "AcDbLine")]
    assert diff_objects(snapshot, list(snapshot)) == []


def test_diff_ignores_objects_without_a_handle():
    # An unhandled record cannot be attributed to the creation, so it must not be
    # smuggled in as evidence.
    fresh = diff_objects([], [obj("", "TDbPipe", PIPE_ANCESTRY)])
    assert fresh == []


def test_diff_handles_deletions_without_reporting_them_as_new():
    before = [obj("1A", "AcDbLine"), obj("1B", "AcDbCircle")]
    after = [obj("1A", "AcDbLine")]
    assert diff_objects(before, after) == []


# ----------------------------------------------------------- identity decision

def test_expected_tdbpipe_is_confirmed():
    verdict = confirm_native_identity([obj("2F", "TDbPipe", PIPE_ANCESTRY, dxf_name="TCH_PIPE")])

    assert verdict["native_identity_confirmed"] is True
    assert verdict["match_count"] == 1
    assert verdict["matches"][0]["dxf_name"] == "TCH_PIPE"


@pytest.mark.parametrize("ordinary", sorted(ORDINARY_CLASSES))
def test_ordinary_entities_are_rejected(ordinary):
    verdict = confirm_native_identity([obj("2F", ordinary)])

    assert verdict["native_identity_confirmed"] is False
    assert "ordinary AutoCAD entity" in verdict["rejected"][0]["reason"]


def test_fake_native_class_is_rejected():
    verdict = confirm_native_identity([obj("2F", "TDbTotallyMadeUpPipe", PIPE_ANCESTRY)])

    assert verdict["native_identity_confirmed"] is False
    assert "not TDbPipe" in verdict["rejected"][0]["reason"]


def test_proxy_object_is_rejected_even_when_named_like_the_target():
    # A proxy means the real class was not loaded. It must never pass as native identity.
    assert is_proxy("AcDbProxyEntity") is True
    verdict = confirm_native_identity([obj("2F", "AcDbProxyEntity", PIPE_ANCESTRY)])

    assert verdict["native_identity_confirmed"] is False
    assert "proxy" in verdict["rejected"][0]["reason"]


def test_target_class_without_dbobject_ancestry_is_rejected():
    ok, reason = classify(obj("2F", "TDbPipe", ["SomethingElse"]), "TDbPipe")

    assert ok is False
    assert "does not derive from AcDbObject" in reason


def test_no_new_objects_is_reported_distinctly():
    verdict = confirm_native_identity([])

    assert verdict["native_identity_confirmed"] is False
    assert verdict["summary"] == "no new objects were created"


# --------------------------------------------- multiple objects created at once

def test_pipe_is_found_among_its_companion_objects():
    # Tianzheng creates nodes and helpers alongside the pipe; that must not defeat detection.
    created = [
        obj("30", "TDbPipeNode", ["TDbEntity", "AcDbEntity", "AcDbObject"]),
        obj("31", "TDbPipe", PIPE_ANCESTRY, dxf_name="TCH_PIPE"),
        obj("32", "TDbPipeNode", ["TDbEntity", "AcDbEntity", "AcDbObject"]),
    ]

    verdict = confirm_native_identity(created)

    assert verdict["native_identity_confirmed"] is True
    assert verdict["match_count"] == 1
    assert verdict["companion_classes"] == ["TDbPipeNode"]


def test_multiple_pipes_are_all_reported():
    created = [obj("31", "TDbPipe", PIPE_ANCESTRY), obj("32", "TDbPipe", PIPE_ANCESTRY)]

    verdict = confirm_native_identity(created)

    assert verdict["match_count"] == 2


def test_companions_alone_do_not_confirm_identity():
    verdict = confirm_native_identity([obj("30", "TDbPipeNode", ["AcDbEntity", "AcDbObject"])])

    assert verdict["native_identity_confirmed"] is False


# ------------------------------------------------------- properties and evidence

def test_properties_come_only_from_the_object():
    read = properties_actually_read({
        "start_point": [0.0, 0.0, 0.0],
        "end_point": [3000.0, 0.0, 0.0],
        "length": 3000.0,
    })

    assert read["start_point"] == [0.0, 0.0, 0.0]
    assert read["length"] == 3000.0
    # Nothing claimed for values the object never reported.
    assert read["not_readable_from_managed_code"] == ["diameter", "system", "elevation"]


def test_unreadable_properties_are_never_invented():
    read = properties_actually_read({"property_read_note": "no curve geometry reachable"})

    assert "start_point" not in read
    assert read["note"] == "no curve geometry reachable"
    assert set(read["not_readable_from_managed_code"]) == {"diameter", "system", "elevation"}


def test_verdict_is_json_serializable_as_evidence():
    verdict = confirm_native_identity([
        obj("31", "TDbPipe", PIPE_ANCESTRY, dxf_name="TCH_PIPE"),
        obj("30", "TDbPipeNode", ["AcDbEntity", "AcDbObject"]),
    ])

    round_tripped = json.loads(json.dumps(verdict, ensure_ascii=False))

    assert round_tripped["native_identity_confirmed"] is True
    assert round_tripped["companion_classes"] == ["TDbPipeNode"]
