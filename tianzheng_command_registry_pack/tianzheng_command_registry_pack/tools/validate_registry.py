from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    commands = data.get("commands", [])
    errors: list[str] = []
    seen_ids: set[str] = set()

    for idx, cmd in enumerate(commands):
        prefix = f"commands[{idx}]"
        for key in ["id", "domain", "label_zh", "primary_command", "category", "safety", "validation_status"]:
            if key not in cmd:
                errors.append(f"{prefix} missing {key}")
        cid = cmd.get("id")
        if cid in seen_ids:
            errors.append(f"duplicate id: {cid}")
        seen_ids.add(cid)
        if cmd.get("safety", {}).get("allow_production") is True:
            errors.append(f"{prefix} production must remain false at Phase T0/T1: {cid}")

    if errors:
        print("\n".join(errors))
        return 1

    print(f"OK: {len(commands)} commands validated. Production is disabled for all commands.")
    return 0


if __name__ == "__main__":
    sys.exit(validate(sys.argv[1] if len(sys.argv) > 1 else "registries/tianzheng_commands.seed.json"))
