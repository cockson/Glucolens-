from typing import Dict, Any
from app.gpt.schemas import FusionPayload

def build_facts_panel(payload: FusionPayload) -> Dict[str, Any]:
    """
    Convert full fusion payload -> safe, de-identified structured facts.
    IMPORTANT: we do NOT send images/base64 to GPT.
    """
    fp = payload

    facts: Dict[str, Any] = {
        "prediction_id": fp.prediction_id,
        "threshold_used": fp.threshold_used,
        "threshold_meta": fp.threshold_meta.model_dump(),
        "fusion": fp.fusion.model_dump(),
        "modalities": {},
        "quality": {},
        "explainability": {},
    }

    # Tabular
    if fp.tabular:
        facts["modalities"]["tabular"] = {
            "model_name": fp.tabular.model_name,
            "model_version": fp.tabular.model_version,
            "predicted_label": fp.tabular.predicted_label,
            "probabilities": fp.tabular.probabilities,
        }

    # Retina
    if fp.retina:
        facts["modalities"]["retina"] = {
            "model_name": fp.retina.model_name,
            "model_version": fp.retina.model_version,
            "predicted_label": fp.retina.predicted_label,
            "probabilities": fp.retina.probabilities,
        }
        facts["quality"]["retina"] = fp.retina.quality_gate.model_dump()
        # We only send a short description of explainability method, NOT base64 image
        if fp.retina.explainability:
            facts["explainability"]["retina"] = {
                "method": fp.retina.explainability.method,
                "has_overlay": bool(fp.retina.explainability.overlay_png_base64),
            }

    # Skin
    if fp.skin:
        facts["modalities"]["skin"] = {
            "model_name": fp.skin.model_name,
            "model_version": fp.skin.model_version,
            "predicted_label": fp.skin.predicted_label,
            "probabilities": fp.skin.probabilities,
        }
        facts["quality"]["skin"] = fp.skin.quality_gate.model_dump()
        if fp.skin.explainability:
            facts["explainability"]["skin"] = {
                "method": fp.skin.explainability.method,
                "has_overlay": bool(fp.skin.explainability.overlay_png_base64),
            }

    # Genomics
    if fp.genomics:
        facts["modalities"]["genomics"] = {
            "model": fp.genomics.model,
            "predicted_label": fp.genomics.predicted_label,
            "probability": fp.genomics.probability,
        }
        if fp.genomics.explainability:
            facts["explainability"]["genomics"] = {
                "top_coefficients": fp.genomics.explainability.top_coefficients[:10],
                "note": "Top coefficients truncated to 10 for safety/conciseness.",
            }

    # High-level missing/insufficient reasons summary
    reasons = []
    if fp.fusion.final_label in ["retake_image", "insufficient_data"]:
        reasons.append(fp.fusion.reason)

    facts["summary"] = {
        "final_label": fp.fusion.final_label,
        "final_proba": fp.fusion.final_proba,
        "reason": fp.fusion.reason,
        "action": (
            "refer_for_confirmatory_testing"
            if fp.fusion.final_label == "screen_positive_refer"
            else "routine_prevention_followup"
            if fp.fusion.final_label == "screen_negative"
            else "retake_image"
            if fp.fusion.final_label == "retake_image"
            else "collect_missing_data"
        ),
        "flags": reasons,
    }

    return facts