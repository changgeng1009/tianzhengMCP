from mcp.alignment.anchor_transform_solver import solve_2point_affine, solve_3point_affine

class TestD42Solver:
    def test_2point_identity(self):
        r = solve_2point_affine([(0,0),(100,0)], [(0,0),(100,0)])
        assert r is not None
        assert abs(r['scale_x']-1.0)<0.01
        assert abs(r['rotation_deg'])<0.1

    def test_2point_scale(self):
        r = solve_2point_affine([(0,0),(100,0)], [(0,0),(200,0)])
        assert abs(r['scale_x']-2.0)<0.1

    def test_3point_affine(self):
        r = solve_3point_affine([(0,0),(100,0),(0,100)], [(0,0),(200,0),(0,200)])
        assert r is not None
        assert abs(r['scale_x']-2.0)<0.1

class TestD42Confidence:
    def test_perfect_confidence(self):
        r = solve_2point_affine([(0,0),(100,0)], [(0,0),(100,0)])
        assert r['confidence'] > 0.95

    def test_threshold_check(self):
        r = solve_2point_affine([(0,0),(100,0)], [(0,0),(100,0)])
        assert r['confidence'] >= 0.85
