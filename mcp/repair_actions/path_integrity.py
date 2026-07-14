from __future__ import annotations

from pathlib import Path
from typing import Any


CORRUPTION_MARKERS = ("????", "\ufffd")


def detect_corrupted_path(value: str) -> bool:
    text = str(value)
    return any(marker in text for marker in CORRUPTION_MARKERS)


def validate_path_integrity(value: str) -> dict[str, Any]:
    text = str(value)
    corrupted = detect_corrupted_path(text)
    return {
        "path": text,
        "path_corrupted": corrupted,
        "safe_for_source_operation": not corrupted,
        "reason": "path contains ASCII question-mark or replacement-character corruption" if corrupted else "",
    }


def validate_report_text_has_no_corrupted_paths(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    corrupted = detect_corrupted_path(text)
    return {
        "report_path": str(path),
        "path_corrupted": corrupted,
        "contains_question_mark_run": "????" in text,
        "contains_replacement_character": "\ufffd" in text,
    }


def utf8_round_trip(value: str) -> bool:
    return value.encode("utf-8").decode("utf-8") == value
