import json
import os
import datetime as dt

import numpy as np
import pandas as pd
from joblib import dump

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline

from app.ml.tabular.features import ANTHRO_FEATURES, GENO_FEATURES, TARGET_COL, CLASSES
from app.ml.tabular.pipeline import build_preprocess, build_baseline_model

# IMPORTANT:
# When you run from: Glucolens/backend
# ART_DIR = backend/artifacts/... would become backend/backend/artifacts...
# Use artifacts/... relative to backend instead.
ART_DIR = os.path.join("artifacts", "tabular")
os.makedirs(ART_DIR, exist_ok=True)


def infer_types(df, feature_cols, numeric_threshold: float = 0.85):
    """
    Robust typing:
    - numeric dtype -> numeric
    - category dtype -> categorical
    - object dtype -> attempt numeric coercion; if mostly numeric -> numeric else categorical
    """
    cats, nums = [], []
    missing_tokens = {"", " ", "na", "n/a", "nan", "null", "none", "-", "--"}

    for c in feature_cols:
        if c not in df.columns:
            continue

        s = df[c].copy()

        # category dtype => categorical
        if str(df[c].dtype) == "category":
            cats.append(c)
            continue

        # bool => numeric (0/1)
        if df[c].dtype == "bool":
            nums.append(c)
            continue

        # numeric dtype => numeric
        if pd.api.types.is_numeric_dtype(df[c]):
            nums.append(c)
            continue

        # object/other => normalize tokens then coerce
        if df[c].dtype == "object":
            s = s.astype(str).str.strip()
            s = s.mask(s.str.lower().isin(missing_tokens), np.nan)

        coerced = pd.to_numeric(s, errors="coerce")

        non_na = pd.Series(s).notna().sum()
        if non_na == 0:
            # all missing -> safer as categorical
            cats.append(c)
            continue

        frac_numeric = coerced.notna().sum() / non_na
        if frac_numeric >= numeric_threshold:
            nums.append(c)
        else:
            cats.append(c)

    return nums, cats


def map_target_to_binary(series: pd.Series) -> np.ndarray:
    """
    Strict label mapping:
    - Known negatives -> 0
    - Known positives -> 1
    - Unknowns -> raise (prevents silent one-class collapse)
    """
    y_raw = series.astype(str).str.strip().str.lower()

    neg = {
        "0", "no", "n", "not_diabetic", "prediabetes", "negative", "false",
        "non-diabetic", "nondiabetic", "normal", "healthy"
    }
    pos = {
        "1", "yes", "y", "diabetic", "diabetes", "positive", "true",
        "t2d", "type2", "type_2", "type-2"
    }

    y = y_raw.map(lambda v: 0 if v in neg else (1 if v in pos else np.nan))

    if y.isna().any():
        bad = sorted(set(y_raw[y.isna()]))[:30]
        raise ValueError(
            f"Unrecognized labels in {TARGET_COL}: {bad} (showing up to 30). "
            f"Fix your labels or expand pos/neg mappings."
        )

    return y.astype(int).to_numpy()


