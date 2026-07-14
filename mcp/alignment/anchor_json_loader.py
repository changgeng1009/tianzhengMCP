import json, os

ANCHOR_PATH = r'D:\ExampleWorkspace\天正\artifacts\alignment\anchors_d4_6.json'

def load_anchors(path=ANCHOR_PATH):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def get_reference_points(path=ANCHOR_PATH):
    a = load_anchors(path)
    if a is None: return None
    return [(p[0], p[1]) for p in a['reference_anchor_points']]

def get_sandbox_points(path=ANCHOR_PATH):
    a = load_anchors(path)
    if a is None: return None
    return [(p[0], p[1]) for p in a['sandbox_anchor_points']]
