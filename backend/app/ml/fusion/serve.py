import os, json
import numpy as np
from joblib import load

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
FUSION_CANDIDATES = [
    os.path.join(REPO_ROOT, "artifacts", "fusion"),
    os.path.join(PROJECT_ROOT, "backend", "artifacts", "fusion"),
]

_cached = {"bundle": None}

def _find_fusion_dir() -> str:
    for d in FUSION_CANDIDATES:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
    raise FileNotFoundError(f"fusion registry.json not found. Checked: {FUSION_CANDIDATES}")

def _load_registry():
    fusion_dir = _find_fusion_dir()
    with open(os.path.join(fusion_dir, "registry.json"), "r", encoding="utf-8") as f:
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

def load_model_card():
    """
    Fusion currently stores registry/performance and bundled metadata.
    Build a model-card-like response from these artifacts.
    """
    reg = _load_registry()
    bundle = get_fusion_bundle()
    perf = load_performance().get("performance", {})
    return {
        "model_name": bundle.get("model_name", reg.get("model_name", "fusion")),
        "model_version": bundle.get("model_version", reg.get("model_version", "unknown")),
        "classes": bundle.get("classes", ["screen_negative", "screen_positive_refer"]),
        "features": bundle.get("features", []),
        "calibration": bundle.get("calibration", perf.get("calibration", "unknown")),
        "metrics_summary": perf.get("metrics_summary"),
        "metrics_holdout": perf.get("metrics_holdout"),
        "metrics_train": perf.get("metrics_train"),
        "n_samples": perf.get("n_samples"),
        "intended_use": "Fusion screening support (tabular + optional image/genomics modalities).",
    }

def load_performance():
    fusion_dir = _find_fusion_dir()
    perf_path = os.path.join(fusion_dir, "performance.json")
    if not os.path.isfile(perf_path):
        return {"performance": None}
    with open(perf_path, "r", encoding="utf-8") as f:
        return {"performance": json.load(f)}

def fusion_predict(
    p_tabular: float | None,
    p_retina: float | None,
    retina_ok: bool,
    p_skin: float | None = None,
    skin_ok: bool = False,
    p_genomics: float | None = None,
    geno_ok: bool = False,
    threshold: float = 0.5,
):
    """
    Abstain policy:
    - if tabular missing -> insufficient_data
    - if retina provided but quality failed -> retake_image
    - if skin provided but quality failed -> retake_image
    - if confidence near threshold -> refer (conservative)
    """
    if p_tabular is None:
        return {"final_label":"insufficient_data", "final_proba": None, "reason":"missing_tabular"}

    if p_retina is not None and not retina_ok:
        return {"final_label":"retake_image", "final_proba": None, "reason":"retina_quality_failed"}
    if p_skin is not None and not skin_ok:
        return {"final_label":"retake_image", "final_proba": None, "reason":"skin_quality_failed"}
    if p_genomics is not None and not geno_ok:
        return {"final_label":"retake_image", "final_proba": None, "reason":"genomics_quality_failed"}

    # If trained fusion artifacts are unavailable, degrade gracefully to tabular-only.
    try:
        bundle = get_fusion_bundle()
        est = bundle["estimator"]
        x = np.array([[
            float(p_tabular),
            float(p_retina) if p_retina is not None else 0.0,
            1 if retina_ok else 0,
            float(p_skin) if p_skin is not None else 0.0,
            1 if skin_ok else 0,
            float(p_genomics) if p_genomics is not None else 0.0,
            1 if geno_ok else 0,
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