def main(train_csv_path: str):
    df = pd.read_csv(train_csv_path)

    feature_cols = list(dict.fromkeys(ANTHRO_FEATURES + GENO_FEATURES))

    # Ensure all expected feature columns exist
    for c in feature_cols:
        if c not in df.columns:
            df[c] = np.nan

    if TARGET_COL not in df.columns:
        raise ValueError(f"Missing target col {TARGET_COL}")

    X = df[feature_cols].copy()
    y = map_target_to_binary(df[TARGET_COL])

    # Drop columns that are entirely missing (prevents median-imputer skipping + unstable transforms)
    all_missing = [c for c in X.columns if X[c].isna().all()]
    if all_missing:
        print("Dropping all-missing features:", all_missing)
        X = X.drop(columns=all_missing)
        feature_cols = [c for c in feature_cols if c not in all_missing]

    # Infer numeric vs categorical based on the *actual X we will train with*
    nums, cats = infer_types(X, list(X.columns))

    # Force numeric cols to be numeric (prevents "170" strings etc.)
    for c in nums:
        X[c] = pd.to_numeric(X[c], errors="coerce")

    # Force categorical cols to object (clean for OneHot)
    for c in cats:
        X[c] = X[c].astype("object")

    print("Numeric cols:", nums)
    print("Categorical cols:", cats)

    # Global class sanity check
    unique_classes = np.unique(y)
    if len(unique_classes) < 2:
        counts = dict(zip(*np.unique(y, return_counts=True)))
        raise ValueError(
            f"Training data has only one class: {unique_classes}. Counts: {counts}. "
            f"Your dataset likely has no positives (or no negatives). Use a labeled dataset."
        )

    # Adaptive folds: ensure each fold can contain minority class
    counts = np.bincount(y)
    minority = int(counts.min())
    if minority < 2:
        raise ValueError(
            "Need at least 2 samples of the minority class to run stratified CV and calibration. "
            f"Counts: {dict(zip(*np.unique(y, return_counts=True)))}"
        )

    n_splits = min(5, minority)
    if n_splits < 5:
        print(f"Adjusting CV folds to {n_splits} due to low minority samples ({minority}).")

    pre = build_preprocess(nums, cats)
    base = build_baseline_model()

    base_pipe = Pipeline(steps=[
        ("preprocess", pre),
        ("model", base),
    ])

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_proba = np.zeros(len(X), dtype=float)

    for tr_idx, va_idx in skf.split(X, y):
        X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
        y_tr, y_va = y[tr_idx], y[va_idx]

        # Extra safety: if a fold somehow ends up one-class, skip it
        if len(np.unique(y_tr)) < 2:
            print("WARNING: Skipping fold with one class in training split.")
            continue
        if len(np.unique(y_va)) < 2:
            print("WARNING: Skipping fold with one class in validation split.")
            continue

        # Calibrate using CV on the training split, then score on validation.
        # Newer sklearn versions no longer accept cv="prefit".
        cal = CalibratedClassifierCV(
            base_pipe,
            method="sigmoid",
            cv=min(5, max(2, np.bincount(y_tr).min())),
        )
        cal.fit(X_tr, y_tr)

        oof_proba[va_idx] = cal.predict_proba(X_va)[:, 1]

    # If we skipped folds, oof_proba might contain zeros for some indices.
    # Still compute metrics, but warn.
    if np.all(oof_proba == 0) or np.all(oof_proba == oof_proba[0]):
        print("WARNING: OOF probabilities look degenerate. Dataset may be too small/imbalanced.")

    auc = float(roc_auc_score(y, oof_proba))
    brier = float(brier_score_loss(y, oof_proba))
    acc = float(accuracy_score(y, (oof_proba >= 0.5).astype(int)))

    # Fit final on full data, then calibrate using CV (stronger)
    base_pipe.fit(X, y)
    final = CalibratedClassifierCV(base_pipe, method="sigmoid", cv=min(5, minority))
    final.fit(X, y)

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = "tabular_logreg_calibrated"
    model_path = os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
    dump(final, model_path)

    model_card = {
        "model_name": model_name,
        "model_version": version,
        "classes": CLASSES,
        "features": {"anthro": ANTHRO_FEATURES, "genomics": GENO_FEATURES},
        "typing": {"numeric": nums, "categorical": cats, "dropped_all_missing": all_missing},
        "training": {
            "source": os.path.basename(train_csv_path),
            "n_samples": int(len(X)),
            "cv": f"{n_splits}-fold stratified; OOF metrics",
            "calibration": "sigmoid (Platt) via CalibratedClassifierCV",
        },
        "metrics_oof": {
            "auroc": auc,
            "brier": brier,
            "accuracy": acc
        },
        "intended_use": "Risk screening support tool; not a diagnostic device.",
        "limitations": [
            "Current Phase uses binary classification only.",
            "Model quality depends heavily on label correctness and minority-class count.",
        ],
        "created_at_utc": dt.datetime.utcnow().isoformat() + "Z",
    }

    card_path = os.path.join(ART_DIR, f"{model_name}_{version}.modelcard.json")
    with open(card_path, "w", encoding="utf-8") as f:
        json.dump(model_card, f, indent=2)

    registry_path = os.path.join(ART_DIR, "registry.json")
    registry = {
        "current": {
            "model_name": model_name,
            "model_version": version,
            "model_path": model_path,
            "modelcard_path": card_path,
        }
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print("Saved:", model_path)
    print("OOF AUROC:", auc, "Brier:", brier, "Acc:", acc)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.ml.tabular.train_tabular <train_csv_path>")
    main(sys.argv[1])
