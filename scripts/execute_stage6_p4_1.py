from mcp.orchestration.private_run_config import require_parameter
from pathlib import Path
from mcp.orchestration.stage6_p4_1_executor import execute

ROOT=Path(r"D:\ExampleWorkspace\天正")
RUN=ROOT/"artifacts/stage6_p4_1_whole_drawing_completion/stage6_p4_1_20260713_160852"

if __name__ == "__main__":
    result=execute(
        run_root=RUN,
        reference=ROOT/"图纸/reference_sample_t8_t8_t8.dwg",
        original_target=ROOT/"图纸/target_sample_t8.dwg",
        candidate=ROOT/"图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852.dwg",
        backup=ROOT/"图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852_prewrite_backup.dwg",
        p2_run=ROOT/"artifacts/stage6_p2_coordinate_reconstruction/stage6_p2_coordinate_reconstruction_20260713_101528",
        expected_reference_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_reference"),
        expected_target_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_target"),
        approval_text="我批准 sandbox 执行",
    )
    print(result["status"])

