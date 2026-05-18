import argparse
import json
import os

import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from app.ml.tabular.train_tabular_pro import (
    FEATURES,
    LEAKY_COLS,
    TARGET,
    add_derived_features,
    build_preprocess,
    infer_feature_types,
    map_target_to_multiclass,
    normalize_columns,
)


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_INPUT = os.path.join(REPO_ROOT, "data", "anthropometric_data", "train_tabular.csv")
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "data", "fusion_train.csv")
DEFAULT_METADATA_OUTPUT = os.path.join(REPO_ROOT, "data", "fusion_train.metadata.json")
FUSION_COLUMNS = ["p_tabular", "p_retina", "retina_ok", "p_skin", "skin_ok", "p_genomics", "geno_ok", "label"]


def _balanced_sample(df: pd.DataFrame, status_col: str, max_rows: int, seed: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    classes = [c for c in ["non_diabetic", "prediabetic", "diabetic"] if c in set(df[status_col])]
    n_per_class = max(1, max_rows // max(1, len(classes)))
    parts = []
    used_idx = set()
    for cls in classes:
        part = df[df[status_col] == cls]
        take = min(n_per_class, len(part))
        sample = part.sample(n=take, random_state=seed)
        parts.append(sample)
        used_idx.update(sample.index.tolist())

    out = pd.concat(parts, ignore_index=False) if parts else pd.DataFrame()
    if len(out) < max_rows:
        remaining = df.drop(index=list(used_idx), errors="ignore")
        if not remaining.empty:
            extra = remaining.sample(n=min(max_rows - len(out), len(remaining)), random_state=seed)
            out = pd.concat([out, extra], ignore_index=False)

    return out.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def _prepare_rows(input_csv: str, max_rows: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(input_csv)
    if "diabetes_status" not in df.columns:
        raise SystemExit("Input CSV must include diabetes_status.")

    y, class_names = map_target_to_multiclass(df["diabetes_status"])
    df = df.copy()
    df["__status__"] = [class_names[int(i)] for i in y]
    df["__label__"] = (df["__status__"] == "diabetic").astype(int)
    df = _balanced_sample(df, "__status__", max_rows=max_rows, seed=seed)
    return df


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate fusion_train.csv from out-of-fold non-leaky tabular predictions. "
            "Optional modalities are left unavailable unless real linked modality predictions are exported separately."
        )
    )
    parser.add_argument("--input-csv", default=DEFAULT_INPUT)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT)
    parser.add_argument("--metadata-output", default=DEFAULT_METADATA_OUTPUT)
    parser.add_argument("--max-rows", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = normalize_columns(pd.read_csv(args.input_csv))
    df = add_derived_features(df)
    if TARGET not in df.columns:
        raise SystemExit(f"Input CSV must include {TARGET}.")

    y_mc, class_names = map_target_to_multiclass(df[TARGET])
    diabetic_idx = class_names.index("diabetic") if "diabetic" in class_names else len(class_names) - 1
    df = df.copy()
    df["__status__"] = [class_names[int(i)] for i in y_mc]
    df["__label__"] = (y_mc == diabetic_idx).astype(int)
    df = _balanced_sample(df, "__status__", max_rows=args.max_rows, seed=args.seed)

    feature_cols = [c for c in FEATURES if c in df.columns and c not in LEAKY_COLS]
    if not feature_cols:
        raise SystemExit("No usable non-leaky tabular features found for fusion export.")

    X = df[feature_cols].copy()
    all_missing = [c for c in X.columns if X[c].isna().all()]
    if all_missing:
        X = X.drop(columns=all_missing)
    feature_cols = list(X.columns)

    nums, cats = infer_feature_types(X, feature_cols)
    for c in nums:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    for c in cats:
        X[c] = X[c].astype("object").where(X[c].isna(), X[c].astype(str))

    y = df["__label__"].astype(int).to_numpy()
    min_class_n = int(pd.Series(y).value_counts().min())
    n_splits = min(5, min_class_n)
    if n_splits < 2:
        raise SystemExit("Need at least two samples per class for OOF fusion export.")

    pre = build_preprocess(X, feature_cols)
    base = RandomForestClassifier(
        n_estimators=160,
        max_depth=8,
        min_samples_leaf=4,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=args.seed,
        n_jobs=-1,
    )
    pipe = Pipeline([("preprocess", pre), ("model", base)])
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=args.seed)
    p_oof = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]

    rows = []
    for i, (_idx, row) in enumerate(df.iterrows()):
        p_tabular = p_oof[i]
        rows.append(
            {
                "p_tabular": float(p_tabular),
                "p_retina": None,
                "retina_ok": 0,
                "p_skin": None,
                "skin_ok": 0,
                "p_genomics": None,
                "geno_ok": 0,
                "label": int(row["__label__"]),
            }
        )
        if (i + 1) % 250 == 0:
            print(f"oof_predictions={i + 1}")

    out = pd.DataFrame(rows, columns=FUSION_COLUMNS)
    if out.empty:
        raise SystemExit("No usable served predictions were produced.")

    os.makedirs(os.path.dirname(args.output_csv), exist_ok=True)
    out.to_csv(args.output_csv, index=False)
    metadata = {
        "source": "oof_tabular_non_leaky_diagnostic_fields_suppressed",
        "input_csv": os.path.relpath(args.input_csv, REPO_ROOT).replace(os.sep, "/"),
        "output_csv": os.path.relpath(args.output_csv, REPO_ROOT).replace(os.sep, "/"),
        "requested_max_rows": int(args.max_rows),
        "rows_written": int(len(out)),
        "label_counts": {str(k): int(v) for k, v in out["label"].value_counts().sort_index().to_dict().items()},
        "tabular_oof_model": {
            "estimator": "RandomForestClassifier",
            "n_splits": int(n_splits),
            "features": feature_cols,
            "leakage_exclusions": sorted(LEAKY_COLS),
        },
        "optional_modalities": {
            "retina": "unavailable",
            "skin": "unavailable",
            "genomics": "unavailable",
        },
        "notes": [
            "Rows are generated from out-of-fold tabular predictions, so each probability comes from a model that did not train on that row.",
            "Diagnostic leakage fields are suppressed before prediction.",
            "Use real linked modality predictions when available; this file is a non-leaky tabular-only fusion training fallback.",
        ],
    }
    os.makedirs(os.path.dirname(args.metadata_output), exist_ok=True)
    with open(args.metadata_output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved {args.output_csv} rows={len(out)}")
    print(f"Saved {args.metadata_output}")
    print("label_counts", out["label"].value_counts().sort_index().to_dict())
    print("source=oof_tabular_non_leaky_diagnostic_fields_suppressed")
    print("optional_modalities=unavailable")


if __name__ == "__main__":
    main()
