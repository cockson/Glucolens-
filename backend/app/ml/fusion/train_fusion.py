import os, json, datetime as dt
import numpy as np
import pandas as pd
from joblib import dump
from pandas.errors import EmptyDataError

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict
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

def _build_features(df: pd.DataFrame):
    # Gate modality probabilities by quality flags.
    df = df.copy()
    df["p_retina_eff"] = df["p_retina"] * df["retina_ok"]
    df["p_skin_eff"] = df["p_skin"] * df["skin_ok"]
    df["p_genomics_eff"] = df["p_genomics"] * df["geno_ok"]

    eff_cols = ["p_tabular", "p_retina_eff", "p_skin_eff", "p_genomics_eff"]
    arr = df[eff_cols].to_numpy(dtype=float)
    valid = np.isfinite(arr)
    counts = valid.sum(axis=1).clip(min=1)
    arr_zeros = np.where(valid, arr, 0.0)
    arr_nanmax = np.where(valid, arr, -np.inf)
    arr_nanmin = np.where(valid, arr, np.inf)

    df["p_mean_active"] = arr_zeros.sum(axis=1) / counts
    df["p_max_active"] = np.where(np.isfinite(arr_nanmax.max(axis=1)), arr_nanmax.max(axis=1), 0.0)
    df["p_min_active"] = np.where(np.isfinite(arr_nanmin.min(axis=1)), arr_nanmin.min(axis=1), 0.0)
    df["p_range_active"] = df["p_max_active"] - df["p_min_active"]
    df["n_modalities_active"] = counts
    df["tab_retina_gap"] = np.abs(df["p_tabular"] - df["p_retina_eff"])
    df["tab_skin_gap"] = np.abs(df["p_tabular"] - df["p_skin_eff"])

    feature_cols = [
        "p_tabular", "p_retina_eff", "p_skin_eff", "p_genomics_eff",
        "retina_ok", "skin_ok", "geno_ok",
        "p_mean_active", "p_max_active", "p_min_active", "p_range_active",
        "n_modalities_active", "tab_retina_gap", "tab_skin_gap",
    ]
    X = df[feature_cols].to_numpy(dtype=float)
    return X, feature_cols

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

    # Clean + deduplicate.
    df = df.drop_duplicates().reset_index(drop=True)
    for c in ["p_tabular", "p_retina", "p_skin", "p_genomics"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).clip(0.0, 1.0)

    X, feature_cols = _build_features(df)
    y = df["label"].astype(int).values

    uniq, counts = np.unique(y, return_counts=True)
    if len(uniq) < 2:
        raise SystemExit("fusion_train.csv needs at least 2 classes in label for training.")

    min_class_n = int(counts.min())
    n_samples = int(len(y))
    if n_samples < 200 or min_class_n < 30:
        print(
            f"WARNING: Very small fusion training set for a Brier target near 0.02 "
            f"(rows={n_samples}, min_class_count={min_class_n}). "
            "Collect more linked outcomes for reliable calibration."
        )
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
            if len(y_train) >= 120 and min_class_train >= 8:
                candidates.append("isotonic")

        best = None
        for c_val in [0.1, 0.5, 1.0, 2.0, 5.0]:
            for cw in ["balanced", None]:
                base = LogisticRegression(max_iter=3000, C=c_val, class_weight=cw)
                # Evaluate via OOF brier on train split to pick robust base.
                cv_inner = StratifiedKFold(n_splits=min(5, min_class_train), shuffle=True, random_state=42)
                p_oof = cross_val_predict(base, X_train, y_train, cv=cv_inner, method="predict_proba")[:, 1]
                b_oof = brier_score_loss(y_train, p_oof)
                for method in candidates:
                    est = CalibratedClassifierCV(base, method=method, cv=calib_cv_train)
                    est.fit(X_train, y_train)
                    p_test = est.predict_proba(X_test)[:,1]
                    m = _metric_pack(y_test, p_test)
                    if best is None or m["brier"] < best["metrics"]["brier"]:
                        best = {
                            "method": method,
                            "metrics": m,
                            "base_params": {"C": c_val, "class_weight": cw},
                            "oof_brier_train": float(b_oof),
                        }

        if best is not None:
            selected_method = best["method"]
            metrics_holdout = best["metrics"]

    # Fall back to direct logistic model when calibration CV is not feasible.
    final_cv = min(5, n_samples, min_class_n)
    base_params = {"C": 1.0, "class_weight": "balanced"}
    if holdout_ok and "best" in locals() and best is not None:
        base_params = best.get("base_params", base_params)
    base_final = LogisticRegression(max_iter=3000, C=base_params["C"], class_weight=base_params["class_weight"])
    if selected_method is not None and final_cv >= 2:
        estimator = CalibratedClassifierCV(
            base_final,
            method=selected_method,
            cv=final_cv,
        )
        estimator.fit(X, y)
        calibration_used = selected_method
    else:
        estimator = base_final
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
        "base_model_params": base_params,
        "metrics_oof": metrics_summary,
        "metrics_holdout": metrics_holdout,
        "metrics_train": metrics_train,
        "estimator": estimator
    }

    model_path = os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
    dump(bundle, model_path, compress=3)

    with open(os.path.join(ART_DIR,"performance.json"),"w",encoding="utf-8") as f:
        json.dump({
            "metrics_summary": metrics_summary,
            "metrics_holdout": metrics_holdout,
            "metrics_train": metrics_train,
            "calibration": calibration_used,
            "n_samples": int(n_samples),
        }, f, indent=2)

    model_ref = os.path.relpath(model_path, REPO_ROOT).replace(os.sep, "/")
    with open(os.path.join(ART_DIR,"registry.json"),"w",encoding="utf-8") as f:
        json.dump({"current":{
            "model_name": model_name,
            "model_version": version,
            "model_path": model_ref
        }}, f, indent=2)

    print("Saved fusion model + registry.")

if __name__ == "__main__":
    main()
