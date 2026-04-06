import datetime as dt
import json
import os
from typing import Any


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS = os.path.join(REPO_ROOT, "artifacts")


def _load_json(*parts: str) -> dict[str, Any]:
    path = os.path.join(ARTIFACTS, *parts)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_model_audit() -> dict[str, Any]:
    tab_perf = _load_json("tabular", "performance.json")
    tab_card = _load_json("tabular", "modelcard.json")
    fusion_perf = _load_json("fusion", "performance.json")
    retina_perf = _load_json("retina", "performance.json")
    retina_card = _load_json("retina", "modelcard.json")
    skin_card = _load_json("skin", "modelcard.json")
    genomics_card = _load_json("genomics", "model_card.json")

    models = [
        {
            "modality": "tabular",
            "model_name": tab_card.get("model_name"),
            "model_version": tab_card.get("model_version"),
            "decision": "retain_core",
            "screening_role": "Primary structured screener and fallback model.",
            "metrics": {
                "auroc": tab_perf.get("best", {}).get("oof", {}).get("auroc"),
                "brier": tab_perf.get("best", {}).get("oof", {}).get("brier"),
                "ece": tab_perf.get("best", {}).get("oof", {}).get("ece_diabetic_vs_rest"),
            },
            "rationale": [
                "Best aligned with screening inputs available at first contact.",
                "Already supports calibrated probabilities and explainability.",
                "Needs real external validation before treating the synthetic training performance as deployment-grade.",
            ],
            "risks": [
                "No site-held-out external validation artifact is present.",
                "Very high performance is likely optimistic relative to real-world data.",
            ],
        },
        {
            "modality": "fusion",
            "model_name": "fusion_logreg_v3",
            "model_version": _load_json("fusion", "registry.json").get("current", {}).get("model_version"),
            "decision": "retain_primary",
            "screening_role": "Primary multimodal screening decision engine with tabular fallback.",
            "metrics": {
                "auroc": fusion_perf.get("metrics_summary", {}).get("auroc"),
                "brier": fusion_perf.get("metrics_summary", {}).get("brier"),
                "accuracy": fusion_perf.get("metrics_summary", {}).get("accuracy"),
            },
            "rationale": [
                "Best fit for program-level screening because it degrades gracefully to tabular-only operation.",
                "Accepts optional retina, skin, and genomics evidence without blocking the base screening pathway.",
            ],
            "risks": [
                "Perfect or near-perfect holdout metrics suggest the current fusion dataset is too easy or not clinically representative.",
                "Fusion still depends on the validity of the underlying tabular signal.",
            ],
        },
        {
            "modality": "retina",
            "model_name": retina_card.get("model_name"),
            "model_version": retina_card.get("model_version"),
            "decision": "retain_adjunct",
            "screening_role": "Adjunct escalation signal when fundus images are available and pass quality gating.",
            "metrics": {
                "auroc": retina_perf.get("val", {}).get("auroc"),
                "brier": retina_perf.get("val", {}).get("brier"),
                "ece": retina_perf.get("val", {}).get("ece"),
                "n_validation": retina_perf.get("val", {}).get("n"),
            },
            "rationale": [
                "Strong image performance and explicit quality gate make it useful as a supportive modality.",
                "Best used to strengthen referral confidence, not to replace the core screener.",
            ],
            "risks": [
                "Validation set is small and heavily positive-skewed.",
                "Retina findings are more proximal to diabetic eye disease than to general future diabetes screening.",
            ],
        },
        {
            "modality": "skin",
            "model_name": skin_card.get("model_name"),
            "model_version": skin_card.get("model_version"),
            "decision": "retain_adjunct_with_caution",
            "screening_role": "Optional proxy signal when acanthosis-related skin evidence is captured well.",
            "metrics": {
                "auroc": skin_card.get("metrics_val", {}).get("auroc"),
                "brier": skin_card.get("metrics_val", {}).get("brier"),
                "accuracy": skin_card.get("metrics_val", {}).get("accuracy"),
            },
            "rationale": [
                "Useful as a low-cost adjunct when skin findings are part of the workflow.",
                "Can contribute to fusion without being mandatory.",
            ],
            "risks": [
                "No dedicated performance.json artifact is present, which weakens governance.",
                "Skin findings are indirect proxies and should not drive standalone screening intervals.",
            ],
        },
        {
            "modality": "genomics",
            "model_name": genomics_card.get("model_name"),
            "model_version": genomics_card.get("model_version"),
            "decision": "retain_research_only",
            "screening_role": "Optional enrichment or research-use feature block, not a primary production screener.",
            "metrics": {
                "auc": genomics_card.get("metrics_oof", {}).get("auc"),
                "brier": genomics_card.get("metrics_oof", {}).get("brier"),
                "positive_rate": genomics_card.get("training", {}).get("positive_rate"),
                "n_samples": genomics_card.get("training", {}).get("n_samples"),
            },
            "rationale": [
                "Current artifact mixes SNPs with Age, BMI, and HbA1c, so it is not a clean standalone genomics signal.",
                "Extreme class imbalance makes the headline metrics unreliable for frontline screening decisions.",
            ],
            "risks": [
                "Positive rate of 0.974 is too skewed for confident deployment decisions.",
                "The current genomics model should not control 3/6/12-month screening cadence.",
            ],
        },
    ]

    return {
        "as_of": dt.date.today().isoformat(),
        "recommended_retention": {
            "primary_screening_model": "fusion_logreg_v3",
            "core_fallback_model": tab_card.get("model_name"),
            "adjunct_models": ["retina_resnet18_tempcal", "skin_resnet18_tempcal"],
            "research_only_model": genomics_card.get("model_name"),
        },
        "screening_alignment": {
            "retain_for_3_6_12_month_program": "fusion + tabular backbone",
            "why": "This combination supports first-contact screening, survives missing optional modalities, and produces the most operationally usable referral signal.",
        },
        "models": models,
    }
