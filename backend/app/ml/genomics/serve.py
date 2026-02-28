import json, os
import pandas as pd
from joblib import load
from app.ml.genomics.prepare_genomics import prepare_genomics

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
ART_CANDIDATES = [
    os.path.join(REPO_ROOT, "artifacts", "genomics"),
    os.path.join(PROJECT_ROOT, "backend", "artifacts", "genomics"),
]


def _find_art_dir() -> str:
    for d in ART_CANDIDATES:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
    return ART_CANDIDATES[0]


def _resolve_model_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    if path == "backend" or path.startswith(f"backend{os.sep}"):
        return os.path.join(PROJECT_ROOT, path)
    return os.path.join(REPO_ROOT, path)

def get_model():
    art = _find_art_dir()
    with open(os.path.join(art, "registry.json"), "r", encoding="utf-8") as f:
        path = json.load(f)["current"]["model_path"]
    return load(_resolve_model_path(path))


def _extract_coefficients(estimator):
    # Supports Pipeline(LogisticRegression) and CalibratedClassifierCV(Pipeline(...)).
    model = estimator
    if hasattr(model, "calibrated_classifiers_") and model.calibrated_classifiers_:
        cc = model.calibrated_classifiers_[0]
        model = getattr(cc, "estimator", None) or getattr(cc, "base_estimator", None) or model

    if hasattr(model, "named_steps"):
        model = model.named_steps.get("logisticregression", model)

    coef = getattr(model, "coef_", None)
    if coef is None:
        return None
    return coef.ravel().tolist()


def load_model_card():
    art = _find_art_dir()
    card_path = os.path.join(art, "model_card.json")
    if os.path.isfile(card_path):
        with open(card_path, "r", encoding="utf-8") as f:
            return json.load(f)

    bundle = get_model()
    return {
        "model_name": "genomics_logreg",
        "task": "binary classification",
        "calibration": bundle.get("calibration", "unknown"),
        "features": bundle.get("features", []),
    }


def load_performance():
    art = _find_art_dir()
    perf_path = os.path.join(art, "performance.json")
    if not os.path.isfile(perf_path):
        return {"performance": None}
    with open(perf_path, "r", encoding="utf-8") as f:
        return {"performance": json.load(f)}

def predict_genomics(payload: dict):
    bundle = get_model()
    features = bundle.get("features") or []
    X = prepare_genomics(pd.DataFrame([payload]))
    if features:
        X = X.reindex(columns=features, fill_value=0.0)

    estimator = bundle["estimator"]
    proba = estimator.predict_proba(X)[:, 1][0]

    explain = {"top_coefficients": []}
    coefs = _extract_coefficients(estimator)
    if coefs is not None and features:
        items = list(zip(features, coefs))
        items.sort(key=lambda t: abs(float(t[1])), reverse=True)
        explain["top_coefficients"] = [
            {
                "feature": feat,
                "coefficient": float(c),
                "abs_coefficient": abs(float(c)),
                "direction": "positive" if float(c) >= 0 else "negative",
            }
            for feat, c in items[:10]
        ]

    return {
        "model": "genomics",
        "probability": float(proba),
        "predicted_label": "positive" if float(proba) >= 0.5 else "negative",
        "explainability": explain,
    }
