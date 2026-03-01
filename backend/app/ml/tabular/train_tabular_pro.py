import os, json, datetime as dt
import numpy as np
import pandas as pd

from joblib import dump

from sklearn.model_selection import StratifiedKFold, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    accuracy_score, f1_score, log_loss
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from sklearn.calibration import CalibratedClassifierCV

try:
    from imblearn.pipeline import Pipeline as ImbPipeline
    from imblearn.over_sampling import SMOTE
    IMBLEARN_AVAILABLE = True
except Exception:
    ImbPipeline = None
    SMOTE = None
    IMBLEARN_AVAILABLE = False

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "tabular")
os.makedirs(ART_DIR, exist_ok=True)

TARGET = "diabetes_status"
SOURCE_COL = "source_file"
CLASS_ORDER = ["non_diabetic", "prediabetic", "diabetic"]

# Core screening features expected for normal operation.
REQUIRED_FEATURES = [
    "age", "sex", "bmi", "waist_circumference", "systolic_bp", "diastolic_bp"
]

# Optional training-only features when available in dataset.
OPTIONAL_FEATURES = [
    "whr", "pulse_pressure",
    "bmi_category", "central_obesity", "smoking_status", "alcohol_use", "physical_activity",
    "family_history_diabetes", "family_history_cvd", "hypertension_status",
    "fasting_glucose_mgdl", "hba1c_pct",
    "total_cholesterol_mgdl", "hdl_mgdl", "ldl_mgdl", "triglycerides_mgdl",
    "cvd_risk_10yr_pct", "cvd_risk_category",
    "on_antihypertensive", "on_statin",
]

FEATURES = REQUIRED_FEATURES + OPTIONAL_FEATURES
MAX_MISSING_RATE = 0.45
LEAKY_COLS = {"label", "on_antidiabetic", "diabetes", "diabetes_dx"}

COL_ALIASES = {
    "diabete_status": "diabetes_status",
    "diabetic_status": "diabetes_status",
    "diabetesstatus": "diabetes_status",
    "gender": "sex",
    "age_years": "age",
    "waist_circumference_cm": "waist_circumference",
    "waist": "waist_circumference",
    "waist_circ": "waist_circumference",
    "systolic": "systolic_bp",
    "systolic_bp_mmhg": "systolic_bp",
    "sbp": "systolic_bp",
    "diastolic": "diastolic_bp",
    "diastolic_bp_mmhg": "diastolic_bp",
    "dbp": "diastolic_bp",
    "waist_hip_ratio": "whr",
    "fasting_glucose": "fasting_glucose_mgdl",
    "hba1c": "hba1c_pct",
    "hba1c_percent": "hba1c_pct",
    "total_cholesterol": "total_cholesterol_mgdl",
    "hdl": "hdl_mgdl",
    "ldl": "ldl_mgdl",
    "triglycerides": "triglycerides_mgdl",
    "cvd_risk_10yr": "cvd_risk_10yr_pct",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for c in df.columns:
        norm = c.strip().lower().replace(" ", "_").replace("-", "_")
        cols.append(norm)
    df.columns = cols

    renames = {c: COL_ALIASES[c] for c in df.columns if c in COL_ALIASES}
    if renames:
        df = df.rename(columns=renames)

    # If aliases map multiple source columns into the same canonical name,
    # coalesce duplicates row-wise (first non-null), then keep one column.
    dup_names = pd.Index(df.columns[df.columns.duplicated()]).unique()
    for name in dup_names:
        same = df.loc[:, df.columns == name]
        coalesced = same.bfill(axis=1).iloc[:, 0]
        df = df.loc[:, df.columns != name]
        df[name] = coalesced
    return df

def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Keep WHR only if already present (or aliased from source columns like waist_hip_ratio).
    if "pulse_pressure" not in df.columns and {"systolic_bp", "diastolic_bp"}.issubset(df.columns):
        sbp = pd.to_numeric(df["systolic_bp"], errors="coerce")
        dbp = pd.to_numeric(df["diastolic_bp"], errors="coerce")
        df["pulse_pressure"] = sbp - dbp
    return df

# -------- DeLong AUROC CI (OOF) --------
def _compute_midrank(x):
    J = np.argsort(x)
    Z = x[J]
    N = len(x)
    T = np.zeros(N, dtype=float)
    i = 0
    while i < N:
        j = i
        while j < N and Z[j] == Z[i]:
            j += 1
        mid = 0.5*(i + j - 1) + 1
        T[i:j] = mid
        i = j
    out = np.empty(N, dtype=float)
    out[J] = T
    return out

def delong_auc_ci(y_true, y_score, alpha=0.95):
    """
    Fast DeLong implementation for binary labels (0/1).
    Returns (auc, lower, upper).
    """
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score).astype(float)

    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    m, n = len(pos), len(neg)
    if m == 0 or n == 0:
        return np.nan, np.nan, np.nan

    # Compute midranks
    all_scores = np.concatenate([pos, neg])
    all_mr = _compute_midrank(all_scores)
    mr_pos = all_mr[:m]
    mr_neg = all_mr[m:]

    auc = (mr_pos.sum() - m*(m+1)/2) / (m*n)

    v01 = (mr_pos - np.arange(1, m+1)) / n
    v10 = 1 - (mr_neg - np.arange(1, n+1)) / m
    s01 = np.var(v01, ddof=1)
    s10 = np.var(v10, ddof=1)
    se = np.sqrt(s01/m + s10/n)
    if se == 0:
        return float(auc), float(auc), float(auc)

    from scipy.stats import norm
    z = norm.ppf(1 - (1-alpha)/2)
    lower = auc - z*se
    upper = auc + z*se
    return float(auc), float(max(0, lower)), float(min(1, upper))

