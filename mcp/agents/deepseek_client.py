from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request
from typing import Any


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class DeepSeekClientResult:
    ok: bool
    status: str
    content: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "content": self.content,
            "error": self.error,
        }


def _read_api_key() -> str | None:
    value = os.environ.get("DEEPSEEK_API_KEY")
    return value if value else None


def _dry_run_response(task_pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": task_pack.get("phase", ""),
        "status": "PARTIAL",
        "files_modified": [],
        "tests_run": [],
        "test_result": "dry_run: no remote DeepSeek call executed",
        "safety_result": {
            "api_key_logged": False,
            "full_chat_sent": False,
            "opened_source_dwg": False,
            "saved_source_dwg": False,
            "used_sendcommand": False,
            "executed_tianzheng_command": False,
        },
        "notes": ["dry_run completed without reading or sending an API key"],
        "next_recommendation": "可用于后续 MVP-1 dry-run 任务。",
    }


def call_deepseek(
    task_pack: dict[str, Any],
    *,
    dry_run: bool = False,
    timeout: float = 30.0,
    max_tokens: int | None = None,
    temperature: float = 0.2,
    model: str = DEFAULT_MODEL,
) -> DeepSeekClientResult:
    if dry_run:
        return DeepSeekClientResult(ok=True, status="PARTIAL", content=_dry_run_response(task_pack))

    api_key = _read_api_key()
    if not api_key:
        return DeepSeekClientResult(
            ok=False,
            status="BLOCKED",
            error="DEEPSEEK_API_KEY is not set; remote call skipped safely",
        )

    request_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a controlled non-visual code worker. Return only JSON matching the requested schema.",
            },
            {
                "role": "user",
                "content": json.dumps(task_pack, ensure_ascii=False),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens or int(task_pack.get("max_output_tokens", 4000)),
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return DeepSeekClientResult(ok=False, status="FAIL", error=f"DeepSeek request failed: {type(exc).__name__}")

    try:
        content_text = payload["choices"][0]["message"]["content"]
        content = json.loads(content_text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return DeepSeekClientResult(ok=False, status="FAIL", error=f"DeepSeek response parse failed: {type(exc).__name__}")

    return DeepSeekClientResult(ok=True, status=str(content.get("status", "PASS")), content=content)
