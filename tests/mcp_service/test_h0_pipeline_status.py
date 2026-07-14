import json
class TestH0Status:
 def test_state_exists(self):
  import os; assert os.path.exists("artifacts/state/pipeline_state.json")
 def test_state_fields(self):
  s = json.load(open("artifacts/state/pipeline_state.json",encoding="utf-8")); assert s["source_dwg_opened"] is False; assert s["production_d1_allowed"] is False