from __future__ import annotations

from typing import Any, Protocol

from mcp.vision.models import VisionElement


class OCRProvider(Protocol):
    def detect_texts(self, image: dict[str, Any]) -> list[VisionElement]:
        ...


class StubOCRProvider:
    warning = "OCR provider not configured"

    def detect_texts(self, image: dict[str, Any]) -> list[VisionElement]:
        return []


class OptionalTesseractOCRProvider:
    def detect_texts(self, image: dict[str, Any]) -> list[VisionElement]:
        try:
            pytesseract = __import__("pytesseract")
        except ImportError as exc:
            raise RuntimeError("pytesseract not available") from exc
        _ = pytesseract
        return []
