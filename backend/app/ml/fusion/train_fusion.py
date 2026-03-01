import os, json, datetime as dt
import numpy as np
import pandas as pd
from joblib import dump
from pandas.errors import EmptyDataError

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score, f1_score

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "fusion")
os.makedirs(ART_DIR, exist_ok=True)

def _metric_pack(y_true, p):
    y_hat = (p >= 0.5).astype(int)
    return {
        "auroc": float(roc_auc_score(y_true, p)) if len(np.unique(y_true)) == 2 else None,
        "brier": float(brier_score_loss(y_true, p)),
        "accuracy": float(accuracy_score(y_true, y_hat)),
        "f1": float(f1_score(y_true, y_hat, zero_division=0)),
    }

def main():
    """
    Train fusion model using prediction_records where both modalities exist.
    Requires outcomes linkage OR a proxy label column in a generated dataset.
    MVP approach: use linked outcomes when available; otherwise skip training.
    """

    # MVP: expects a prepared dataset created from DB export:
    # backend/data/fusion_train.csv with columns:
    # p_tabular, p_retina, retina_ok, label
    path = os.path.join(REPO_ROOT, "data", "fusion_train.csv")
    if not os.path.exists(path):
        raise SystemExit("Missing backend/data/fusion_train.csv (export from linked outcomes).")

    try:
        df = pd.read_csv(path)
    except EmptyDataError:
        raise SystemExit("fusion_train.csv is empty. Run export_fusion_train or provide data.")
    if df.empty:
        raise SystemExit("fusion_train.csv has no rows. Run export_fusion_train or provide data.")
    df = df.dropna(subset=["p_tabular","label"])
    if df.empty:
        raise SystemExit("fusion_train.csv has no usable rows after dropna. Check required columns.")

    # Optional modality columns may be absent in older exports.
    for col, default in (("p_retina", 0.0), ("retina_ok", 0), ("p_skin", 0.0), ("skin_ok", 0), ("p_genomics", 0.0), ("geno_ok", 0)):
        if col not in df.columns:
            df[col] = default

    # Optional modality values.
    df["p_retina"] = df["p_retina"].fillna(0.0)
    df["retina_ok"] = df["retina_ok"].fillna(0).astype(int)
    df["p_skin"] = df["p_skin"].fillna(0.0)
    df["skin_ok"] = df["skin_ok"].fillna(0).astype(int)
    df["p_genomics"] = df["p_genomics"].fillna(0.0)
    df["geno_ok"] = df["geno_ok"].fillna(0).astype(int)

    feature_cols = ["p_tabular","p_retina","retina_ok","p_skin","skin_ok","p_genomics","geno_ok"]
    X = df[feature_cols].values
    y = df["label"].astype(int).values

    uniq, counts = np.unique(y, return_counts=True)
    if len(uniq) < 2:
        raise SystemExit("fusion_train.csv needs at least 2 classes in label for training.")

    min_class_n = int(counts.min())
    n_samples = int(len(y))
    if n_samples < 20 or min_class_n < 3:
        raise SystemExit(
            f"fusion_train.csv too small for reliable calibration (rows={n_samples}, min_class_count={min_class_n}). "
            "Need at least 20 rows and >=3 samples per class; preferably 100+ rows."
        )
    holdout_ok = n_samples >= 20 and min_class_n >= 3
    selected_method = None
    metrics_holdout = None
    metrics_train = None

    if holdout_ok:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )
        min_class_train = int(np.bincount(y_train).min())
        calib_cv_train = min(5, len(y_train), min_class_train)

        candidates = []
        if calib_cv_train >= 2:
            candidates = ["sigmoid"]
            if len(y_train) >= 100 and min_class_train >= 5:
                candidates.append("isotonic")

        best = None
        for method in candidates:
            est = CalibratedClassifierCV(
                LogisticRegression(max_iter=2000, class_weight="balanced"),
                method=method,
                cv=calib_cv_train,
            )
            est.fit(X_train, y_train)
            p_test = est.predict_proba(X_test)[:,1]
            m = _metric_pack(y_test, p_test)
            if best is None or m["brier"] < best["metrics"]["brier"]:
                best = {"method": method, "metrics": m}

        if best is not None:
            selected_method = best["method"]
            metrics_holdout = best["metrics"]

    # Fall back to direct logistic model when calibration CV is not feasible.
    final_cv = min(5, n_samples, min_class_n)
    if selected_method is not None and final_cv >= 2:
        estimator = CalibratedClassifierCV(
            LogisticRegression(max_iter=2000, class_weight="balanced"),
            method=selected_method,
            cv=final_cv,
        )
        estimator.fit(X, y)
        calibration_used = selected_method
    else:
        estimator = LogisticRegression(max_iter=2000, class_weight="balanced")
        estimator.fit(X, y)
        calibration_used = "none"
        # Tiny-data fallback: holdout metrics unavailable.
        metrics_holdout = None

    # Always capture train-set metrics for comparison.
    p_train = estimator.predict_proba(X)[:,1]
    metrics_train = _metric_pack(y, p_train)

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = "fusion_logreg_v3"

    # Backward-compatible summary prefers holdout when available.
    metrics_summary = metrics_holdout if metrics_holdout is not None else metrics_train

    bundle = {
        "model_name": model_name,
        "model_version": version,
        "features": feature_cols,
        "classes": ["screen_negative","screen_positive_refer"],
        "calibration": calibration_used,
        "metrics_oof": metrics_summary,
        "metrics_holdout": metrics_holdout,
        "metrics_train": metrics_train,
        "estimator": estimator
    }

    dump(bundle, os.path.join(ART_DIR, f"{model_name}_{version}.joblib"))

    with open(os.path.join(ART_DIR,"performance.json"),"w",encoding="utf-8") as f:
        json.dump({
            "metrics_summary": metrics_summary,
            "metrics_holdout": metrics_holdout,
            "metrics_train": metrics_train,
            "calibration": calibration_used,
            "n_samples": int(n_samples),
        }, f, indent=2)

    with open(os.path.join(ART_DIR,"registry.json"),"w",encoding="utf-8") as f:
        json.dump({"current":{
            "model_name": model_name,
            "model_version": version,
            "model_path": os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
        }}, f, indent=2)

    print("Saved fusion model + registry.")

if __name__ == "__main__":
    main()
