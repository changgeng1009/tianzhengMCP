from __future__ import annotations

from mcp.vision_templates.models import ClassifiedSymbol, TemplateMatch


SYMBOL_TYPE_MAP = {
    "sprinkler": "sprinkler_candidate",
    "valve": "valve_candidate",
    "fitting": "fitting_candidate",
    "legend": "legend_candidate",
}


def classify_symbols_from_matches(
    matches: list[TemplateMatch],
    options: dict | None = None,
) -> list[ClassifiedSymbol]:
    symbols: list[ClassifiedSymbol] = []
    for match in matches:
        if match.confidence < 0.60:
            continue
        band = "high" if match.confidence >= 0.85 else "review"
        symbol_type = SYMBOL_TYPE_MAP.get(match.template_type, f"{match.template_type}_candidate")
        symbols.append(
            ClassifiedSymbol(
                symbol_id=f"sym_{match.match_id}",
                symbol_type=symbol_type,
                bbox=list(match.bbox),
                center=list(match.center),
                confidence=float(match.confidence),
                matched_template_id=match.template_id,
                method=match.method,
                metadata={
                    "confidence_band": band,
                    "template_type": match.template_type,
                    **dict(match.metadata),
                },
                warnings=list(match.warnings),
            )
        )
    return symbols

