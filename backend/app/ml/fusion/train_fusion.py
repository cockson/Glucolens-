import os, json, datetime as dt
import numpy as np
import pandas as pd
from joblib import dump
from pandas.errors import EmptyDataError

from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score, f1_score

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "fusion")
os.makedirs(ART_DIR, exist_ok=True)

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
    # retina optional
    df["p_retina"] = df["p_retina"].fillna(0.0)
    df["retina_ok"] = df["retina_ok"].fillna(0).astype(int)

    X = df[["p_tabular","p_retina","retina_ok"]].values
    y = df["label"].astype(int).values

    outer = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof = np.zeros(len(df), dtype=float)

    for tr, va in outer.split(X, y):
        base = LogisticRegression(max_iter=600, class_weight="balanced")
        base.fit(X[tr], y[tr])
        cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
        cal.fit(X[va], y[va])
        oof[va] = cal.predict_proba(X[va])[:,1]

    auroc = float(roc_auc_score(y, oof)) if len(np.unique(y)) == 2 else None
    brier = float(brier_score_loss(y, oof))
    acc = float(accuracy_score(y, (oof>=0.5).astype(int)))
    f1 = float(f1_score(y, (oof>=0.5).astype(int)))

    # Fit final
    base = LogisticRegression(max_iter=600, class_weight="balanced")
    base.fit(X, y)
    cal = CalibratedClassifierCV(base, method="isotonic", cv=5)
    cal.fit(X, y)

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = "fusion_logreg_isotonic"

    bundle = {
        "model_name": model_name,
        "model_version": version,
        "features": ["p_tabular","p_retina","retina_ok"],
        "classes": ["screen_negative","screen_positive_refer"],
        "calibration": "isotonic",
        "metrics_oof": {"auroc": auroc, "brier": brier, "accuracy": acc, "f1": f1},
        "estimator": cal
    }

    dump(bundle, os.path.join(ART_DIR, f"{model_name}_{version}.joblib"))

    with open(os.path.join(ART_DIR,"performance.json"),"w",encoding="utf-8") as f:
        json.dump(bundle["metrics_oof"], f, indent=2)

    with open(os.path.join(ART_DIR,"registry.json"),"w",encoding="utf-8") as f:
        json.dump({"current":{
            "model_name": model_name,
            "model_version": version,
            "model_path": os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
        }}, f, indent=2)

    print("Saved fusion model + registry.")

if __name__ == "__main__":
    main()
