from mcp.orchestration.private_run_config import require_parameter
from pathlib import Path

from mcp.orchestration.stage6_p3_1_p4_0_native_relation_micro_clone import run_stage


ROOT = Path(r"D:\ExampleWorkspace\天正")


if __name__ == "__main__":
    report = run_stage(
        root=ROOT,
        prior_run=ROOT / "artifacts" / "stage6_p3_p4_missing_and_drawing" / "stage6_p3_p4_20260713_145002",
        p2_run=ROOT / "artifacts" / "stage6_p2_coordinate_reconstruction" / "stage6_p2_coordinate_reconstruction_20260713_101528",
        reference=ROOT / "图纸" / "reference_sample_t8_t8_t8.dwg",
        target=ROOT / "图纸" / "target_sample_t8.dwg",
        expected_reference_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_reference"),
        expected_target_hash=require_parameter("scripts.finalize_stage6_p3_p4_blocked.expected_target"),
        user_approval_text="",
        cached_sample_run=ROOT / "artifacts" / "stage6_p3_1_p4_0_native_relation_micro_clone" / "stage6_p3_1_p4_0_20260713_154100",
    )
    print(report["status"])
