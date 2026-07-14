from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_registry(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["commands"]


def resolve_command(
    intent: str,
    registry_path: str | Path = "registries/tianzheng_commands.seed.json",
    domain: str | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Return command candidates only. This function must never execute CAD commands."""
    intent_norm = intent.lower().strip()
    commands = load_registry(registry_path)
    if domain:
        commands = [c for c in commands if c.get("domain") == domain]

    scored: list[tuple[int, dict[str, Any]]] = []
    for cmd in commands:
        text = " ".join(
            [
                cmd.get("label_zh", ""),
                cmd.get("primary_command", ""),
                cmd.get("category", ""),
                " ".join(cmd.get("aliases", [])),
                " ".join(cmd.get("all_invocation_names", [])),
            ]
        ).lower()
        score = 0
        for token in [intent_norm, *intent_norm.split()]:
            if token and token in text:
                score += 10 if token == intent_norm else 2
        # Simple Chinese intent hints.
        if "管" in intent and ("管" in cmd.get("label_zh", "") or cmd.get("category") == "draw_or_pipe_network"):
            score += 2
        if "标注" in intent and cmd.get("category") == "annotation":
            score += 4
        if "阀" in intent and "阀" in cmd.get("label_zh", ""):
            score += 4
        if "风" in intent and cmd.get("domain") == "hvac":
            score += 2
        if "给水" in intent and cmd.get("domain") == "plumbing":
            score += 2
        if score:
            scored.append((score, cmd))

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [c for _, c in scored[:max_results]]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resolve Tianzheng command candidates without executing anything.")
    parser.add_argument("intent", help="Natural language intent or command keyword")
    parser.add_argument("--registry", default="registries/tianzheng_commands.seed.json")
    parser.add_argument("--domain", choices=["plumbing", "hvac"], default=None)
    args = parser.parse_args()

    print(json.dumps(resolve_command(args.intent, args.registry, args.domain), ensure_ascii=False, indent=2))
