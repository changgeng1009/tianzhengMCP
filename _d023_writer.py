import pathlib
base = pathlib.Path(r'C:\Users\example-user\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw\scripts\tianzheng')

# candidate_registry.py
code = '''# -*- coding: utf-8 -*-
"""D0.2.3: Tianzheng water candidate registry."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class CandidateCommand:
    command: str = ""
    display_name: str = ""
    candidate_role: str = "unknown"
    confidence: str = "low"
    risk: str = "candidate_not_executed"
    d0_3_candidate: bool = False
    can_be_tested_later: bool = False
    source_entries: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    def to_dict(self):
        return {"command":self.command,"display_name":self.display_name,"candidate_role":self.candidate_role,"confidence":self.confidence,"risk":self.risk,"d0_3_candidate":self.d0_3_candidate,"can_be_tested_later":self.can_be_tested_later,"source_entry_count":len(self.source_entries),"notes":self.notes}

@dataclass
class CandidateRegistry:
    strong_draw_candidates: list[dict] = field(default_factory=list)
    probable_draw_candidates: list[dict] = field(default_factory=list)
    valve_candidates: list[dict] = field(default_factory=list)
    label_candidates: list[dict] = field(default_factory=list)
    connection_candidates: list[dict] = field(default_factory=list)
    forbidden_candidates: list[dict] = field(default_factory=list)
    noise_entries: list[dict] = field(default_factory=list)
    total_entries_scanned: int = 0
    warnings: list[str] = field(default_factory=list)
    def to_dict(self):
        return {"strong_draw_candidates":self.strong_draw_candidates,"probable_draw_candidates":self.probable_draw_candidates,"valve_candidates":self.valve_candidates,"label_candidates":self.label_candidates,"connection_candidates":self.connection_candidates,"forbidden_candidates":self.forbidden_candidates,"noise_entries":self.noise_entries[:20],"total_entries_scanned":self.total_entries_scanned,"warnings":self.warnings}

STRONG_DRAW_RULES = [("hsxg",["双线水管","绘制双线水管"])]
PROBABLE_DRAW_RULES = [("hzdg",["绘制多管","多根管线"])]
VALVE_RULES = [("fmfj",["阀门阀件","阀门","阀件","FMFJ"])]
LABEL_RULES = [("lgbz",["管线标注","管径标注","LGBZ"])]
CONNECTION_RULES = [("gxlj",["管线连接","GXLJ"])]
FORBIDDEN_RULES = [("PC2T20",["转化","转换","选择需要转化的图元"])]
ACAD_NOISE_COMMANDS = frozenset({"_DIMLINEAR","_DIMALIGNED","_DIMANGULAR","_DIMRADIUS","_DIMDIAMETER","_REVCLOUD","_TEXTEDIT","_MTEDIT","_DDEDIT","_PROPERTIES","_MATCHPROP","_LAYER","_LAYERP","_STYLE","_UNITS","_LIMITS","_REGEN","_REGENALL","_ZOOM","_PAN","_REDRAW","_LINE","_CIRCLE","_ARC","_RECTANG","_PLINE","_SPLINE","_ELLIPSE","_HATCH","_BHATCH","_TEXT","_MTEXT","_INSERT","_BLOCK"})

def build_candidate_registry(macro_entries: list[dict]) -> CandidateRegistry:
    registry = CandidateRegistry()
    registry.total_entries_scanned = len(macro_entries)
    for entry in macro_entries:
        caption = entry.get("caption","") or ""
        item_name = entry.get("item_name","") or ""
        help_str = entry.get("help_string","") or ""
        macro_clean = entry.get("macro_clean","") or ""
        tokens = [t.upper() for t in (entry.get("command_tokens",[]) or [])]
        text = f"{item_name} {caption} {help_str} {macro_clean} {' '.join(tokens)}".lower()
        combined = text + " " + " ".join(tokens)
        matched = False
        for cmd, keywords in FORBIDDEN_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.forbidden_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="conversion_or_selection",confidence="high",risk="forbidden",d0_3_candidate=False,source_entries=[entry],notes=["Forbidden: conversion/selection command"]).to_dict())
                matched = True; break
        if matched: continue
        for cmd, keywords in STRONG_DRAW_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.strong_draw_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="pipe_draw",confidence="high",risk="candidate_not_executed",d0_3_candidate=True,source_entries=[entry],notes=["Strong pipe draw candidate"]).to_dict())
                matched = True; break
        if matched: continue
        for cmd, keywords in PROBABLE_DRAW_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.probable_draw_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="multi_pipe_draw",confidence="medium_high",risk="candidate_not_executed",d0_3_candidate=True,source_entries=[entry]).to_dict())
                matched = True; break
        if matched: continue
        for cmd, keywords in VALVE_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.valve_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="valve_insert",confidence="medium",risk="candidate_not_executed",d0_3_candidate=False,can_be_tested_later=True,source_entries=[entry]).to_dict())
                matched = True; break
        if matched: continue
        for cmd, keywords in LABEL_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.label_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="pipe_label",confidence="medium",risk="candidate_not_executed",d0_3_candidate=False,source_entries=[entry]).to_dict())
                matched = True; break
        if matched: continue
        for cmd, keywords in CONNECTION_RULES:
            if cmd.upper() in combined.upper() or any(kw.lower() in combined.lower() for kw in keywords):
                registry.connection_candidates.append(CandidateCommand(command=cmd.lower(),display_name=keywords[0],candidate_role="pipe_connect",confidence="medium",risk="candidate_not_executed",d0_3_candidate=False,source_entries=[entry]).to_dict())
                matched = True; break
        if matched: continue
        is_noise = False
        for t in tokens:
            clean = t.strip("_")
            if clean in ACAD_NOISE_COMMANDS: is_noise = True; break
            if clean.startswith("_DIM") or clean.startswith("_TEXT") or clean.startswith("_MT"): is_noise = True; break
        if is_noise: registry.noise_entries.append(entry)
    return registry

def assess_d0_3_readiness(registry: CandidateRegistry, recording_pair_cls: dict) -> tuple:
    reasons = []
    after_cls = recording_pair_cls.get("after_classification", {})
    has_hsxg = len(registry.strong_draw_candidates) > 0
    is_start_point = after_cls.get("prompt_type") == "start_point_prompt"
    is_conversion = after_cls.get("prompt_type") == "conversion_prompt"
    was_cancelled = after_cls.get("was_cancelled", False)
    if not has_hsxg: reasons.append("hsxg not found in strong draw candidates")
    if not is_start_point: reasons.append("After prompt is not start_point_prompt")
    if is_conversion: reasons.append("After prompt is conversion_prompt")
    if has_hsxg and is_start_point and not is_conversion:
        readiness = "candidate_ready_but_was_cancelled" if was_cancelled else "candidate_ready_but_requires_user_approval"
    else:
        readiness = "not_ready"
    return readiness, reasons
'''
base.joinpath('candidate_registry.py').write_text(code, encoding='utf-8')
print('Created candidate_registry.py')
