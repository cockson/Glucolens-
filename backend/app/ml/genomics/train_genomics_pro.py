import os, json, datetime as dt
import pandas as pd
import numpy as np
from joblib import dump
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.genomics.prepare_genomics import prepare_genomics

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART = os.path.join(REPO_ROOT, "artifacts", "genomics")
os.makedirs(ART, exist_ok=True)

def _extract_label(df: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    candidates = ["label", "Label", "target", "Target", "status", "Status", "outcome", "Outcome"]
    label_col = next((c for c in candidates if c in df.columns), None)
    if label_col is None:
        raise SystemExit(
            f"Missing label column. Expected one of: {candidates}. Found: {list(df.columns)}"
        )

    y_raw = df[label_col]
    x_df = df.drop(columns=[label_col])

    # Numeric labels: treat >0 as positive.
    y_num = pd.to_numeric(y_raw, errors="coerce")
    if y_num.notna().all():
        y = (y_num.values > 0).astype(int)
        return y, x_df

    # String labels: map common clinical class names to binary.
    s = y_raw.astype(str).str.strip().str.lower()
    neg = {"0", "no", "negative", "normal", "healthy", "control", "non-diabetic", "nondiabetic"}
    pos = {"1", "yes", "positive", "diabetic", "t2d", "type2", "type_2", "case", "pre-diabetic", "prediabetic"}

    y = np.full(len(s), -1, dtype=int)
    y[s.isin(neg)] = 0
    y[s.isin(pos)] = 1
    # Fallback substring rules for labels like "Type 2 Diabetic".
    y[(y < 0) & s.str.contains("diab|t2d|type 2", regex=True)] = 1
    y[(y < 0) & s.str.contains("normal|healthy|control|non", regex=True)] = 0

    if (y < 0).any():
        unknown = sorted(set(s[y < 0].tolist()))
        raise SystemExit(f"Unrecognized label values in {label_col}: {unknown}")

    return y.astype(int), x_df

def main():
    df = pd.read_csv("data/genomics/train.csv")
    y, x_df = _extract_label(df)
    X = prepare_genomics(x_df)

    uniq, counts = np.unique(y, return_counts=True)
    if len(uniq) < 2:
        raise SystemExit("Genomics training requires at least 2 classes in labels.")

    n_samples = int(len(y))
    min_class_n = int(counts.min())
    outer_splits = min(5, n_samples, min_class_n)
    calibration_method = "isotonic" if n_samples >= 100 else "sigmoid"
    oof = np.zeros(len(df))

    base_params = dict(
        solver="lbfgs",
        max_iter=5000,
        class_weight="balanced",
        random_state=42,
    )

    def make_base_estimator():
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(**base_params),
        )

    if outer_splits >= 2:
        outer = StratifiedKFold(n_splits=outer_splits, shuffle=True, random_state=42)
        for tr, va in outer.split(X, y):
            inner_cv = min(3, int(np.bincount(y[tr]).min()), len(tr))
            if inner_cv >= 2:
                cal = CalibratedClassifierCV(
                    make_base_estimator(),
                    method=calibration_method,
                    cv=inner_cv,
                )
                cal.fit(X.iloc[tr], y[tr])
                oof[va] = cal.predict_proba(X.iloc[va])[:,1]
            else:
                base = make_base_estimator()
                base.fit(X.iloc[tr], y[tr])
                oof[va] = base.predict_proba(X.iloc[va])[:,1]
    else:
        base = make_base_estimator()
        base.fit(X, y)
        oof = base.predict_proba(X)[:,1]

    auc = roc_auc_score(y, oof)
    brier = brier_score_loss(y, oof)

    final_cv = min(5, n_samples, min_class_n)
    if final_cv >= 2:
        final = CalibratedClassifierCV(
            make_base_estimator(),
            method=calibration_method,
            cv=final_cv,
        )
        final.fit(X, y)
    else:
        final = make_base_estimator()
        final.fit(X, y)

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(ART, f"genomics_{version}.joblib")
    dump({"estimator":final, "features":list(X.columns), "calibration": calibration_method if final_cv >= 2 else "none"}, path)

    with open(f"{ART}/registry.json","w", encoding="utf-8") as f:
        model_ref = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        json.dump({"current":{"model_path":model_ref}}, f, indent=2)

    perf = {
        "auc": float(auc),
        "brier": float(brier),
        "n_samples": int(len(y)),
        "positive_rate": float(np.mean(y)),
    }
    with open(f"{ART}/performance.json", "w", encoding="utf-8") as f:
        json.dump(perf, f, indent=2)

    model_card = {
        "model_name": "genomics_logreg",
        "model_version": version,
        "task": "binary classification",
        "target": "diabetes_proxy_positive",
        "features": list(X.columns),
        "calibration": calibration_method if final_cv >= 2 else "none",
        "training": {
            "n_samples": int(len(y)),
            "positive_rate": float(np.mean(y)),
            "cv_outer_splits": int(outer_splits),
        },
        "metrics_oof": perf,
    }
    with open(f"{ART}/model_card.json", "w", encoding="utf-8") as f:
        json.dump(model_card, f, indent=2)

    print("Genomics trained:", auc, brier)

if __name__ == "__main__":
    main()
