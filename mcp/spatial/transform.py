from __future__ import annotations

import math

from mcp.spatial.models import AnchorPair, BBox2D, Point2D, Transform2D


class TransformEstimator:
    def estimate_from_anchor_pairs(self, anchor_pairs: list[AnchorPair]) -> Transform2D:
        if not anchor_pairs:
            return Transform2D(
                "unknown",
                [],
                0.0,
                None,
                {"warning": "not enough anchor pairs"},
            )

        if len(anchor_pairs) == 1:
            pair = anchor_pairs[0]
            dx = pair.target_anchor.point.x - pair.reference_anchor.point.x
            dy = pair.target_anchor.point.y - pair.reference_anchor.point.y
            return Transform2D(
                "translation",
                [[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
                round(pair.confidence * 0.9, 4),
                0.0,
                {"anchor_pair_count": 1},
            )

        first = anchor_pairs[0]
        dx = first.target_anchor.point.x - first.reference_anchor.point.x
        dy = first.target_anchor.point.y - first.reference_anchor.point.y
        residuals = [
            math.hypot(
                (pair.reference_anchor.point.x + dx) - pair.target_anchor.point.x,
                (pair.reference_anchor.point.y + dy) - pair.target_anchor.point.y,
            )
            for pair in anchor_pairs
        ]
        residual = sum(residuals) / len(residuals)
        avg_conf = sum(pair.confidence for pair in anchor_pairs) / len(anchor_pairs)
        confidence = max(0.0, min(1.0, avg_conf / (1.0 + residual)))
        return Transform2D(
            "translation",
            [[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]],
            round(confidence, 4),
            round(residual, 4),
            {"anchor_pair_count": len(anchor_pairs)},
        )

    def apply_point(self, transform: Transform2D, point: Point2D) -> Point2D:
        if transform.transform_type == "unknown" or not transform.matrix:
            return point
        matrix = transform.matrix
        x = matrix[0][0] * point.x + matrix[0][1] * point.y + matrix[0][2]
        y = matrix[1][0] * point.x + matrix[1][1] * point.y + matrix[1][2]
        return Point2D(round(x, 6), round(y, 6))

    def apply_bbox(self, transform: Transform2D, bbox: BBox2D) -> BBox2D:
        points = [
            self.apply_point(transform, Point2D(bbox.min_x, bbox.min_y)),
            self.apply_point(transform, Point2D(bbox.max_x, bbox.max_y)),
        ]
        return BBox2D(
            min(point.x for point in points),
            min(point.y for point in points),
            max(point.x for point in points),
            max(point.y for point in points),
        )

    def apply_points(self, transform: Transform2D, points: list[Point2D]) -> list[Point2D]:
        return [self.apply_point(transform, point) for point in points]
