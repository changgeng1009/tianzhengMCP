from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from runtime.errors import ManifestInvalid

from .migrator import ManifestMigrator
from .versioning import CURRENT_VERSION, ManifestVersionPolicy


class ManifestLoader:
    """只读取 UTF-8 JSON Manifest；拒绝把 CAD 文件作为配置载入。"""

    def __init__(self, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).resolve().parents[1] / "schemas"

    def load(self, path: str | Path) -> dict[str, Any]:
        candidate = Path(path)
        if candidate.suffix.lower() != ".json":
            raise ManifestInvalid("Manifest 必须是 JSON 文件", field="path")
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ManifestInvalid(
                f"Manifest 读取或 JSON 解析失败: {exc}", field="path", source=str(candidate)
            ) from exc
        if not isinstance(payload, dict):
            raise ManifestInvalid("Manifest 顶层必须是 object")
        return payload

    def validate(self, manifest: Mapping[str, Any]) -> None:
        normalized = ManifestVersionPolicy.normalize(manifest.get("schema_version"))
        schema_name = (
            "project_manifest.schema.json"
            if normalized == CURRENT_VERSION
            else "project_manifest_v1_0.schema.json"
        )
        schema = json.loads((self.schema_root / schema_name).read_text(encoding="utf-8"))
        try:
            import jsonschema
            jsonschema.validate(
                dict(manifest), schema, format_checker=jsonschema.FormatChecker()
            )
        except ImportError as exc:
            raise ManifestInvalid("需要 jsonschema 才能验证 Manifest") from exc
        except jsonschema.ValidationError as exc:
            field = ".".join(str(part) for part in exc.absolute_path) or None
            raise ManifestInvalid(
                exc.message,
                field=field,
                details={"schema_path": list(exc.absolute_schema_path)},
            ) from exc

    def load_canonical(self, path: str | Path) -> dict[str, Any]:
        manifest = self.load(path)
        self.validate(manifest)
        canonical = ManifestMigrator().migrate(manifest)
        self.validate(canonical)
        return canonical
