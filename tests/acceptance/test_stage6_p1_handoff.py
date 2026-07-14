from pathlib import Path

from mcp.orchestration import stage6_p1_handoff as handoff


def test_handoff_executor_contains_no_persistence_or_close_calls() -> None:
    source = Path(handoff.__file__).read_text(encoding="utf-8")
    forbidden = (".Save(", ".SaveAs(", ".Close(", "Close(False)", "Close(True)")
    for token in forbidden:
        assert token not in source


def test_handoff_chunks_preserve_all_handles() -> None:
    values = [f"H{index}" for index in range(405)]
    chunks = handoff._chunks(values, 200)
    assert [len(item) for item in chunks] == [200, 200, 5]
    assert [value for chunk in chunks for value in chunk] == values
