import os, json
import numpy as np
from joblib import load

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
FUSION_DIR = os.path.join(REPO_ROOT, "artifacts", "fusion")
REGISTRY = os.path.join(FUSION_DIR,"registry.json")

_cached = {"bundle": None}

def _load_registry():
    with open(REGISTRY,"r",encoding="utf-8") as f:
        return json.load(f)["current"]

def _resolve_model_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    # If path starts with "backend/...", resolve from project root.
    if path == "backend" or path.startswith(f"backend{os.sep}"):
        return os.path.join(PROJECT_ROOT, path)
    return os.path.join(REPO_ROOT, path)

def get_fusion_bundle():
    if _cached["bundle"] is None:
        reg = _load_registry()
        model_path = _resolve_model_path(reg["model_path"])
        _cached["bundle"] = load(model_path)
    return _cached["bundle"]

def fusion_predict(p_tabular: float | None, p_retina: float | None, retina_ok: bool, threshold: float):
    """
    Abstain policy:
    - if tabular missing -> insufficient_data
    - if retina provided but quality failed -> retake_image
    - if confidence near threshold -> refer (conservative)
    """
    if p_tabular is None:
        return {"final_label":"insufficient_data", "final_proba": None, "reason":"missing_tabular"}

    if p_retina is not None and not retina_ok:
        return {"final_label":"retake_image", "final_proba": None, "reason":"retina_quality_failed"}

    # If trained fusion artifacts are unavailable, degrade gracefully to tabular-only.
    try:
        bundle = get_fusion_bundle()
        est = bundle["estimator"]
        x = np.array([[
            float(p_tabular),
            float(p_retina) if p_retina is not None else 0.0,
            1 if retina_ok else 0
        ]])
        proba = float(est.predict_proba(x)[:,1][0])
        reason = "fusion"
    except Exception:
        proba = float(p_tabular)
        reason = "fallback_tabular_only"

    # Conservative abstain band near threshold
    band = 0.03
    if abs(proba - threshold) <= band:
        return {"final_label":"screen_positive_refer", "final_proba": proba, "reason":"near_threshold_conservative"}

    label = "screen_positive_refer" if proba >= threshold else "screen_negative"
    return {"final_label": label, "final_proba": proba, "reason": reason}
