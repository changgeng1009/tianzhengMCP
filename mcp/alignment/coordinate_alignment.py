import json, math, datetime

class CoordinateAligner:
    def __init__(self):
        self.reference_anchors = []
        self.target_anchors = []
        self.transform_matrix = None
        self.scale_x = 1.0; self.scale_y = 1.0
        self.offset_x = 0.0; self.offset_y = 0.0
        self.confidence = 0.0

    def set_reference_anchors(self, points):
        self.reference_anchors = [(float(p[0]), float(p[1])) for p in points]

    def set_target_anchors(self, points):
        self.target_anchors = [(float(p[0]), float(p[1])) for p in points]

    def compute_2point_transform(self, ref_points, target_points):
        if len(ref_points) < 2 or len(target_points) < 2:
            return None
        r0, r1 = ref_points[0], ref_points[1]
        t0, t1 = target_points[0], target_points[1]
        dx_r = r1[0] - r0[0]; dy_r = r1[1] - r0[1]
        dx_t = t1[0] - t0[0]; dy_t = t1[1] - t0[1]
        self.scale_x = dx_t / dx_r if dx_r != 0 else dy_t / dy_r if dy_r != 0 else 1.0
        self.scale_y = dy_t / dy_r if dy_r != 0 else dx_t / dx_r if dx_r != 0 else 1.0
        if abs(self.scale_x - self.scale_y) > 0.5 * max(abs(self.scale_x), abs(self.scale_y), 1):
            self.confidence = 0.3
        else:
            self.confidence = 0.7
        self.offset_x = t0[0] - self.scale_x * r0[0]
        self.offset_y = t0[1] - self.scale_y * r0[1]
        return self.to_dict()

    def transform_point(self, x, y):
        return (self.scale_x * x + self.offset_x, self.scale_y * y + self.offset_y)

    def transform_batch(self, points):
        return [self.transform_point(p[0], p[1]) for p in points]

    def to_dict(self):
        return {
            'scale_x': self.scale_x, 'scale_y': self.scale_y,
            'offset_x': self.offset_x, 'offset_y': self.offset_y,
            'confidence': self.confidence,
            'reference_anchors': self.reference_anchors,
            'target_anchors': self.target_anchors
        }

def pdf_to_dwg_aligner(pdf_page_width, pdf_page_height):
    dwg_width = 42000
    dwg_height = 59400
    aligner = CoordinateAligner()
    aligner.set_reference_anchors([(0, 0), (pdf_page_width, pdf_page_height)])
    aligner.set_target_anchors([(0, 0), (dwg_width, dwg_height)])
    aligner.compute_2point_transform(
        [(0, 0), (pdf_page_width, pdf_page_height)],
        [(0, 0), (dwg_width, dwg_height)]
    )
    return aligner

def generate_alignment_report(pdf_geom_path, output_path):
    pdf = json.load(open(pdf_geom_path, encoding='utf-8'))
    page = pdf['pages'][0]
    aligner = pdf_to_dwg_aligner(page['width'], page['height'])
    report = {
        'phase': 'D4', 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'pdf_dimensions': {'width': page['width'], 'height': page['height']},
        'dwg_target_extents': {'width': 42000, 'height': 59400},
        'alignment': aligner.to_dict(),
        'source_dwg_opened': False, 'd1_allowed': False
    }
    json.dump(report, open(output_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return report
