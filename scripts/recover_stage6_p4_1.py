from pathlib import Path
from mcp.orchestration.stage6_p4_1_executor import read_json, recover_completed_records

ROOT=Path(r"D:\ExampleWorkspace\天正")
RUN=ROOT/"artifacts/stage6_p4_1_whole_drawing_completion/stage6_p4_1_20260713_160852"

if __name__ == "__main__":
    checkpoint=read_json(RUN/"execution/execution_checkpoint.json")
    result=recover_completed_records(
        run_root=RUN,
        candidate=ROOT/"图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852.dwg",
        prior_target_scan=ROOT/"artifacts/stage6_p3_p4_missing_and_drawing/stage6_p3_p4_20260713_145002/logs/target_full_readonly_scan.json",
        completed_batch_count=int(checkpoint["completed_batches"]),
    )
    print({key:value for key,value in result.items() if key != "records"})
