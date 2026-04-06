from typing import Any


def build_facts_panel(payload: dict[str, Any]) -> dict[str, Any]:
    fusion = payload.get("fusion") or {}
    tabular = payload.get("tabular") or {}
    retina = payload.get("retina") or {}
    skin = payload.get("skin") or {}
    genomics = payload.get("genomics") or {}

    facts: dict[str, Any] = {
        "prediction_id": payload.get("prediction_id"),
        "threshold_used": payload.get("threshold_used"),
        "threshold_meta": payload.get("threshold_meta") or {},
        "screening_plan": payload.get("screening_plan") or {},
        "fusion": fusion,
        "modalities": {},
        "quality": {},
        "explainability": {},
    }

    if tabular:
        facts["modalities"]["tabular"] = {
            "model_name": tabular.get("model_name"),
            "model_version": tabular.get("model_version"),
            "predicted_label": tabular.get("predicted_label"),
            "probabilities": tabular.get("probabilities") or {},
        }
        if payload.get("tabular_inputs"):
            facts["tabular_inputs"] = payload.get("tabular_inputs")

    if retina:
        facts["modalities"]["retina"] = {
            "model_name": retina.get("model_name"),
            "model_version": retina.get("model_version"),
            "predicted_label": retina.get("predicted_label"),
            "probabilities": retina.get("probabilities") or {},
        }
        facts["quality"]["retina"] = retina.get("quality_gate") or {}
        if retina.get("explainability"):
            facts["explainability"]["retina"] = {
                "method": retina["explainability"].get("method"),
                "has_overlay": bool(retina["explainability"].get("overlay_png_base64")),
            }

    if skin:
        facts["modalities"]["skin"] = {
            "model_name": skin.get("model_name"),
            "model_version": skin.get("model_version"),
            "predicted_label": skin.get("predicted_label"),
            "probabilities": skin.get("probabilities") or {},
        }
        facts["quality"]["skin"] = skin.get("quality_gate") or {}
        if skin.get("explainability"):
            facts["explainability"]["skin"] = {
                "method": skin["explainability"].get("method"),
                "has_overlay": bool(skin["explainability"].get("overlay_png_base64")),
            }

    if genomics:
        facts["modalities"]["genomics"] = {
            "model_name": genomics.get("model_name") or genomics.get("model"),
            "model_version": genomics.get("model_version"),
            "predicted_label": genomics.get("predicted_label"),
            "probability": genomics.get("probability"),
        }
        if genomics.get("explainability"):
            facts["explainability"]["genomics"] = {
                "top_coefficients": (genomics["explainability"].get("top_coefficients") or [])[:10],
            }

    facts["summary"] = {
        "final_label": fusion.get("final_label"),
        "final_proba": fusion.get("final_proba"),
        "reason": fusion.get("reason"),
    }
    return facts
