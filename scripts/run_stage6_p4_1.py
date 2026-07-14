from mcp.orchestration.private_run_config import require_parameter
from pathlib import Path

from mcp.orchestration.stage6_p4_1_whole_drawing_completion import run_analysis


ROOT = Path(r"D:\ExampleWorkspace\天正")

if __name__ == "__main__":
    result = run_analysis(
        root=ROOT,
        prior_run=ROOT / "artifacts" / "stage6_p3_p4_missing_and_drawing" / "stage6_p3_p4_20260713_145002",
        p2_run=ROOT / "artifacts" / "stage6_p2_coordinate_reconstruction" / "stage6_p2_coordinate_reconstruction_20260713_101528",
        reference=ROOT / "图纸" / "reference_sample_t8_t8_t8.dwg",
        target=ROOT / "图纸" / "target_sample_t8.dwg",
        expected_reference_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_reference"),
        expected_target_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_target"),
        approval_text="允许继续",
    )
    print(result["status"])

