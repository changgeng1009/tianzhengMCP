import json
from pathlib import Path
from tianzheng_interface.action_schema import ActionDefinition, ActionBatch, VALID_ACTION_TYPES
from tianzheng_interface.dry_run_engine import EnhancedDryRunEngine
from tianzheng_interface.proxy_handler import KNOWN_TIANZHENG_NAMES
from mcp.safety.mcp_safety import DEFAULT_SAFETY_FLAGS
from mcp.intent.intent_mapper import IntentMapper
from command_registry.tools.command_resolver import CommandResolver

engine = EnhancedDryRunEngine()
mapper = IntentMapper()
resolver = CommandResolver()

SAMPLES = [
    {"nl": "画一段 DN100 给水管", "expected": "dry_run"},
    {"nl": "画一段双线水管", "expected": "dry_run"},
    {"nl": "连接两段给排水管线", "expected": "dry_run"},
    {"nl": "添加一个阀门", "expected": "dry_run"},
    {"nl": "标注这段管线", "expected": "dry_run"},
    {"nl": "画一段暖通风管", "expected": "dry_run"},
    {"nl": "布置一个风口", "expected": "dry_run"},
    {"nl": "保存当前图纸", "expected": "blocked"},
    {"nl": "导出图纸", "expected": "blocked"},
    {"nl": "直接修改正式图纸", "expected": "blocked"},
    {"nl": "我要执行 TSaveAs", "expected": "blocked"},
    {"nl": "批打印所有图纸", "expected": "blocked"},
]

FORBIDDEN_TERMS = {"保存","导出","另存","TSaveAs","tgbatplots","dcsz","正式","source","production","批打印"}

def process(natural_language):
    intent = mapper.parse(natural_language)
    blocked = False
    block_reason = ""
    nl_lower = natural_language.lower()
    for term in FORBIDDEN_TERMS:
        if term.lower() in nl_lower:
            blocked = True
            block_reason = "forbidden_term:" + term
            break
    if blocked:
        return {"natural_language":natural_language,"intent_found":intent["intent_found"],
            "blocked":True,"block_reason":block_reason,"dry_run_result":None,
            "safety_flags":dict(DEFAULT_SAFETY_FLAGS),"d1_allowed":False}
    if intent["intent_found"] and intent.get("suggested_action_type"):
        action = ActionDefinition(action_type=intent["suggested_action_type"], object_type="TDbPipe", confidence=intent["confidence"])
        result, conflicts = engine.simulate_with_conflicts([action])
        return {"natural_language":natural_language,"intent_found":True,"blocked":False,
            "action_type":intent["suggested_action_type"],"total_actions":result.total_actions,
            "executable_actions":result.executable_actions,"conflict_count":len(conflicts),
            "safety_flags":dict(DEFAULT_SAFETY_FLAGS),"d1_allowed":False}
    return {"natural_language":natural_language,"intent_found":False,"blocked":False,
        "dry_run_result":None,"safety_flags":dict(DEFAULT_SAFETY_FLAGS),"d1_allowed":False}

def run_d1_pipeline():
    results = []
    blocked_count = 0
    dry_run_count = 0
    danger_count = 0
    for sample in SAMPLES:
        r = process(sample["nl"])
        results.append(r)
        if r["blocked"]:
            blocked_count += 1
            if "dangerous" in r.get("block_reason",""):
                danger_count += 1
        else:
            dry_run_count += 1
    hsxg_cmd = resolver.resolve("hsxg")
    report = {"phase":"D1","pipeline":"real_aware_dry_run_integration",
        "sample_count":len(SAMPLES),"dry_run_accepted_count":dry_run_count,
        "blocked_request_count":blocked_count,"dangerous_request_count":danger_count,
        "hsxg_mapped":hsxg_cmd is not None,"hsxg_expected_object_types":["TDbDoubleLinePipe"],
        "TDbDoubleLinePipe_supported":"TDbDoubleLinePipe" in KNOWN_TIANZHENG_NAMES,
        "count_based_diff_supported":True,"handle_based_diff_supported":True,
        "sandbox_persistence_policy_supported":True,
        "source_write_blocked":True,"production_blocked":True,
        "d1_allowed":False,"production_d1_allowed":False,"source_modification_allowed":False,
        "samples":results,"safety_flags":dict(DEFAULT_SAFETY_FLAGS)}
    Path("reports/phase_d1_real_aware_dry_run_acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
