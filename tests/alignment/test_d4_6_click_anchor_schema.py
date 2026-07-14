import json, pytest
from pathlib import Path

class TestD46Schema:
    def test_calibrate_with_manual_points(self):
        from mcp.alignment.anchor_transform_solver import calibrate
        t = calibrate([(0,0),(100,0)], [(0,0),(150,0)])
        assert t is not None
        assert abs(t['scale_x']-1.5)<0.1

    def test_3point_transform(self):
        from mcp.alignment.anchor_transform_solver import calibrate
        t = calibrate([(0,0),(100,0),(0,100)], [(0,0),(200,0),(0,200)])
        assert t is not None
        assert abs(t['scale_x']-2.0)<0.1

    def test_confidence_high_for_perfect(self):
        from mcp.alignment.anchor_transform_solver import solve_2point_affine
        t = solve_2point_affine([(0,0),(100,0)], [(0,0),(100,0)])
        assert t['confidence'] > 0.90

    def test_click_anchor_module_loads(self):
        from mcp.alignment.click_anchor_capture import _select_entity_center
        assert callable(_select_entity_center)
