import pathlib
td = pathlib.Path(r'C:\Users\example-user\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw\tests')
td.mkdir(exist_ok=True)

def w(name, content):
    (td / name).write_text(content.lstrip(), encoding='utf-8')
    print('Created:', name)

w('test_prompt_classifier_start.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: prompt classifier start point tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.prompt_classifier import classify_lastprompt

def test_start_point_with_cancel():
    r = classify_lastprompt("\u8bf7\u8f93\u5165\u8d77\u70b9:<\u9000\u51fa>*\u53d6\u6d88*")
    assert r.prompt_type == "start_point_prompt"
    assert r.is_draw_workflow is True
    assert r.was_cancelled is True

def test_start_point_simple():
    r = classify_lastprompt("\u8bf7\u8f93\u5165\u8d77\u70b9")
    assert r.prompt_type == "start_point_prompt"
''')
print('1/12')

w('test_prompt_classifier_conversion.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: prompt classifier conversion tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.prompt_classifier import classify_lastprompt

def test_conversion_prompt():
    r = classify_lastprompt("\u9009\u62e9\u9700\u8981\u8f6c\u5316\u7684\u56fe\u5143<\u9000\u51fa>")
    assert r.prompt_type == "conversion_prompt"
    assert r.is_conversion_workflow is True

def test_convert_keyword():
    r = classify_lastprompt("\u8f6c\u5316\u56fe\u5143")
    assert r.prompt_type == "conversion_prompt"
''')
print('2/12')

w('test_prompt_classifier_edge.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: prompt classifier edge cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.prompt_classifier import classify_lastprompt, classify_recording_pair

def test_empty_prompt():
    r = classify_lastprompt("")
    assert r.prompt_type == "empty_prompt"

def test_unknown_prompt():
    r = classify_lastprompt("\u547d\u4ee4: _u GROUP")
    assert r.prompt_type == "unknown_prompt"

def test_recording_pair_draw():
    r = classify_recording_pair(
        before_prompt="\u547d\u4ee4: _u GROUP",
        after_prompt="\u8bf7\u8f93\u5165\u8d77\u70b9")
    assert r.draw_workflow_detected is True
    assert r.assessment == "draw_workflow_observed"
''')
print('3/12')

w('test_candidate_registry_hsxg.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: candidate registry hsxg strong draw candidate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry

def test_hsxg_strong():
    entries = [{"item_name":"\u53cc\u7ebf\u6c34\u7ba1","caption":"\u7ed8\u5236\u53cc\u7ebf\u6c34\u7ba1","help_string":"\u7ed8\u5236\u53cc\u7ebf\u6c34\u7ba1","macro_clean":"hsxg","command_tokens":["hsxg"]}]
    r = build_candidate_registry(entries)
    assert len(r.strong_draw_candidates) >= 1
    assert r.strong_draw_candidates[0]["command"] == "hsxg"
    assert r.strong_draw_candidates[0]["d0_3_candidate"] is True

def test_hsxg_from_help():
    entries = [{"item_name":"ID_DRAWWATERPIPE","caption":"","help_string":"\u7ed8\u5236\u53cc\u7ebf\u6c34\u7ba1","macro_clean":"","command_tokens":[]}]
    r = build_candidate_registry(entries)
    assert len(r.strong_draw_candidates) >= 1
''')
print('4/12')

w('test_candidate_registry_hzdg.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: candidate registry hzdg probable draw candidate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry

def test_hzdg_probable():
    entries = [{"item_name":"\u7ed8\u5236\u591a\u7ba1","help_string":"\u540c\u65f6\u7ed8\u5236\u5e73\u884c\u7684\u591a\u6839\u7ba1\u7ebf","macro_clean":"hzdg","command_tokens":["hzdg"]}]
    r = build_candidate_registry(entries)
    assert len(r.probable_draw_candidates) >= 1
    assert r.probable_draw_candidates[0]["command"] == "hzdg"
    assert r.probable_draw_candidates[0]["candidate_role"] == "multi_pipe_draw"
''')
print('5/12')

w('test_candidate_registry_fmfj.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: candidate registry fmfj valve candidate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry

def test_fmfj_valve():
    entries = [{"item_name":"\u9600\u95e8\u9600\u4ef6","help_string":"\u5728\u7ba1\u7ebf\u4e0a\u63d2\u5165\u9600\u95e8\u56fe\u5757","macro_clean":"FMFJ","command_tokens":["FMFJ"]}]
    r = build_candidate_registry(entries)
    assert len(r.valve_candidates) >= 1
    assert r.valve_candidates[0]["command"] == "fmfj"
''')
print('6/12')

