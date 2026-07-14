from pathlib import Path

from mcp.orchestration import stage6_p4_1_executor as stage


def task(index, name="TDbPipe", region="t1"):
    return {"task_id":f"x{index}","reference_handle":str(index),"object_name":name,"target_region_id":region}


def test_batches_do_not_cross_region_or_type():
    batches=stage.ordered_batches([task(1),task(2,region="t2"),task(3,name="AcDbLine")])
    assert all(len({item["target_region_id"] for item in batch["tasks"]})==1 for batch in batches)
    assert all(len({item["object_name"] for item in batch["tasks"]})==1 for batch in batches)


def test_batch_size_is_bounded():
    batches=stage.ordered_batches([task(i) for i in range(120)],tdb_batch_size=50)
    assert [len(batch["tasks"]) for batch in batches]==[50,50,20]


def test_ordinary_precedes_tdb():
    batches=stage.ordered_batches([task(1),task(2,name="AcDbCircle")])
    assert batches[0]["object_name"]=="AcDbCircle"


def test_mapping_uses_idpairs():
    parsed={"idpairs":[{"source_handle":"1","target_handle":"A"}],"primary_return_records":[]}
    assert stage._resolve_batch_mapping(parsed,[task(1)])=={"1":"A"}


def test_mapping_can_use_exact_primary_return_count():
    parsed={"idpairs":[],"primary_return_records":[{"handle":"A"}]}
    assert stage._resolve_batch_mapping(parsed,[task(1)])=={"1":"A"}


def test_bbox_validation_uses_tolerance():
    assert stage._bbox_close([0,0,1,1],[0.1,0.1,1.1,1.1])
    assert not stage._bbox_close([0,0,1,1],[100,100,101,101])


def test_source_contains_no_sendcommand_or_saveas():
    source=Path(stage.__file__).read_text(encoding="utf-8")
    assert "Send"+"Command(" not in source
    assert ".SaveAs(" not in source


def test_manual_save_path_returns_before_final_close():
    source=Path(stage.__file__).read_text(encoding="utf-8")
    marker='return {"status": manual_state["status"]'
    assert marker in source


def test_display_bbox_exception_is_limited_to_annotations():
    source=Path(stage.__file__).read_text(encoding="utf-8")
    assert '{"TDbSymbMultiLeader", "TDbVPipeDim"}' in source
