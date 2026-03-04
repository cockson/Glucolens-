import argparse
import json
import os
from dataclasses import dataclass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from app.ml.tabular import train_tabular_pro as tp


@dataclass
class AuditContext:
    df: pd.DataFrame
    X: pd.DataFrame
    y: np.ndarray
    feature_cols: list[str]
    output_dir: str


def _mk_out(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _norm_columns(df: pd.DataFrame) -> pd.DataFrame:
    return tp.add_derived_features(tp.normalize_columns(df.copy()))


def _binary_target_from_multiclass(df: pd.DataFrame, target_col: str) -> np.ndarray:
    y_mc, class_names = tp.map_target_to_multiclass(df[target_col])
    diabetic_idx = class_names.index("diabetic") if "diabetic" in class_names else len(class_names) - 1
    return (y_mc == diabetic_idx).astype(int)


def _build_X(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    available = [c for c in tp.FEATURES if c in df.columns and c not in tp.LEAKY_COLS]
    if not available:
        raise ValueError("No tabular features found for audit.")

    X = df[available].copy()
    all_missing = [c for c in X.columns if X[c].isna().all()]
    if all_missing:
        X = X.drop(columns=all_missing)
    return X, list(X.columns)


def _pipeline(X: pd.DataFrame, feature_cols: list[str]) -> Pipeline:
    pre = tp.build_preprocess(X, feature_cols)
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    return Pipeline([("preprocess", pre), ("model", model)])


def _oof_auc(pipe: Pipeline, X: pd.DataFrame, y: np.ndarray, seed: int = 42) -> tuple[float, np.ndarray]:
    splits = min(5, int(np.bincount(y).min()))
    if splits < 2:
        raise ValueError("Not enough minority samples for OOF audit.")
    cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=seed)
    p = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
    return float(roc_auc_score(y, p)), p


def _shuffle_auc(pipe: Pipeline, X: pd.DataFrame, y: np.ndarray, seed: int = 42) -> float:
    rng = np.random.default_rng(seed)
    y_shuf = y.copy()
    rng.shuffle(y_shuf)
    auc, _ = _oof_auc(pipe, X, y_shuf, seed=seed)
    return auc


def _group_split_auc(pipe: Pipeline, X: pd.DataFrame, y: np.ndarray, groups: pd.Series) -> dict:
    g = groups.fillna("unknown").astype(str)
    n_groups = g.nunique()
    if n_groups < 2:
        return {"available": False, "reason": "fewer_than_2_groups"}

    n_splits = min(5, n_groups)
    gkf = GroupKFold(n_splits=n_splits)
    aucs = []
    fold_rows = []
    for i, (tr, va) in enumerate(gkf.split(X, y, groups=g), start=1):
        y_tr = y[tr]
        y_va = y[va]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_va)) < 2:
            fold_rows.append({"fold": i, "auroc": None, "reason": "single_class_fold"})
            continue
        pipe.fit(X.iloc[tr], y_tr)
        p = pipe.predict_proba(X.iloc[va])[:, 1]
        auc = float(roc_auc_score(y_va, p))
        aucs.append(auc)
        fold_rows.append({"fold": i, "auroc": auc, "reason": "ok"})

    if not aucs:
        return {"available": False, "reason": "no_valid_folds", "folds": fold_rows}
    return {
        "available": True,
        "n_groups": int(n_groups),
        "n_splits": int(n_splits),
        "auroc_mean": float(np.mean(aucs)),
        "auroc_std": float(np.std(aucs)),
        "folds": fold_rows,
    }


def _keyword_leak_scan(columns: list[str]) -> list[str]:
    patterns = (
        "label", "target", "outcome", "diagnos", "diabet", "on_antidiabetic", "ground_truth", "y_true"
    )
    suspicious = []
    for c in columns:
        lc = c.lower()
        if any(p in lc for p in patterns):
            suspicious.append(c)
    return sorted(set(suspicious))


def _perfect_predictor_scan(ctx: AuditContext) -> list[dict]:
    out = []
    y = pd.Series(ctx.y)
    for c in ctx.feature_cols:
        s = ctx.X[c]
        # Bounded-cardinality scan to reduce noise/compute.
        if s.nunique(dropna=True) > 200:
            continue
        grp = pd.DataFrame({"x": s, "y": y}).dropna().groupby("x")["y"]
        stats = grp.agg(["mean", "count"]).reset_index()
        stats = stats[stats["count"] >= 20]
        if stats.empty:
            continue
        hit = stats[(stats["mean"] <= 0.0) | (stats["mean"] >= 1.0)]
        if not hit.empty:
            out.append(
                {
                    "feature": c,
                    "max_support": int(hit["count"].max()),
                    "n_perfect_bins": int(len(hit)),
                }
            )
    return sorted(out, key=lambda r: (r["max_support"], r["n_perfect_bins"]), reverse=True)


def _duplicate_checks(ctx: AuditContext) -> dict:
    feats = ctx.X.copy()
    feats["_y"] = ctx.y
    dup_any = feats.duplicated(subset=ctx.feature_cols, keep=False)
    n_dup = int(dup_any.sum())
    rate = float(n_dup / max(1, len(feats)))

    conflict = (
        feats.groupby(ctx.feature_cols, dropna=False)["_y"]
        .nunique()
        .reset_index(name="n_labels")
    )
    n_conflict_groups = int((conflict["n_labels"] > 1).sum())

    return {
        "duplicate_row_count": n_dup,
        "duplicate_row_rate": rate,
        "conflicting_label_groups": n_conflict_groups,
    }