w('test_candidate_registry_forbidden.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: candidate registry forbidden tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry

def test_pc2t20_forbidden():
    entries = [{"item_name":"\u8f6c\u5316","help_string":"\u9009\u62e9\u9700\u8981\u8f6c\u5316\u7684\u56fe\u5143","macro_clean":"PC2T20","command_tokens":["PC2T20"]}]
    r = build_candidate_registry(entries)
    assert len(r.forbidden_candidates) >= 1
    assert r.forbidden_candidates[0]["risk"] == "forbidden"

def test_conversion_not_strong():
    entries = [{"item_name":"\u8f6c\u5316\u7ba1\u7ebf","help_string":"\u9009\u62e9\u9700\u8981\u8f6c\u5316\u7684\u56fe\u5143","macro_clean":"PC2T20","command_tokens":["PC2T20"]}]
    r = build_candidate_registry(entries)
    assert len(r.strong_draw_candidates) == 0
    assert len(r.forbidden_candidates) >= 1
''')
print('7/12')

w('test_candidate_registry_noise.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: candidate registry noise filtering."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry

def test_dimlinear_not_candidate():
    entries = [{"item_name":"Linear Dim","command_tokens":["_DIMLINEAR"],"macro_clean":"_dimlinear"}]
    r = build_candidate_registry(entries)
    assert len(r.strong_draw_candidates) == 0
    assert len(r.probable_draw_candidates) == 0
    assert len(r.valve_candidates) == 0
''')
print('8/12')

w('test_candidate_confirmation_readiness.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: D0.3 readiness tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_registry import build_candidate_registry, assess_d0_3_readiness

def test_readiness_hsxg_start_point():
    entries = [{"item_name":"\u53cc\u7ebf\u6c34\u7ba1","macro_clean":"hsxg","command_tokens":["hsxg"]}]
    r = build_candidate_registry(entries)
    cls = {"after_classification": {"prompt_type": "start_point_prompt", "is_draw_workflow": True, "was_cancelled": False}}
    readiness, _ = assess_d0_3_readiness(r, cls)
    assert readiness == "candidate_ready_but_requires_user_approval"

def test_readiness_no_hsxg():
    entries = [{"item_name":"unknown"}]
    r = build_candidate_registry(entries)
    cls = {"after_classification": {"prompt_type": "start_point_prompt"}}
    readiness, _ = assess_d0_3_readiness(r, cls)
    assert readiness == "not_ready"

def test_readiness_conversion():
    entries = [{"item_name":"\u53cc\u7ebf\u6c34\u7ba1","macro_clean":"hsxg","command_tokens":["hsxg"]}]
    r = build_candidate_registry(entries)
    cls = {"after_classification": {"prompt_type": "conversion_prompt", "is_draw_workflow": False}}
    readiness, reasons = assess_d0_3_readiness(r, cls)
    assert readiness == "not_ready"
''')
print('9/12')

w('test_candidate_confirmation_report.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: confirmation report tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts.tianzheng.candidate_confirmation_report import generate_confirmation_report

def test_report_has_candidate_ranking():
    registry = {"strong_draw_candidates": [{"command":"hsxg","display_name":"\u53cc\u7ebf\u6c34\u7ba1","candidate_role":"pipe_draw","confidence":"high","d0_3_candidate":True,"risk":"candidate"}], "probable_draw_candidates":[], "valve_candidates":[], "label_candidates":[], "connection_candidates":[]}
    report = generate_confirmation_report(registry, {"after_classification":{"prompt_type":"start_point_prompt","is_draw_workflow":True,"was_cancelled":False,"is_conversion_workflow":False}}, {}, "candidate_ready", ["hsxg found"])
    assert "Candidate Ranking" in report
    assert "hsxg" in report

def test_report_has_forbidden():
    registry = {"strong_draw_candidates":[],"probable_draw_candidates":[],"valve_candidates":[],"label_candidates":[],"connection_candidates":[],"forbidden_candidates":[{"command":"pc2t20","display_name":"\u8f6c\u5316","risk":"forbidden"}]}
    report = generate_confirmation_report(registry, {"after_classification":{}}, {}, "not_ready", [])
    assert "Forbidden Candidates" in report
    assert "pc2t20" in report
''')
print('10/12')

w('test_d023_safety.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: safety tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

def test_no_save_in_d023():
    base = Path(__file__).parent.parent / "scripts" / "tianzheng"
    for name in ["prompt_classifier", "candidate_registry", "candidate_confirmation_report", "manual_candidate_confirmation"]:
        target = base / (name + ".py")
        if target.exists():
            src = target.read_text(encoding="utf-8")
            assert ".Save(" not in src, name + ": .Save( found"
            assert "SaveAs" not in src, name + ": SaveAs found"
            assert "CopyObjects" not in src, name + ": CopyObjects found"

def test_d023_py_compile():
    import py_compile
    base = Path(__file__).parent.parent / "scripts" / "tianzheng"
    for name in ["prompt_classifier", "candidate_registry", "candidate_confirmation_report", "manual_candidate_confirmation"]:
        py_compile.compile(str(base / (name + ".py")), doraise=True)
''')
print('11/12')

w('test_d023_py_compile_all.py', r'''
# -*- coding: utf-8 -*-
"""D0.2.3: py_compile all new modules."""
import py_compile, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

def test_all_modules_compile():
    base = Path(__file__).parent.parent / "scripts" / "tianzheng"
    for name in ["prompt_classifier", "candidate_registry", "candidate_confirmation_report", "manual_candidate_confirmation"]:
        py_compile.compile(str(base / (name + ".py")), doraise=True)
''')
print('12/12')
print('DONE')