# -------- Calibration metrics --------
def expected_calibration_error(y, p, n_bins=10):
    y = np.asarray(y); p = np.asarray(p)
    bins = np.linspace(0, 1, n_bins+1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i+1]
        mask = (p >= lo) & (p < hi) if i < n_bins-1 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        acc = y[mask].mean()
        conf = p[mask].mean()
        ece += (mask.sum()/len(y)) * abs(acc - conf)
    return float(ece)

def calibration_slope_intercept(y, p):
    # Fit logistic regression of y on logit(p)
    eps = 1e-6
    p = np.clip(p, eps, 1-eps)
    logit = np.log(p/(1-p)).reshape(-1,1)
    lr = LogisticRegression(solver="lbfgs")
    lr.fit(logit, y)
    slope = float(lr.coef_[0][0])
    intercept = float(lr.intercept_[0])
    return slope, intercept

def multiclass_brier(y_true, proba, n_classes):
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba).astype(float)
    oh = np.zeros((len(y_true), n_classes), dtype=float)
    oh[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((proba - oh) ** 2, axis=1)))

# -------- Decision Curve Analysis --------
def decision_curve_net_benefit(y, p, thresholds=None):
    y = np.asarray(y).astype(int)
    p = np.asarray(p).astype(float)
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 99)
    out = []
    N = len(y)
    for t in thresholds:
        pred = (p >= t).astype(int)
        tp = ((pred == 1) & (y == 1)).sum()
        fp = ((pred == 1) & (y == 0)).sum()
        nb = (tp / N) - (fp / N) * (t/(1-t))
        out.append({"threshold": float(t), "net_benefit": float(nb)})
    return out

def infer_feature_types(df: pd.DataFrame, feature_cols, numeric_threshold: float = 0.85):
    cats, nums = [], []
    missing_tokens = {"", " ", "na", "n/a", "nan", "null", "none", "-", "--"}
    for c in feature_cols:
        if c not in df.columns:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            nums.append(c)
            continue
        # Try coercion for string-like columns.
        s_txt = s.astype(str).str.strip()
        s_txt = s_txt.mask(s_txt.str.lower().isin(missing_tokens), np.nan)
        coerced = pd.to_numeric(s_txt, errors="coerce")
        non_na = s_txt.notna().sum()
        frac_numeric = (coerced.notna().sum() / non_na) if non_na else 0.0
        if frac_numeric >= numeric_threshold and c != "sex":
            nums.append(c)
        else:
            cats.append(c)
    return nums, cats

def build_preprocess(df, feature_cols):
    nums, cats = infer_feature_types(df, feature_cols)

    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler())
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore"))
    ])

    pre = ColumnTransformer([
        ("num", num_pipe, nums),
        ("cat", cat_pipe, cats),
    ], remainder="drop")

    return pre

