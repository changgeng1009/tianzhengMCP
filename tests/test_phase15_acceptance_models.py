from __future__ import annotations


def test_acceptance_models_are_json_serializable() -> None:
    from mcp.acceptance.models import (
        AcceptanceRunConfig,
        AcceptanceRunResult,
        ConfirmedSchemaSet,
        ManualConfirmationTemplate,
        T30ProbeWorkflowResult,
    )

    probe = T30ProbeWorkflowResult(
        workflow_id="wf1",
        probe_result_path="artifacts/t30_probe_result.json",
        status="success",
        capabilities=[{"capability_id": "TDbPipe.Insert"}],
        candidate_methods=[{"method": "TDbPipe.Insert"}],
    )
    template = ManualConfirmationTemplate(
        template_id="tpl1",
        generated_from_probe="probe.json",
        object_types=["TDbPipe"],
        confirmation_items={"TDbPipe.Insert": {"confirmed": False}},
    )
    schema_set = ConfirmedSchemaSet(
        schema_set_id="schema1",
        schemas=[{"object_type": "TDbPipe"}],
        confirmed_object_types=["TDbPipe"],
        unconfirmed_object_types=["TDbSprinkler"],
    )
    config = AcceptanceRunConfig(run_id="run1", scenario_path="scenario.json")
    result = AcceptanceRunResult(
        run_id="run1",
        status="warning",
        confirmed_schema_status=schema_set.to_dict(),
    )

    assert probe.to_dict()["candidate_methods"][0]["method"] == "TDbPipe.Insert"
    assert template.to_dict()["confirmation_items"]["TDbPipe.Insert"]["confirmed"] is False
    assert config.to_dict()["dry_run_only"] is True
    assert result.to_dict()["confirmed_schema_status"]["confirmed_object_types"] == ["TDbPipe"]