def _plot_calibration(y: np.ndarray, p: np.ndarray, out_png: str, title: str):
    frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot([0, 1], [0, 1], "--", color="#777")
    ax[0].plot(mean_pred, frac_pos, marker="o", color="#1f77b4")
    ax[0].set_title(f"{title} Reliability")
    ax[0].set_xlabel("Predicted probability")
    ax[0].set_ylabel("Observed frequency")
    ax[0].set_xlim(0, 1)
    ax[0].set_ylim(0, 1)

    ax[1].hist(p, bins=20, color="#ff7f0e", alpha=0.8)
    ax[1].set_title(f"{title} Probability Histogram")
    ax[1].set_xlabel("Predicted probability")
    ax[1].set_ylabel("Count")

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def run_audit(
    csv_path: str,
    output_dir: str,
    target_col: str = tp.TARGET,
    site_col: str = "source_file",
    patient_col: str = "patient_key",
    strict: bool = False,
) -> dict:
    _mk_out(output_dir)
    df = pd.read_csv(csv_path)
    df = _norm_columns(df)

    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found.")

    y = _binary_target_from_multiclass(df, target_col)
    X, feature_cols = _build_X(df)
    ctx = AuditContext(df=df, X=X, y=y, feature_cols=feature_cols, output_dir=output_dir)

    pipe = _pipeline(ctx.X, ctx.feature_cols)
    auc_true, p_true = _oof_auc(pipe, ctx.X, ctx.y)
    auc_shuffle = _shuffle_auc(pipe, ctx.X, ctx.y)

    site_report = {"available": False, "reason": "site_col_missing"}
    if site_col in ctx.df.columns:
        site_report = _group_split_auc(pipe, ctx.X, ctx.y, ctx.df[site_col])

    patient_report = {"available": False, "reason": "patient_col_missing"}
    if patient_col in ctx.df.columns:
        patient_report = _group_split_auc(pipe, ctx.X, ctx.y, ctx.df[patient_col])

    leak_keyword_hits = _keyword_leak_scan(list(ctx.df.columns))
    perfect_predictors = _perfect_predictor_scan(ctx)
    dup = _duplicate_checks(ctx)

    cal_png = os.path.join(output_dir, "calibration_oof.png")
    _plot_calibration(ctx.y, p_true, cal_png, "OOF")

    failures = []
    warnings = []

    if auc_shuffle > 0.60:
        failures.append(f"Label-shuffle AUROC too high ({auc_shuffle:.3f} > 0.60). Possible leakage.")
    elif auc_shuffle > 0.55:
        warnings.append(f"Label-shuffle AUROC elevated ({auc_shuffle:.3f}). Investigate.")

    if site_report.get("available"):
        site_auc = site_report["auroc_mean"]
        if (auc_true - site_auc) > 0.15:
            failures.append(
                f"Large drop on site-group split (OOF={auc_true:.3f}, site_group={site_auc:.3f})."
            )

    if patient_report.get("available"):
        p_auc = patient_report["auroc_mean"]
        if (auc_true - p_auc) > 0.15:
            failures.append(
                f"Large drop on patient-group split (OOF={auc_true:.3f}, patient_group={p_auc:.3f})."
            )

    if dup["conflicting_label_groups"] > 0:
        warnings.append(
            f"Found {dup['conflicting_label_groups']} duplicate feature groups with conflicting labels."
        )

    if perfect_predictors:
        warnings.append(
            f"Potential perfect-predictor bins detected in {len(perfect_predictors)} feature(s)."
        )

    # Ignore known target col itself if present; still flag others.
    bad_keyword_hits = [c for c in leak_keyword_hits if c != target_col]
    if bad_keyword_hits:
        warnings.append(f"Leakage-like column names detected: {bad_keyword_hits[:10]}")

    report = {
        "status": "fail" if failures else "pass",
        "summary": {
            "n_rows": int(len(ctx.df)),
            "n_features": int(len(ctx.feature_cols)),
            "positive_rate": float(np.mean(ctx.y)),
            "auroc_oof": float(auc_true),
            "auroc_label_shuffle": float(auc_shuffle),
        },
        "leak_checks": {
            "keyword_hits": bad_keyword_hits,
            "perfect_predictor_candidates": perfect_predictors[:25],
            "duplicates": dup,
        },
        "group_split_validation": {
            "site": site_report,
            "patient": patient_report,
        },
        "calibration_plot": os.path.basename(cal_png),
        "warnings": warnings,
        "failures": failures,
    }

    out_json = os.path.join(output_dir, "audit_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if strict and failures:
        msg = "STRICT AUDIT FAILED:\n- " + "\n- ".join(failures)
        raise SystemExit(msg)

    return report


def main():
    parser = argparse.ArgumentParser(description="Strict tabular model audit (leakage, shuffle sanity, group split, calibration).")
    parser.add_argument("--csv", default=os.path.join("data", "anthropometric_data", "train_tabular.csv"))
    parser.add_argument("--target-col", default=tp.TARGET)
    parser.add_argument("--site-col", default="source_file")
    parser.add_argument("--patient-col", default="patient_key")
    parser.add_argument("--output-dir", default=os.path.join("artifacts", "audit", "tabular"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = run_audit(
        csv_path=args.csv,
        output_dir=args.output_dir,
        target_col=args.target_col,
        site_col=args.site_col,
        patient_col=args.patient_col,
        strict=args.strict,
    )
    print(json.dumps(report["summary"], indent=2))
    if report["warnings"]:
        print("Warnings:")
        for w in report["warnings"]:
            print("-", w)
    if report["failures"]:
        print("Failures:")
        for x in report["failures"]:
            print("-", x)


if __name__ == "__main__":
    main()

