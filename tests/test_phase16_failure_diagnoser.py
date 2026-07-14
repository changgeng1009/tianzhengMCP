from __future__ import annotations


def test_failure_diagnoser_detects_no_confirmed_schema() -> None:
    from mcp.acceptance_pack.failure_diagnoser import diagnose_acceptance_failure

    diagnosis = diagnose_acceptance_failure(
        {
            "status": "warning",
            "artifacts": [
                {
                    "type": "acceptance_report_json",
                    "data": {
                        "confirmed_schema_status": {"confirmed_object_types": []},
                        "writeback_result": {},
                    },
                }
            ],
            "warnings": [],
            "errors": [],
        }
    )

    assert diagnosis["failure_type"] == "no_confirmed_schema"
    assert "manual_confirmation" in diagnosis["suggested_next_action"]


def test_failure_diagnoser_detects_reread_verification_failed() -> None:
    from mcp.acceptance_pack.failure_diagnoser import diagnose_acceptance_failure

    diagnosis = diagnose_acceptance_failure(
        {
            "status": "warning",
            "artifacts": [
                {
                    "type": "acceptance_report_json",
                    "data": {
                        "confirmed_schema_status": {"confirmed_object_types": ["TDbPipe"]},
                        "writeback_result": {"status": "committed"},
                        "reread_verification": {"status": "failed"},
                    },
                }
            ],
            "warnings": [],
            "errors": [],
        }
    )

    assert diagnosis["failure_type"] == "reread_verification_failed"
    assert "re-read" in diagnosis["blocking_reason"]

