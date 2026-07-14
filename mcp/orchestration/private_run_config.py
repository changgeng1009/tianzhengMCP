"""Explicit, unbundled run parameters for historical CAD workflows.

Set TIANZHENG_RUN_CONFIG to a local JSON file with schema_version=1 and a
parameters object. Keys are documented by the require_parameter calls in each
consumer. No defaults, CAD access, or inferred authorization are provided.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


class RunConfigurationError(ValueError):
    """Missing or invalid external evidence; execution must stop."""


def require_parameter(key: str, kind: str = "sha256") -> Any:
    filename = os.environ.get("TIANZHENG_RUN_CONFIG")
    if not filename:
        raise RunConfigurationError("Set TIANZHENG_RUN_CONFIG to an authorized local run configuration")
    if Path(filename).resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise RunConfigurationError("Run configuration must be stored outside the public repository")
    try:
        payload = json.loads(Path(filename).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunConfigurationError("Run configuration is unreadable or malformed") from exc
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1 or not isinstance(payload.get("parameters"), dict):
        raise RunConfigurationError("Run configuration requires schema_version=1 and parameters object")
    # Stage 4/5 workflows must have their full input identity and transform
    # before any copies or CAD connection, even when the first consumer hashes.
    stage45 = {"mcp.orchestration.stage4_mvp.reference_sha256", "mcp.orchestration.stage4_mvp.target_sha256", "stage45.translation"}
    if key in stage45:
        parameters = payload["parameters"]
        if not stage45.issubset(parameters):
            raise RunConfigurationError("Stage 4/5 requires both input hashes and translation before execution")
        for hash_key in stage45 - {"stage45.translation"}:
            if not isinstance(parameters[hash_key], str) or not re.fullmatch(r"[0-9a-f]{64}", parameters[hash_key]):
                raise RunConfigurationError("Invalid Stage 4/5 input hash")
        translation = parameters["stage45.translation"]
        if not isinstance(translation, list) or len(translation) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in translation):
            raise RunConfigurationError("Invalid Stage 4/5 translation")
    if key not in payload["parameters"]:
        raise RunConfigurationError(f"Missing run parameter: {key}")
    value = payload["parameters"][key]
    if kind == "sha256":
        valid = isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    elif kind in {"translation2", "translation3"}:
        valid = isinstance(value, list) and len(value) == int(kind[-1]) and all(type(v) in (int, float) and math.isfinite(v) for v in value)
    elif kind == "bindings":
        valid = isinstance(value, dict) and bool(value) and all(isinstance(k, str) and isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) and x for x in v) for k, v in value.items())
        if valid:
            valid = all(len({pair[i] for pair in value.values()}) == len(value) for i in (0, 1))
    else:
        raise RunConfigurationError(f"Unsupported run parameter type: {kind}")
    if not valid:
        raise RunConfigurationError(f"Invalid run parameter: {key} ({kind})")
    if kind == "bindings":
        required = {"basement", "first_floor", "floors_6_to_16", "floor_19_and_roof", "water_tank_and_tank_roof", "domestic_water_and_drainage_system", "fire_hydrant_and_sprinkler_system"}
        if set(value) != required:
            raise RunConfigurationError(f"Incomplete semantic bindings: {key}")
        return {k: tuple(v) for k, v in value.items()}
    return value


def verify_input_hash(path: Path, key: str) -> str:
    """Compare a supplied input against its configured digest, never invent one."""
    expected = require_parameter(key)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RunConfigurationError("Configured input is unavailable") from exc
    if digest != expected:
        raise RunConfigurationError(f"Input hash mismatch: {key}")
    return digest


def dependency_records(evidence: dict[str, Any]) -> list[dict[str, str]]:
    """Use explicit PoC mappings, including dependency-only failed-primary runs."""
    mappings = evidence.get("dependency_mappings")
    if not isinstance(mappings, list):
        raise RunConfigurationError("PoC dependency_mappings evidence is required")
    expected_tasks = evidence.get("approved_dependency_task_ids")
    if not isinstance(expected_tasks, list) or len(set(expected_tasks)) != len(expected_tasks):
        raise RunConfigurationError("PoC dependency task identities are required and must be unique")
    approved = set(evidence.get("approved_reference_handles", []))
    created = set(evidence.get("created_handles", []))
    records = []
    for item in mappings:
        if not isinstance(item, dict) or item.get("task_id") not in expected_tasks or item.get("reference_handle") == evidence.get("primary_reference_handle") or item.get("reference_handle") not in approved or item.get("target_handle") not in created or item.get("object_name") != "TDbPipe":
            raise RunConfigurationError("PoC dependency mapping is inconsistent with approved/created handles")
        records.append({k: item[k] for k in ("task_id", "reference_handle", "target_handle", "object_name")})
    if len({r["reference_handle"] for r in records}) != len(records) or len({r["target_handle"] for r in records}) != len(records):
        raise RunConfigurationError("PoC dependency mappings must be one-to-one")
    if {r["task_id"] for r in records} != set(expected_tasks) or len(records) != len(expected_tasks):
        raise RunConfigurationError("PoC dependency mappings are incomplete")
    return records


def verify_stage45_inputs(reference: Path, target: Path) -> None:
    """Fail before copies/connections when the configured input pair changed."""
    require_parameter("stage45.translation", "translation3")
    verify_input_hash(reference, "mcp.orchestration.stage4_mvp.reference_sha256")
    verify_input_hash(target, "mcp.orchestration.stage4_mvp.target_sha256")
