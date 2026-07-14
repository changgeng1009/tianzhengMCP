from pathlib import Path
import json

from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, _resolve_open_document, _close_document_without_save
from mcp.acceptance.stage5_2_native_clone_poc import _retry

ROOT=Path(r"D:\ExampleWorkspace\天正")
RUN=ROOT/"artifacts/stage6_p4_1_whole_drawing_completion/stage6_p4_1_20260713_160852"
CANDIDATE=ROOT/"图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852.dwg"
TARGET_SCAN=ROOT/"artifacts/stage6_p3_p4_missing_and_drawing/stage6_p3_p4_20260713_145002/logs/target_full_readonly_scan.json"

if __name__ == "__main__":
    recovery=json.loads((RUN/"execution/recovery_checkpoint.json").read_text(encoding="utf-8"))
    target=json.loads(TARGET_SCAN.read_text(encoding="utf-8"))
    original={str(item["handle"]).upper() for item in target["entities"] if item.get("handle")}
    handles=[str(value).upper() for value in recovery["unmatched_new_handles"]]
    if any(handle in original for handle in handles):
        raise RuntimeError("REFUSE_TO_DELETE_PREEXISTING_TARGET_OBJECT")
    acad=attach_existing_autocad(); document=None
    deleted=[]
    try:
        returned=_retry(lambda: acad.Documents.Open(str(CANDIDATE),False),"open candidate for new-object cleanup",attempts=30,delay=.5)
        document=_resolve_open_document(acad,CANDIDATE,returned)
        document=_retry(lambda: acad.ActiveDocument,"resolve active cleanup document",attempts=30,delay=.5)
        full_name=_retry(lambda: str(document.FullName),"read cleanup document path",attempts=30,delay=.5)
        read_only=_retry(lambda: bool(document.ReadOnly),"read cleanup document mode",attempts=30,delay=.5)
        if read_only or Path(full_name).resolve()!=CANDIDATE.resolve():
            raise RuntimeError("CANDIDATE_IDENTITY_OR_WRITABILITY_FAILED")
        for handle in handles:
            try:
                obj=_retry(lambda handle=handle: document.HandleToObject(handle),f"resolve cleanup handle {handle}",attempts=3,delay=.2)
            except Exception:
                deleted.append({"handle":handle,"reason":"REMOVED_BY_SAME_BATCH_DEPENDENCY_CASCADE"})
                continue
            deleted.append({"handle":handle,"object_name":str(obj.ObjectName),"layer":str(obj.Layer),"reason":"AUTO_DEPENDENCY_AT_REFERENCE_COORDINATES"})
            _retry(lambda obj=obj: obj.Delete(),f"delete cleanup handle {handle}",attempts=10,delay=.2)
        _retry(lambda: document.Save(),"save dependency cleanup",attempts=10,delay=.5)
        _retry(lambda: document.Close(False),"close dependency cleanup",attempts=10,delay=.3); document=None
        (RUN/"execution/auto_dependency_cleanup.json").write_text(json.dumps({"deleted_count":len(deleted),"deleted":deleted,"preexisting_target_deleted":0},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print({"deleted_count":len(deleted),"preexisting_target_deleted":0})
    finally:
        if document is not None:
            _close_document_without_save(document)
        detach_autocad()