def candidate_models():
    # Two strong baselines to compare
    logreg = LogisticRegression(max_iter=800, class_weight="balanced", solver="lbfgs")
    rf = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced_subsample",
        n_jobs=-1
    )

    return {
        "logreg": (logreg, {
            "model__C": np.logspace(-2, 1, 10)
        }),
        "rf": (rf, {
            "model__max_depth": [None, 6, 12],
            "model__min_samples_split": [2, 5],
            "model__min_samples_leaf": [1, 2],
            "model__max_features": ["sqrt", "log2"],
        })
    }

def map_target_to_multiclass(series: pd.Series):
    y_raw = series.astype(str).str.strip().str.lower()

    non_diabetic = {
        "0", "no", "n", "negative", "false", "normal", "healthy",
        "non_diabetic", "not_diabetic", "non-diabetic", "nondiabetic",
    }
    prediabetic = {"prediabetes", "prediabetic", "pre-diabetes", "pre_diabetes", "impaired_glucose_tolerance"}
    diabetic = {
        "1", "yes", "y", "diabetic", "diabetes", "positive", "true",
        "t2d", "type2", "type_2", "type-2"
    }

    mapped = y_raw.map(
        lambda v: "non_diabetic" if v in non_diabetic else (
            "prediabetic" if v in prediabetic else ("diabetic" if v in diabetic else np.nan)
        )
    )
    present_classes = [c for c in CLASS_ORDER if c in set(mapped.dropna().tolist())]
    idx_map = {name: idx for idx, name in enumerate(present_classes)}
    y = mapped.map(idx_map)
    if y.isna().any():
        bad = sorted(set(y_raw[y.isna()]))[:30]
        raise ValueError(
            f"Unrecognized labels in {TARGET}: {bad} (showing up to 30). "
            "Fix your labels or expand class mappings."
        )

    return y.astype(int).to_numpy(), present_classes


