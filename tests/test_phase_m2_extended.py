"""Phase M2 扩展测试 — ActionBatch, ConflictDetector, ProxyDiscovery, DependencyGraph."""

import pytest
from tianzheng_interface.action_schema import (
    ActionDefinition, ActionConflict, ActionBatch,
    DependencyGraph, ConflictType,
)
from tianzheng_interface.dry_run_engine import (
    ConflictDetector, EnhancedDryRunEngine,
)
from tianzheng_interface.proxy_handler import ProxyDiscovery


class TestActionBatch:
    def test_from_actions(self):
        actions = [
            ActionDefinition(action_type="add_pipe", object_type="TDbPipe"),
            ActionDefinition(action_type="add_valve", object_type="TDbPipeValve"),
            ActionDefinition(action_type="delete_candidate", object_type="TDbPipe"),
        ]
        batch = ActionBatch.from_actions(actions, batch_id="test")
        assert batch.total_count == 3
        assert batch.high_risk_count == 1
        assert len(batch.execution_order) == 3

    def test_empty_batch(self):
        batch = ActionBatch.from_actions([])
        assert batch.total_count == 0
        assert batch.high_risk_count == 0

    def test_to_dict(self):
        batch = ActionBatch.from_actions(
            [ActionDefinition(action_type="add_pipe")], batch_id="B1"
        )
        d = batch.to_dict()
        assert d["batch_id"] == "B1"
        assert d["total_count"] == 1


class TestDependencyGraph:
    def test_add_nodes_and_resolve(self):
        g = DependencyGraph()
        a1 = ActionDefinition(action_type="add_pipe")
        a2 = ActionDefinition(action_type="connect_pipe")
        a3 = ActionDefinition(action_type="update_diameter")
        g.add_node(a1)
        g.add_node(a2)
        g.add_node(a3)
        g.add_dependency(a1.action_id, a2.action_id)
        g.add_dependency(a1.action_id, a3.action_id)
        order = g.resolve_order()
        assert a1.action_id in order
        assert order.index(a1.action_id) < order.index(a2.action_id)

    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.resolve_order() == []


class TestConflictDetector:
    def setup_method(self):
        self.detector = ConflictDetector()

    def test_no_conflicts_empty(self):
        conflicts = self.detector.detect_all([])
        assert conflicts == []

    def test_spatial_overlap(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 0, "y": 0, "z": 0},
            ),
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 10, "y": 10, "z": 0},
            ),
        ]
        conflicts = self.detector.detect_spatial(actions)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.SPATIAL_OVERLAP.value

    def test_spatial_no_overlap(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 0, "y": 0},
            ),
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 5000, "y": 5000},
            ),
        ]
        conflicts = self.detector.detect_spatial(actions)
        assert len(conflicts) == 0

    def test_diameter_mismatch(self):
        actions = [
            ActionDefinition(action_type="add_pipe", dn="DN100"),
            ActionDefinition(action_type="add_pipe", dn="DN200"),
        ]
        conflicts = self.detector.detect_diameter(actions)
        assert len(conflicts) == 1
        assert "管径不匹配" in conflicts[0].description

    def test_diameter_match(self):
        actions = [
            ActionDefinition(action_type="add_pipe", dn="DN100"),
            ActionDefinition(action_type="add_pipe", dn="DN100"),
        ]
        conflicts = self.detector.detect_diameter(actions)
        assert len(conflicts) == 0

    def test_elevation_clash(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe",
                parameters={"elevation": 3000},
            ),
            ActionDefinition(
                action_type="add_pipe",
                parameters={"elevation": 1000},
            ),
        ]
        conflicts = self.detector.detect_elevation(actions)
        assert len(conflicts) >= 1

    def test_system_mismatch(self):
        actions = [
            ActionDefinition(
                action_type="connect_pipe",
                parameters={"pipe_a_system": "给水", "pipe_b_system": "消防"},
            ),
        ]
        conflicts = self.detector.detect_system_mismatch(actions)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "high"


class TestEnhancedDryRunEngine:
    def setup_method(self):
        self.engine = EnhancedDryRunEngine()

    def test_simulate_with_conflicts(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 0, "y": 0},
            ),
            ActionDefinition(
                action_type="add_pipe", object_type="TDbPipe",
                geometry={"x": 10, "y": 10},
            ),
        ]
        result, conflicts = self.engine.simulate_with_conflicts(actions)
        assert result.total_actions == 2
        assert len(conflicts) >= 1

    def test_estimate_changes(self):
        actions = [
            ActionDefinition(action_type="add_pipe"),
            ActionDefinition(action_type="add_pipe"),
            ActionDefinition(action_type="update_diameter"),
            ActionDefinition(action_type="delete_candidate"),
        ]
        estimates = self.engine.estimate_changes(actions)
        assert estimates["add_pipe"] == 2
        assert estimates["update_diameter"] == 1
        assert estimates["delete_candidate"] == 1


class TestProxyDiscovery:
    def test_known_tianzheng(self):
        result = ProxyDiscovery.discover("TDbPipe")
        assert result.classification == "known_tianzheng"
        assert result.is_tianzheng

    def test_extended_tianzheng(self):
        result = ProxyDiscovery.discover("TDbAirDuct")
        assert result.classification == "known_tianzheng"

    def test_pattern_match_high_confidence(self):
        result = ProxyDiscovery.discover("TDbCustomThing")
        assert result.classification == "unknown_tianzheng_candidate"
        assert result.is_tianzheng

    def test_pattern_match_low_confidence(self):
        result = ProxyDiscovery.discover("TCH_OldObject")
        assert result.classification == "unknown_tianzheng_candidate"

    def test_unknown_type(self):
        result = ProxyDiscovery.discover("SomeRandomName")
        assert not result.is_tianzheng

    def test_classify_with_confidence(self):
        result, conf = ProxyDiscovery.classify_with_confidence("TDbPipe")
        assert result.is_tianzheng
        assert conf == 1.0

    def test_classify_unknown_confidence(self):
        result, conf = ProxyDiscovery.classify_with_confidence("RandomThing")
        assert conf == 0.0
