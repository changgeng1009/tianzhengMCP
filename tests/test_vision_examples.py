import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_example(name: str) -> dict:
    with (PROJECT_ROOT / "examples" / name).open("r", encoding="utf-8") as file:
        return json.load(file)


def test_examples_match_vision_mvp_data_contract() -> None:
    from vision.diff_engine import DiffEngine
    from vision.models import CurrentCADModel, ReferenceModel

    reference = ReferenceModel.from_dict(_load_example("reference_model_sample.json"))
    current = CurrentCADModel.from_dict(_load_example("current_cad_model_sample.json"))
    sample_diff = _load_example("diff_result_sample.json")

    result = DiffEngine(move_tolerance=0.05).compare(reference, current)

    assert result.summary() == sample_diff["summary"]
    assert [item.operation.value for item in result.items] == [
        item["operation"] for item in sample_diff["items"]
    ]
    for item in sample_diff["items"]:
        assert item["operation"] in {"add", "modify", "move", "delete_suggestion"}
        if item["operation"] == "delete_suggestion":
            assert item["automatic_execution_allowed"] is False
        if item["entity"] is not None:
            assert "geometry" in item["entity"]