def main(csv_path: str):
    df = pd.read_csv(csv_path)
    df = normalize_columns(df)
    df = add_derived_features(df)

    # Ensure required features exist
    for c in REQUIRED_FEATURES:
        if c not in df.columns:
            df[c] = np.nan

    if TARGET not in df.columns:
        raise ValueError(f"Missing target col {TARGET}")
    target_obj = df[TARGET]
    if isinstance(target_obj, pd.DataFrame):
        target_series = target_obj.bfill(axis=1).iloc[:, 0]
    else:
        target_series = target_obj
    y, class_names = map_target_to_multiclass(target_series)
    n_classes = len(class_names)
    if n_classes < 2:
        raise ValueError(f"Need at least 2 classes for training. Found: {class_names}")
    diabetic_idx = class_names.index("diabetic") if "diabetic" in class_names else (n_classes - 1)
    available = [c for c in FEATURES if c in df.columns]
    if not available:
        raise ValueError("No usable feature columns found in dataset after normalization.")
    missing_rate = df[available].isna().mean().to_dict()
    filtered = []
    dropped_missing = []
    for c in available:
        if c in LEAKY_COLS:
            continue
        # Keep core screening fields even when missing is high; drop optional features that are mostly missing.
        if c not in REQUIRED_FEATURES and missing_rate.get(c, 1.0) > MAX_MISSING_RATE:
            dropped_missing.append(c)
            continue
        filtered.append(c)
    X = df[filtered].copy()

    # Drop columns that are entirely missing to avoid imputer warnings/unstable transforms
    all_missing = [c for c in X.columns if X[c].isna().all()]
    if all_missing:
        print("Dropping all-missing features:", all_missing)
        X = X.drop(columns=all_missing)

    if dropped_missing:
        print(f"Dropping high-missing optional features (>{int(MAX_MISSING_RATE*100)}% missing):", dropped_missing)
    feature_cols = list(X.columns)
    nums_inferred, cats_inferred = infer_feature_types(X, feature_cols)
    for c in nums_inferred:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    for c in cats_inferred:
        X[c] = X[c].astype("object")

    # ---- External validation: site-held-out by source_file ----
    if SOURCE_COL in df.columns and df[SOURCE_COL].nunique() >= 3:
        # Hold out one "site" (one file) entirely
        held_out_site = df[SOURCE_COL].value_counts().index[0]
        train_mask = df[SOURCE_COL] != held_out_site
        ext_mask = ~train_mask
    else:
        held_out_site = None
        train_mask = np.ones(len(df), dtype=bool)
        ext_mask = np.zeros(len(df), dtype=bool)

    X_train, y_train = X[train_mask], y[train_mask]
    X_ext, y_ext = X[ext_mask], y[ext_mask]
    search_scoring = "roc_auc" if n_classes == 2 else "roc_auc_ovr_weighted"

    pre = build_preprocess(pd.concat([X_train, X_ext], axis=0), feature_cols)

    models = candidate_models()

    # We will compare:
    # - Each base model with SMOTE and without SMOTE
    # - Calibration: sigmoid vs isotonic (outer fold)
    comparisons = []

    outer = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

    def evaluate_model(name, base_estimator, param_dist, use_smote: bool, calib_method: str):
        # OOF preds for honest metrics
        oof = np.zeros((len(X_train), n_classes), dtype=float)
        best_params_list = []

        use_smote_effective = bool(use_smote and IMBLEARN_AVAILABLE)
        if use_smote and not IMBLEARN_AVAILABLE:
            print("WARNING: imblearn not available/compatible; skipping SMOTE for this run.")

        for fold, (tr_idx, va_idx) in enumerate(outer.split(X_train, y_train), start=1):
            Xtr, Xva = X_train.iloc[tr_idx], X_train.iloc[va_idx]
            ytr, yva = y_train[tr_idx], y_train[va_idx]

            # Inner tuning (RandomizedSearchCV)
            if use_smote_effective:
                pipe = ImbPipeline([
                    ("preprocess", pre),
                    ("smote", SMOTE(random_state=42)),
                    ("model", base_estimator),
                ])
            else:
                pipe = Pipeline([
                    ("preprocess", pre),
                    ("model", base_estimator),
                ])

            search = RandomizedSearchCV(
                pipe,
                param_distributions=param_dist,
                n_iter=min(12, max(6, len(param_dist))),
                scoring=search_scoring,
                cv=3,
                random_state=42,
                n_jobs=-1,
                verbose=0,
            )
            search.fit(Xtr, ytr)
            best = search.best_estimator_
            best_params_list.append(search.best_params_)

            # Calibrate on the training split (no prefit; compatible with new sklearn)
            cal = CalibratedClassifierCV(
                best,
                method=calib_method,
                cv=3,
            )
            cal.fit(Xtr, ytr)
            p_fold = cal.predict_proba(Xva)
            fold_classes = list(cal.classes_)
            for cls_idx in range(n_classes):
                if cls_idx in fold_classes:
                    oof[va_idx, cls_idx] = p_fold[:, fold_classes.index(cls_idx)]
            row_sum = oof[va_idx].sum(axis=1, keepdims=True)
            zero_mask = (row_sum.squeeze() <= 0)
            if np.any(zero_mask):
                oof[va_idx[zero_mask], :] = 1.0 / n_classes
                row_sum = oof[va_idx].sum(axis=1, keepdims=True)
            oof[va_idx] = oof[va_idx] / row_sum

        if n_classes == 2:
            p_pos = oof[:, diabetic_idx]
            auc = roc_auc_score(y_train, p_pos)
            ap = average_precision_score((y_train == diabetic_idx).astype(int), p_pos)
            ece = expected_calibration_error((y_train == diabetic_idx).astype(int), p_pos)
            slope, intercept = calibration_slope_intercept((y_train == diabetic_idx).astype(int), p_pos)
            auc_, lo, hi = delong_auc_ci((y_train == diabetic_idx).astype(int), p_pos, alpha=0.95)
            dca = decision_curve_net_benefit((y_train == diabetic_idx).astype(int), p_pos)
        else:
            auc = roc_auc_score(y_train, oof, multi_class="ovr", average="macro")
            ap = average_precision_score((y_train == diabetic_idx).astype(int), oof[:, diabetic_idx])
            ece = expected_calibration_error((y_train == diabetic_idx).astype(int), oof[:, diabetic_idx])
            slope, intercept = calibration_slope_intercept((y_train == diabetic_idx).astype(int), oof[:, diabetic_idx])
            auc_, lo, hi = np.nan, np.nan, np.nan
            dca = decision_curve_net_benefit((y_train == diabetic_idx).astype(int), oof[:, diabetic_idx])

        brier = multiclass_brier(y_train, oof, n_classes=n_classes)
        yhat = oof.argmax(axis=1)
        acc = accuracy_score(y_train, yhat)
        f1 = f1_score(y_train, yhat, average="macro")
        ll = log_loss(y_train, oof, labels=list(range(n_classes)))

        # Fit final model on all training data using best overall params (median-ish pick)
        # Simpler: re-run search on full train then calibrate with CV.
        if use_smote_effective:
            final_pipe = ImbPipeline([
                ("preprocess", pre),
                ("smote", SMOTE(random_state=42)),
                ("model", base_estimator),
            ])
        else:
            final_pipe = Pipeline([
                ("preprocess", pre),
                ("model", base_estimator),
            ])

        final_search = RandomizedSearchCV(
            final_pipe,
            param_distributions=param_dist,
            n_iter=12,
            scoring=search_scoring,
            cv=3,
            random_state=42,
            n_jobs=-1,
            verbose=0,
        )
        final_search.fit(X_train, y_train)
        final_best = final_search.best_estimator_

        final_cal = CalibratedClassifierCV(final_best, method=calib_method, cv=5)
        final_cal.fit(X_train, y_train)

        ext_metrics = None
        if held_out_site is not None and len(y_ext) > 0 and len(np.unique(y_ext)) >= 2:
            p_ext_raw = final_cal.predict_proba(X_ext)
            p_ext = np.zeros((len(X_ext), n_classes), dtype=float)
            final_classes = list(final_cal.classes_)
            for cls_idx in range(n_classes):
                if cls_idx in final_classes:
                    p_ext[:, cls_idx] = p_ext_raw[:, final_classes.index(cls_idx)]
            row_sum_ext = p_ext.sum(axis=1, keepdims=True)
            zero_ext = (row_sum_ext.squeeze() <= 0)
            if np.any(zero_ext):
                p_ext[zero_ext, :] = 1.0 / n_classes
                row_sum_ext = p_ext.sum(axis=1, keepdims=True)
            p_ext = p_ext / row_sum_ext
            p_ext_t2d = p_ext[:, diabetic_idx]
            ext_metrics = {
                "site": str(held_out_site),
                "auroc_macro_ovr": float(roc_auc_score(y_ext, p_ext, multi_class="ovr", average="macro")) if n_classes > 2 else float(roc_auc_score(y_ext, p_ext_t2d)),
                "auprc_diabetic_vs_rest": float(average_precision_score((y_ext == diabetic_idx).astype(int), p_ext_t2d)),
                "brier_multiclass": float(multiclass_brier(y_ext, p_ext, n_classes=n_classes)),
                "ece_diabetic_vs_rest": float(expected_calibration_error((y_ext == diabetic_idx).astype(int), p_ext_t2d)),
            }

        return {
            "name": name,
            "use_smote": use_smote,
            "calibration": calib_method,
            "oof": {
                "auroc": float(auc),
                "auroc_95ci": [float(lo), float(hi)] if n_classes == 2 else None,
                "auprc_diabetic_vs_rest": float(ap),
                "brier": float(brier),
                "ece_diabetic_vs_rest": float(ece),
                "cal_slope_diabetic_vs_rest": float(slope),
                "cal_intercept_diabetic_vs_rest": float(intercept),
                "accuracy": float(acc),
                "f1": float(f1),
                "log_loss": float(ll),
            },
            "external_site": ext_metrics,
            "dca": dca,
            "final_model": final_cal,
            "final_best_params": final_search.best_params_,
        }

    # Train all candidates
    calib_options = ["sigmoid", "isotonic"] if n_classes == 2 else ["sigmoid"]
    for base_name, (est, dist) in models.items():
        for use_smote in [False, True]:
            for calib in calib_options:
                print(f"Training {base_name} | SMOTE={use_smote} | calib={calib}")
                res = evaluate_model(base_name, est, dist, use_smote, calib)
                comparisons.append(res)

    # Choose best: highest AUROC then lowest Brier
    comparisons_sorted = sorted(
        comparisons,
        key=lambda r: (r["oof"]["auroc"], -r["oof"]["brier"]),
        reverse=True
    )
    best = comparisons_sorted[0]

    # Save artifacts
    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = f"tabular_{best['name']}_cal_{best['calibration']}_smote_{int(best['use_smote'])}"
    model_path = os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
    dump(best["final_model"], model_path)

    # Performance outputs
    perf = {
        "current": {"model_name": model_name, "model_version": version, "model_path": model_path},
        "train_summary": {
            "n_total": int(len(df)),
            "n_train": int(len(X_train)),
            "n_external": int(len(X_ext)),
            "held_out_site": held_out_site,
            "label_counts_train": {
                class_names[i]: int((y_train == i).sum()) for i in range(n_classes)
            },
            "classes": class_names,
            "target_index_diabetic": int(diabetic_idx),
        },
        "best": {
            "oof": best["oof"],
            "external_site": best["external_site"],
            "best_params": best["final_best_params"],
            "calibration": best["calibration"],
            "use_smote": best["use_smote"],
        },
        "comparisons": [
            {
                "name": c["name"],
                "use_smote": c["use_smote"],
                "calibration": c["calibration"],
                **c["oof"],
                "external_site": c["external_site"],
            } for c in comparisons_sorted
        ]
    }

    performance_path = os.path.join(ART_DIR, "performance.json")
    with open(performance_path, "w", encoding="utf-8") as f:
        json.dump(perf, f, indent=2)

    # CSV comparison table
    rows = []
    for c in comparisons_sorted:
        row = {
            "model": c["name"],
            "smote": c["use_smote"],
            "calibration": c["calibration"],
            "auroc_oof": c["oof"]["auroc"],
            "auroc_ci_low": (c["oof"]["auroc_95ci"][0] if c["oof"]["auroc_95ci"] else np.nan),
            "auroc_ci_high": (c["oof"]["auroc_95ci"][1] if c["oof"]["auroc_95ci"] else np.nan),
            "auprc_diabetic_vs_rest_oof": c["oof"]["auprc_diabetic_vs_rest"],
            "brier_oof": c["oof"]["brier"],
            "ece_diabetic_vs_rest_oof": c["oof"]["ece_diabetic_vs_rest"],
            "cal_slope_diabetic_vs_rest": c["oof"]["cal_slope_diabetic_vs_rest"],
            "cal_intercept_diabetic_vs_rest": c["oof"]["cal_intercept_diabetic_vs_rest"],
            "accuracy_oof": c["oof"]["accuracy"],
            "f1_oof": c["oof"]["f1"],
            "log_loss_oof": c["oof"]["log_loss"],
        }
        if c["external_site"]:
            row.update({
                "ext_site": c["external_site"]["site"],
                "ext_auroc_macro_ovr": c["external_site"]["auroc_macro_ovr"],
                "ext_auprc_diabetic_vs_rest": c["external_site"]["auprc_diabetic_vs_rest"],
                "ext_brier_multiclass": c["external_site"]["brier_multiclass"],
                "ext_ece_diabetic_vs_rest": c["external_site"]["ece_diabetic_vs_rest"],
            })
        rows.append(row)

    comp_csv = os.path.join(ART_DIR, "comparison.csv")
    pd.DataFrame(rows).to_csv(comp_csv, index=False)

    # Registry pointer
    registry = {
        "current": {
            "model_name": model_name,
            "model_version": version,
            "model_path": model_path,
            "performance_path": performance_path,
            "comparison_csv": comp_csv,
        }
    }
    registry_path = os.path.join(ART_DIR, "registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    # Model card
    model_card = {
        "model_name": model_name,
        "model_version": version,
        "classes": class_names,
        "target_index_diabetic": int(diabetic_idx),
        "features": feature_cols,
        "pipeline": {
            "preprocess": "median impute + scale numeric; most_frequent impute + onehot categorical",
            "imbalance": "SMOTE inside CV" if best["use_smote"] else "class_weight/balanced only",
            "tuning": "RandomizedSearchCV inner loop (nested CV)",
            "calibration": best["calibration"],
        },
        "metrics_oof": best["oof"],
        "external_validation": best["external_site"],
        "dca": "Saved in performance.json comparisons[*].dca",
        "created_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "limitations": [
            "Primary clinical thresholding remains focused on diabetic-vs-rest risk.",
            "Synthetic dataset may not generalize to real clinics; use site-held-out external validation with real data next.",
        ],
        "intended_use": "Screening support (not a diagnosis). Confirm with lab tests.",
    }
    with open(os.path.join(ART_DIR, "modelcard.json"), "w", encoding="utf-8") as f:
        json.dump(model_card, f, indent=2)

    print("\nBEST MODEL:", model_name, version)
    print("Saved model:", model_path)
    print("Saved performance:", performance_path)
    print("Saved comparison:", comp_csv)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.ml.tabular.train_tabular_pro <csv_path>")
    main(sys.argv[1])
