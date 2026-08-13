"""S10.5 capability honesty.

The four combinations tested here are the ones S10 actually paid to learn, and they are the
ones most likely to be quietly broken by a later refactor:

    valve       runtime exists, create unavailable
    fitting     runtime exists, ACTIVE create unavailable (side-effect creation is not the same)
    pump        available
    annotation  control available, entity create NOT APPLICABLE

If any of them ever flips silently, MCP starts promising objects it cannot build.
"""
from __future__ import annotations

import pytest

from mcp_nextgen.s10 import capabilities as caps


class TestPublishedRegistry:
    def test_registry_matches_the_declared_s10_5_table(self):
        registry = caps.native_capability_registry()
        assert registry == {
            "tianzheng_native_pipe_create": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_pipe_query": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_pipe_identity_validation": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_pipe_persistence": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_pipe_idempotency": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_pump_create": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_equipment_create": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_equipment_query": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_pipe_annotation_control": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_pipe_diameter_annotation": "AVAILABLE_SANDBOX_MVP",
            "tianzheng_native_valve_create": "NOT_IMPLEMENTED",
            "tianzheng_native_fitting_create": "NOT_IMPLEMENTED",
            "tianzheng_native_annotation_create": "NOT_APPLICABLE",
        }

    def test_supported_equipment_types_is_pump_only(self):
        assert caps.SUPPORTED_EQUIPMENT_TYPES == ("pump",)
        assert caps.equipment_type_supported("pump")
        assert caps.equipment_type_supported("PUMP"), "the check is case-insensitive"
        for unsupported in ("water_tank", "boiler", "chiller", "fan", ""):
            assert not caps.equipment_type_supported(unsupported)


class TestThreeLayerHonesty:
    """runtime_available != manual_creation_available != automation_available."""

    def test_valve_runtime_exists_but_creation_is_not_automatable(self):
        valve = caps.OBJECT_FAMILIES["valve"]
        assert valve.runtime_class == "TDbPipeValve"
        assert valve.dxf_name == "TCH_PIPEVALVE"
        assert valve.runtime_available is True
        assert valve.manual_creation_available is True
        assert valve.automation_available is False
        assert valve.blocker == "BLOCKED_BY_INTERACTIVE_INPUT_SURFACE"
        assert valve.public_capabilities == ()
        assert caps.capability_status(caps.CAP_VALVE_CREATE) == caps.NOT_IMPLEMENTED
        assert not caps.is_usable(caps.CAP_VALVE_CREATE)

    def test_fitting_runtime_exists_but_active_creation_is_unavailable(self):
        fitting = caps.OBJECT_FAMILIES["fitting"]
        assert fitting.runtime_class == "TDbPipeFitting"
        assert fitting.runtime_available is True
        assert fitting.automation_available is False
        assert fitting.blocker == "ACTIVE_CREATION_NOT_AVAILABLE"
        assert not caps.is_usable(caps.CAP_FITTING_CREATE)

    def test_fitting_side_effect_creation_is_not_a_create_capability(self):
        # Endpoint fittings really do appear when a pipe is created. That must never be
        # reported as the ability to insert a fitting deliberately.
        fitting = caps.OBJECT_FAMILIES["fitting"]
        assert "side effect" in fitting.note
        assert caps.CAP_FITTING_CREATE not in fitting.public_capabilities

    def test_pump_is_available_on_all_three_layers(self):
        pump = caps.OBJECT_FAMILIES["equipment_pump"]
        assert pump.runtime_class == "TDbPump"
        assert pump.dxf_name == "TCH_PUMP"
        assert (pump.runtime_available, pump.manual_creation_available,
                pump.automation_available) == (True, True, True)
        assert caps.is_usable(caps.CAP_PUMP_CREATE)

    def test_annotation_control_available_but_entity_create_not_applicable(self):
        annotation = caps.OBJECT_FAMILIES["pipe_annotation"]
        assert annotation.automation_available is True
        assert caps.is_usable(caps.CAP_ANNOTATION_CONTROL)
        assert caps.is_usable(caps.CAP_DIAMETER_ANNOTATION)

        # NOT_APPLICABLE, not NOT_IMPLEMENTED: there is no annotation entity to create, so
        # "unfinished" would wrongly imply that finishing it is the plan.
        assert caps.capability_status(caps.CAP_ANNOTATION_CREATE) == caps.NOT_APPLICABLE
        assert not caps.is_usable(caps.CAP_ANNOTATION_CREATE)

    def test_runtime_existence_never_implies_a_create_capability(self):
        for family in caps.OBJECT_FAMILIES.values():
            if family.runtime_available and not family.automation_available:
                assert family.public_capabilities == (), (
                    f"{family.family} publishes capabilities despite having no automation")


class TestStorageModelIsNotRewritten:
    def test_annotation_is_reported_as_pipe_owned_state(self):
        report = caps.capability_report()
        assert report["annotation_storage_model"] == caps.MODEL_B_PIPE_OWNED_STATE
        assert report["annotation_xdata_application"] == "TG_PIPELABEL_THICK_SHOW"

    def test_no_capability_name_describes_annotation_as_entity_creation(self):
        for name, status in caps.native_capability_registry().items():
            if "annotation" in name and "create" in name:
                assert status == caps.NOT_APPLICABLE


class TestCommandInteractionProfiles:
    @pytest.mark.parametrize(
        "command,profile,automatable",
        [
            ("HZGX", caps.CommandInteractionProfile.STANDARD_POINT, True),
            ("HZSB", caps.CommandInteractionProfile.MIXED, True),
            ("DGGJ", caps.CommandInteractionProfile.STANDARD_POINT, True),
            ("GJBZ", caps.CommandInteractionProfile.NATIVE_SELECTION, False),
            ("FMFJ", caps.CommandInteractionProfile.INTERACTIVE_SAMPLER, False),
            ("DXJT", caps.CommandInteractionProfile.NATIVE_SELECTION, False),
            ("GXLJ", caps.CommandInteractionProfile.NATIVE_SELECTION, False),
        ],
    )
    def test_measured_profiles(self, command, profile, automatable):
        entry = caps.COMMAND_PROFILES[command]
        assert entry.profile == profile
        assert entry.automatable is automatable
        assert entry.evidence, "a profile without evidence is a guess"

    def test_dggj_and_gjbz_do_not_share_an_input_surface(self):
        # The whole reason DGGJ was pre-tested rather than assumed to behave like GJBZ.
        assert (caps.COMMAND_PROFILES["DGGJ"].profile
                != caps.COMMAND_PROFILES["GJBZ"].profile)

    def test_editor_command_blocking_constraint_is_documented(self):
        text = caps.EDITOR_COMMAND_IS_BLOCKING
        assert "blocks" in text
        assert "AFTER" in text, "the constraint is specifically about code placed after the call"


class TestSnapshotMerge:
    def test_defaults_are_used_when_no_live_report_exists(self):
        assert caps.merge_snapshot(None) == caps.native_capability_registry()

    def test_a_live_report_overrides_but_unknown_names_never_read_as_available(self):
        merged = caps.merge_snapshot({"capabilities": {"tianzheng_native_pipe_create": "NOT_IMPLEMENTED"}})
        assert merged["tianzheng_native_pipe_create"] == "NOT_IMPLEMENTED"
        # a name the live report did not mention keeps its registry value
        assert merged["tianzheng_native_valve_create"] == caps.NOT_IMPLEMENTED
