from vision.diff_engine import DiffEngine
from vision.models import CurrentCADModel, ReferenceModel, VisionEntity


def _entity(
    entity_id: str,
    entity_type: str,
    *,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    properties: dict[str, object] | None = None,
) -> VisionEntity:
    from vision.models import (
        BoundingBox,
        ConfidenceStatus,
        CoordinateSystem,
        EntityGeometry,
        Point2D,
    )

    return VisionEntity(
        entity_id=entity_id,
        type=entity_type,
        geometry=EntityGeometry(
            coordinate_system=CoordinateSystem.NORMALIZED,
            points=[
                Point2D(x=x_min, y=y_min, coordinate_system=CoordinateSystem.NORMALIZED),
                Point2D(x=x_max, y=y_max, coordinate_system=CoordinateSystem.NORMALIZED),
            ],
            bounding_box=BoundingBox(
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
                coordinate_system=CoordinateSystem.NORMALIZED,
            ),
        ),
        confidence=0.95,
        status=ConfidenceStatus.CONFIRMED,
        evidence="测试实体。",
        uncertainties=[],
        properties=properties or {},
    )


def test_diff_engine_outputs_only_incremental_operations() -> None:
    reference = ReferenceModel(
        source={"kind": "image", "name": "reference"},
        entities=[
            _entity(
                "shared_pipe",
                "pipe",
                x_min=0.10,
                y_min=0.10,
                x_max=0.40,
                y_max=0.12,
                properties={"dn": 100},
            ),
            _entity(
                "moved_fixture",
                "fixture",
                x_min=0.70,
                y_min=0.70,
                x_max=0.80,
                y_max=0.80,
            ),
            _entity(
                "missing_window",
                "window",
                x_min=0.20,
                y_min=0.80,
                x_max=0.30,
                y_max=0.85,
            ),
        ],
    )
    current = CurrentCADModel(
        source={"kind": "mock", "name": "current"},
        entities=[
            _entity(
                "shared_pipe",
                "pipe",
                x_min=0.10,
                y_min=0.10,
                x_max=0.40,
                y_max=0.12,
                properties={"dn": 75},
            ),
            _entity(
                "moved_fixture",
                "fixture",
                x_min=0.50,
                y_min=0.50,
                x_max=0.60,
                y_max=0.60,
            ),
            _entity(
                "obsolete_valve",
                "valve",
                x_min=0.90,
                y_min=0.90,
                x_max=0.95,
                y_max=0.95,
            ),
        ],
    )

    result = DiffEngine(move_tolerance=0.05).compare(reference, current)
    operations = [item.operation.value for item in result.items]

    assert operations == ["modify", "move", "add", "delete_suggestion"]
    assert not {"rebuild_all", "delete_all", "redraw_full_drawing"} & set(operations)
    delete_item = result.items[-1]
    assert delete_item.operation.value == "delete_suggestion"
    assert delete_item.automatic_execution_allowed is False
