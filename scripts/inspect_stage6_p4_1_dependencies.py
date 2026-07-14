from pathlib import Path
import json

from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, _open_document_with_retry, _resolve_open_document, _close_document_without_save
from mcp.acceptance.stage5_2_native_clone_poc import _scan_native

ROOT=Path(r"D:\ExampleWorkspace\天正")
RUN=ROOT/"artifacts/stage6_p4_1_whole_drawing_completion/stage6_p4_1_20260713_160852"
CANDIDATE=ROOT/"图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852.dwg"

if __name__ == "__main__":
    recovery=json.loads((RUN/"execution/recovery_checkpoint.json").read_text(encoding="utf-8"))
    acad=attach_existing_autocad(); document=None
    try:
        document=_resolve_open_document(acad,CANDIDATE,_open_document_with_retry(acad,CANDIDATE))
        records=[_scan_native(document.HandleToObject(handle),"p4_1_auto_dependency") for handle in recovery["unmatched_new_handles"]]
        (RUN/"execution/auto_dependency_records.json").write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print([(item["handle"],item["object_name"],item["layer"],item.get("bbox")) for item in records])
    finally:
        if document is not None:
            _close_document_without_save(document)
        detach_autocad()
