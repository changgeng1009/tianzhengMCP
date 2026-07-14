from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ALIAS_RE = re.compile(
    r"^\s*(?:(?P<alias>[A-Za-z0-9_\u4e00-\u9fff]+)\s*[,，]?\s*)?\*+\s*(?P<command>[A-Za-z0-9_().\" \-]+)\s*(?:;(?P<comment>.*))?$"
)
PGP_RE = re.compile(
    r"^\s*(?P<alias>[A-Za-z0-9_]+)\s*[,，]\s*\*+\s*(?P<command>[A-Za-z0-9_().\" \-]+)\s*(?:;(?P<comment>.*))?$"
)


def infer_domain(path: Path, text: str) -> str:
    p = str(path).lower()
    if any(k in p for k in ["twt", "给排水", "gps", "wt"]):
        return "plumbing"
    if any(k in p for k in ["thvac", "暖通", "nt", "hvac"]):
        return "hvac"
    if any(k in text for k in ["风管", "风口", "水管阀件", "风机盘管"]):
        return "hvac"
    if any(k in text for k in ["给排水", "消火栓", "喷头", "洁具"]):
        return "plumbing"
    return "generic"


def parse_command_file(path: Path, default_domain: str | None = None) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="gbk", errors="ignore")
    domain = default_domain or infer_domain(path, raw)
    records: list[dict[str, Any]] = []
    last_comment = ""

    for line_no, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            comment = stripped.lstrip(";").strip()
            if comment:
                last_comment = comment
            continue

        m = PGP_RE.match(stripped) or ALIAS_RE.match(stripped)
        if not m:
            continue

        command = (m.group("command") or "").strip()
        alias = (m.groupdict().get("alias") or "").strip()
        comment = (m.groupdict().get("comment") or "").strip() or last_comment

        if not command:
            continue

        label = comment or command
        safe_command = re.sub(r"[^a-zA-Z0-9_]+", "_", command).strip("_") or "cmd"
        command_id = f"{domain}_{safe_command.lower()}_{line_no}"

        records.append(
            {
                "id": command_id,
                "domain": domain,
                "module": "天正给排水" if domain == "plumbing" else ("天正暖通" if domain == "hvac" else "天正/AutoCAD"),
                "label_zh": label,
                "primary_command": command,
                "aliases": [alias] if alias else [],
                "all_invocation_names": [x for x in [command, alias] if x],
                "category": "unclassified_from_local_file",
                "expected_inputs": [],
                "interactive": True,
                "creates_or_edits": [],
                "safety": {
                    "danger_level": "review",
                    "allow_dry_run": True,
                    "allow_sandbox": True,
                    "allow_production": False,
                    "requires_visual_review": True,
                    "notes": "本地抽取命令，需人工分类与 sandbox 验证。"
                },
                "validation_status": {
                    "source_status": f"local_file:{path.name}:line:{line_no}",
                    "dry_run": "not_started",
                    "sandbox": "not_started",
                    "production": "forbidden"
                },
                "source_ids": [str(path)],
                "notes": ""
            }
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Tianzheng commands from local acad.pgp / tmn / mnu-like text files.")
    parser.add_argument("--root", required=True, help="Tianzheng installation root or sys directory")
    parser.add_argument("--domain", choices=["plumbing", "hvac", "generic"], default=None)
    parser.add_argument("--out", default="local_tianzheng_commands.extracted.json")
    parser.add_argument("--patterns", nargs="*", default=["*.pgp", "*.tmn", "*.mnu", "*.txt", "*.lsp"])
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Path not found: {root}")

    files: list[Path] = []
    for pattern in args.patterns:
        files.extend(root.rglob(pattern))

    commands: list[dict[str, Any]] = []
    for file in sorted(set(files)):
        try:
            commands.extend(parse_command_file(file, args.domain))
        except Exception as exc:
            print(f"[WARN] Skip {file}: {exc}")

    payload = {
        "schema_version": "0.1.0",
        "status": "local_extracted_needs_review",
        "root": str(root),
        "file_count": len(files),
        "command_count": len(commands),
        "commands": commands,
    }

    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(commands)} commands to {args.out}")


if __name__ == "__main__":
    main()
