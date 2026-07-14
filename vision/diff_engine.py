from __future__ import annotations

from typing import Any

from vision.models import (
    CurrentCADModel,
    DiffItem,
    DiffOperation,
    DiffResult,
    ReferenceModel,
    VisionEntity,
)


class DiffEngine:
    """只输出增量差异建议，不生成整图重绘计划。"""

    def __init__(self, move_tolerance: float = 0.03) -> None:
        self.move_tolerance = move_tolerance

    def compare(
        self, reference_model: ReferenceModel, current_model: CurrentCADModel
    ) -> DiffResult:
        items: list[DiffItem] = []
        used_current_ids: set[str] = set()

        for reference_entity in reference_model.entities:
            current_entity = self._find_match(
                reference_entity, current_model.entities, used_current_ids
            )
            if current_entity is None:
                items.append(self._add_item(reference_entity))
                continue

            used_current_ids.add(current_entity.entity_id)
            property_changes = self._property_changes(reference_entity, current_entity)
            if property_changes:
                items.append(self._modify_item(reference_entity, current_entity, property_changes))

            move_changes = self._move_changes(reference_entity, current_entity)
            if move_changes:
                items.append(self._move_item(reference_entity, current_entity, move_changes))

        for current_entity in current_model.entities:
            if current_entity.entity_id not in used_current_ids:
                items.append(self._delete_suggestion_item(current_entity))

        return DiffResult(items=items)

    def _find_match(
        self,
        reference_entity: VisionEntity,
        current_entities: list[VisionEntity],
        used_current_ids: set[str],
    ) -> VisionEntity | None:
        for current_entity in current_entities:
            if (
                current_entity.entity_id == reference_entity.entity_id
                and current_entity.entity_id not in used_current_ids
            ):
                return current_entity

        reference_key = self._match_key(reference_entity)
        for current_entity in current_entities:
            if current_entity.entity_id in used_current_ids:
                continue
            if self._match_key(current_entity) == reference_key:
                return current_entity
        return None

    def _match_key(self, entity: VisionEntity) -> tuple[str, tuple[tuple[str, Any], ...]]:
        stable_properties = {
            key: value
            for key, value in entity.properties.items()
            if key in {"system", "dn", "text", "symbol_name", "dimension"}
        }
        return (entity.type, tuple(sorted(stable_properties.items())))

    def _property_changes(
        self, reference_entity: VisionEntity, current_entity: VisionEntity
    ) -> dict[str, Any]:
        if reference_entity.properties == current_entity.properties:
            return {}
        return {
            "properties": {
                "from": dict(current_entity.properties),
                "to": dict(reference_entity.properties),
            }
        }

    def _move_changes(
        self, reference_entity: VisionEntity, current_entity: VisionEntity
    ) -> dict[str, Any]:
        reference_box = reference_entity.geometry.bounding_box
        current_box = current_entity.geometry.bounding_box
        if reference_box is None or current_box is None:
            return {}
        if reference_box.coordinate_system != current_box.coordinate_system:
            return {}
        distance = reference_box.distance_to(current_box)
        if distance <= self.move_tolerance:
            return {}
        return {
            "coordinate_system": reference_box.coordinate_system.value,
            "from": current_box.to_dict(),
            "to": reference_box.to_dict(),
            "distance": distance,
        }

    def _add_item(self, reference_entity: VisionEntity) -> DiffItem:
        return DiffItem(
            operation=DiffOperation.ADD,
            reference_entity_id=reference_entity.entity_id,
            current_entity_id=None,
            entity_type=reference_entity.type,
            confidence=reference_entity.confidence,
            reason="Reference Model 中存在该对象，Current CAD Model 中未找到匹配对象。",
            entity=reference_entity.to_dict(),
        )

    def _modify_item(
        self,
        reference_entity: VisionEntity,
        current_entity: VisionEntity,
        changes: dict[str, Any],
    ) -> DiffItem:
        return DiffItem(
            operation=DiffOperation.MODIFY,
            reference_entity_id=reference_entity.entity_id,
            current_entity_id=current_entity.entity_id,
            entity_type=reference_entity.type,
            confidence=min(reference_entity.confidence, current_entity.confidence),
            reason="匹配对象存在，但属性与 Reference Model 不一致。",
            changes=changes,
        )

    def _move_item(
        self,
        reference_entity: VisionEntity,
        current_entity: VisionEntity,
        changes: dict[str, Any],
    ) -> DiffItem:
        return DiffItem(
            operation=DiffOperation.MOVE,
            reference_entity_id=reference_entity.entity_id,
            current_entity_id=current_entity.entity_id,
            entity_type=reference_entity.type,
            confidence=min(reference_entity.confidence, current_entity.confidence),
            reason="匹配对象存在，但位置差异超过移动容差。",
            changes=changes,
        )

    def _delete_suggestion_item(self, current_entity: VisionEntity) -> DiffItem:
        return DiffItem(
            operation=DiffOperation.DELETE_SUGGESTION,
            reference_entity_id=None,
            current_entity_id=current_entity.entity_id,
            entity_type=current_entity.type,
            confidence=current_entity.confidence,
            reason="Current CAD Model 中存在该对象，但 Reference Model 中未找到匹配对象；仅建议删除，不允许自动执行。",
            entity=current_entity.to_dict(),
        )
