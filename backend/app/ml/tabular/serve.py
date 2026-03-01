import json
import os
import numpy as np
import pandas as pd
from joblib import load
import shap

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "tabular")
ALT_ART_DIR = os.path.join(REPO_ROOT, "backend", "artifacts", "tabular")
REGISTRY = os.path.join(ART_DIR, "registry.json")

_cached = {"model": None, "meta": None, "explainer": None, "feature_cols": None, "classes": None, "target_idx": None}

def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None

def _sanitize_json(value):
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    return value

def load_registry():
    reg_path = _first_existing([REGISTRY, os.path.join(ALT_ART_DIR, "registry.json")])
    if not reg_path:
        raise FileNotFoundError("Tabular registry.json not found")
    return _read_json(reg_path)["current"]

def _resolve_model_path(path: str) -> str:
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    # If path starts with "backend/...", resolve from project root.
    if path == "backend" or path.startswith(f"backend{os.sep}"):
        return os.path.join(PROJECT_ROOT, path)
    return os.path.join(REPO_ROOT, path)

def get_model():
    if _cached["model"] is None:
        reg = load_registry()
        _cached["meta"] = reg
        model_path = _resolve_model_path(reg["model_path"])
        _cached["meta"]["model_path"] = model_path
        _cached["model"] = load(model_path)
        # infer feature columns from modelcard if available
        card_path = _first_existing([os.path.join(ART_DIR, "modelcard.json"), os.path.join(ALT_ART_DIR, "modelcard.json")])
        if card_path:
            card = _read_json(card_path)
            _cached["feature_cols"] = card.get("features")
            card_classes = card.get("classes")
            if isinstance(card_classes, list) and card_classes:
                _cached["classes"] = [str(c) for c in card_classes]
            _cached["target_idx"] = card.get("target_index_diabetic")
        if _cached["classes"] is None and hasattr(_cached["model"], "classes_"):
            _cached["classes"] = [str(c) for c in _cached["model"].classes_]
    return _cached["model"], _cached["meta"]

def build_input_df(payload: dict) -> pd.DataFrame:
    model, meta = get_model()
    # Use modelcard feature list as source of truth (produced by pro trainer)
    feature_cols = _cached["feature_cols"] or list(payload.keys())
    row = {c: payload.get(c, np.nan) for c in feature_cols}
    return pd.DataFrame([row])

def predict_with_explain(payload: dict, max_features: int = 10):
    model, meta = get_model()
    X = build_input_df(payload)

    proba = model.predict_proba(X)[0].astype(float)
    class_names = _cached["classes"] or [str(i) for i in range(len(proba))]
    if len(class_names) != len(proba):
        class_names = [str(i) for i in range(len(proba))]
    class_to_idx = {c: i for i, c in enumerate(class_names)}
    predicted_label = class_names[int(np.argmax(proba))]
    target_idx = _cached["target_idx"]
    if target_idx is None or not (0 <= int(target_idx) < len(proba)):
        target_idx = class_to_idx.get("diabetic")
        if target_idx is None:
            target_idx = class_to_idx.get("t2d", len(proba) - 1)
    p_t2d = float(proba[int(target_idx)])

    explain_method = "shap"
    shap_top = []

    # SHAP can fail on mixed object dtypes in tabular maskers; keep inference robust.
    try:
        if _cached["explainer"] is None:
            bg = X.copy()
            _cached["explainer"] = shap.Explainer(
                lambda data: model.predict_proba(pd.DataFrame(data, columns=X.columns))[:, int(target_idx)],
                bg
            )
        explainer = _cached["explainer"]
        sv = explainer(X)
        vals = sv.values[0]
        feats = X.columns.tolist()
        pairs = list(zip(feats, vals, X.iloc[0].tolist()))
        pairs.sort(key=lambda t: abs(t[1]), reverse=True)
        shap_top = [{"feature": f, "shap_value": float(v), "value": val} for f, v, val in pairs[:max_features]]
    except Exception:
        explain_method = "occlusion"
        base = p_t2d
        fallback_pairs = []
        for feat in X.columns.tolist():
            x_alt = X.copy()
            x_alt.at[0, feat] = np.nan
            try:
                p_alt = float(model.predict_proba(x_alt)[0][int(target_idx)])
                fallback_pairs.append((feat, base - p_alt, X.iloc[0][feat]))
            except Exception:
                continue
        fallback_pairs.sort(key=lambda t: abs(t[1]), reverse=True)
        shap_top = [
            {"feature": f, "shap_value": float(v), "value": val}
            for f, v, val in fallback_pairs[:max_features]
        ]

    probs = {class_names[i]: float(proba[i]) for i in range(len(class_names))}
    # Backward-compatible key used by fusion/monitoring code.
    probs["t2d"] = p_t2d

    return {
        "model_name": meta["model_name"],
        "model_version": meta["model_version"],
        "predicted_label": predicted_label,
        "probabilities": probs,
        "explainability": {"method": explain_method, "top_features": shap_top},
    }

def load_model_card():
    reg = load_registry()
    candidate = _resolve_model_path(reg.get("modelcard_path", ""))
    path = _first_existing([
        os.path.join(ART_DIR, "modelcard.json"),
        candidate,
        os.path.join(ALT_ART_DIR, "modelcard.json"),
    ])
    if not path:
        # Fallback to any versioned model card generated by training.
        for base in [ART_DIR, ALT_ART_DIR]:
            if not os.path.exists(base):
                continue
            cards = [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".modelcard.json")]
            if cards:
                path = sorted(cards)[-1]
                break
    if not path:
        raise FileNotFoundError("Tabular model card not found")
    return _sanitize_json(_read_json(path))

def load_performance():
    reg = load_registry()
    perf_path = _first_existing([
        _resolve_model_path(reg.get("performance_path", "")),
        os.path.join(ART_DIR, "performance.json"),
        os.path.join(ALT_ART_DIR, "performance.json"),
    ])
    if not perf_path:
        raise FileNotFoundError("Tabular performance.json not found")
    perf = _sanitize_json(_read_json(perf_path))

    comp_csv_path = _first_existing([
        _resolve_model_path(reg.get("comparison_csv", "")),
        os.path.join(ART_DIR, "comparison.csv"),
        os.path.join(ALT_ART_DIR, "comparison.csv"),
    ])
    comp = []
    if comp_csv_path:
        try:
            comp = _sanitize_json(pd.read_csv(comp_csv_path).to_dict(orient="records"))
        except Exception:
            comp = []
    return perf, comp
