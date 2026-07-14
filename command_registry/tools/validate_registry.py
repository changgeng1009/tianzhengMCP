"""Command Registry Validator - Phase C1.

Validate seed registry integrity: id uniqueness, alias conflicts,
safety policy compliance, production blocking.
"""

from collections import Counter
from typing import Any

REQUIRED_FIELDS = ["id", "domain", "primary_command", "category", "safety", "validation_status"]
VALID_DOMAINS = frozenset({"plumbing", "hvac"})
DANGEROUS_COMMANDS = {"TSaveAs", "dcsz", "tgbatplots"}


def validate_registry(commands: list[dict[str, Any]]) -> dict[str, Any]:
    """Full validation. Returns dict with errors, warnings, stats."""
    result: dict[str, Any] = {
        "total": len(commands),
        "errors": [],
        "warnings": [],
        "stats": {},
    }

    # 1. Required fields
    for c in commands:
        for field in REQUIRED_FIELDS:
            if not c.get(field):
                result["errors"].append(f"Missing {field} in command: {c.get('id', '?')}")

    # 2. Unique IDs
    ids = [c["id"] for c in commands]
    dup_ids = [i for i, n in Counter(ids).items() if n > 1]
    if dup_ids:
        result["errors"].append(f"Duplicate IDs: {dup_ids}")

    # 3. Valid domains
    for c in commands:
        if c.get("domain") not in VALID_DOMAINS:
            result["errors"].append(f"Invalid domain {c.get('domain')} in {c.get('id')}")

    # 4. Alias conflicts
    alias_map: dict[str, str] = {}
    for c in commands:
        for a in c.get("aliases", []):
            if a and a in alias_map:
                result["warnings"].append(f"Alias conflict: {a} used by {alias_map[a]} and {c['id']}")
            alias_map[a] = c["id"]

    # 5. Production forbidden
    prod_true = [c["id"] for c in commands if c.get("safety", {}).get("allow_production")]
    if prod_true:
        result["errors"].append(f"Allow production=true in: {prod_true}")

    val_prod = [c["id"] for c in commands if c.get("validation_status", {}).get("production") != "forbidden"]
    if val_prod:
        result["warnings"].append(f"Validation production not forbidden in: {val_prod}")

    # 6. Dangerous commands must be dangerous
    for c in commands:
        if c.get("primary_command") in DANGEROUS_COMMANDS:
            if c.get("safety", {}).get("danger_level") != "dangerous":
                result["errors"].append(f"{c['id']} should be dangerous but is {c.get('safety', {}).get('danger_level')}")
        if c.get("safety", {}).get("danger_level") == "dangerous":
            if c.get("safety", {}).get("allow_sandbox"):
                result["warnings"].append(f"Dangerous command {c['id']} allows sandbox")

    # 7. Stats
    danger_levels = Counter(c.get("safety", {}).get("danger_level", "?") for c in commands)
    domains = Counter(c.get("domain", "?") for c in commands)
    result["stats"] = {
        "by_domain": dict(domains),
        "by_danger_level": dict(danger_levels),
        "with_source": sum(1 for c in commands if c.get("source_ids")),
        "error_count": len(result["errors"]),
        "warning_count": len(result["warnings"]),
    }

    return result
