from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from vision.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT
from vision.schema import VISION_REFERENCE_MODEL_SCHEMA


ALLOWED_IMAGE_DETAILS = {"original", "high", "auto", "low"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class VisionProviderConfig:
    model: str = "gpt-5.5"
    image_detail: str = "original"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model is required")
        if self.image_detail not in ALLOWED_IMAGE_DETAILS:
            raise ValueError(
                "image_detail must be one of: auto, high, low, original"
            )


@dataclass(frozen=True)
class ImageInput:
    image_url: str | None = None
    path: Path | None = None
    mime_type: str | None = None

    @classmethod
    def from_url(cls, image_url: str) -> "ImageInput":
        if not image_url:
            raise ValueError("image_url is required")
        return cls(image_url=image_url)

    @classmethod
    def from_path(cls, path: str | Path) -> "ImageInput":
        image_path = Path(path)
        suffix = image_path.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError("only PNG, JPG, and JPEG reference images are supported")
        mime_type = mimetypes.types_map.get(suffix, "application/octet-stream")
        return cls(path=image_path, mime_type=mime_type)

    def to_openai_image_url(self) -> str:
        if self.image_url:
            return self.image_url
        if self.path is None:
            raise ValueError("image_url or path is required")
        data = base64.b64encode(self.path.read_bytes()).decode("ascii")
        mime_type = self.mime_type or "application/octet-stream"
        return f"data:{mime_type};base64,{data}"


class VisionProvider(Protocol):
    def analyze_image(self, image: ImageInput) -> dict[str, Any]:
        """返回结构化 Reference Model 字典。"""


class OpenAIVisionProvider:
    """OpenAI Vision Provider，模型和图片细节等级通过配置控制。"""

    def __init__(
        self,
        config: VisionProviderConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or VisionProviderConfig()
        self._client = client

    def build_responses_payload(self, image: ImageInput) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "input": [
                {
                    "role": "system",
                    "content": VISION_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": VISION_USER_PROMPT,
                        },
                        {
                            "type": "input_image",
                            "image_url": image.to_openai_image_url(),
                            "detail": self.config.image_detail,
                        },
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "vision_reference_model",
                    "schema": VISION_REFERENCE_MODEL_SCHEMA,
                    "strict": True,
                }
            },
        }

    def analyze_image(self, image: ImageInput) -> dict[str, Any]:
        client = self._client
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAI SDK is required for real Vision calls. "
                    "Install project requirements before manual integration testing."
                ) from exc
            client = OpenAI()

        response = client.responses.create(**self.build_responses_payload(image))
        return self._extract_structured_output(response)

    def _extract_structured_output(self, response: Any) -> dict[str, Any]:
        if hasattr(response, "output_parsed") and response.output_parsed is not None:
            parsed = response.output_parsed
            return parsed if isinstance(parsed, dict) else parsed.model_dump()

        if hasattr(response, "output_text") and response.output_text:
            return json.loads(response.output_text)

        if isinstance(response, dict):
            if "output_parsed" in response and response["output_parsed"] is not None:
                return response["output_parsed"]
            if "output_text" in response and response["output_text"]:
                return json.loads(response["output_text"])

        raise ValueError("OpenAI response did not contain structured JSON output")
