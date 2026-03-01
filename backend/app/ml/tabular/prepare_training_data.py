import os
import re
import json
import numpy as np
import pandas as pd

DATA_DIR = "data/anthropometric_data"
DEFAULT_FILES = [
    "ncd_high_ncd_burden.csv",
    "ncd_moderate_ncd_burden.csv",
    "ncd_low_ncd_burden.csv",
]
# Keep both outputs for backward compatibility with existing scripts.
OUT_FILES = [
    "data/anthropometric_data/train_tabular.csv",
    "data/ropometric_data/train_tabular.csv",
]

# ---- Column alias mapping (handles different naming across files) ----
ALIASES = {
    "age": ["age", "patient_age", "age_years", "ageyrs"],
    "sex": ["sex", "gender"],
    "bmi": ["bmi", "body_mass_index"],
    "waist_circumference": ["waist", "waist_circumference", "waist_cm", "waist_circumference_cm", "waist_circ"],
    "systolic_bp": ["sbp", "systolic_bp", "systolic", "systolicbloodpressure", "systolic_bp_mmhg"],
    "diastolic_bp": ["dbp", "diastolic_bp", "diastolic", "diastolicbloodpressure", "diastolic_bp_mmhg"],
    "bmi_category": ["bmi_category"],
    "central_obesity": ["central_obesity"],
    "smoking_status": ["smoking_status"],
    "alcohol_use": ["alcohol_use"],
    "physical_activity": ["physical_activity"],
    "family_history_diabetes": ["family_history_diabetes"],
    "family_history_cvd": ["family_history_cvd"],
    "hypertension_status": ["hypertension_status"],
    "fasting_glucose_mgdl": ["fasting_glucose_mgdl", "fasting_glucose", "fbg_mgdl"],
    "hba1c_pct": ["hba1c_pct", "hba1c", "hba1c_percent"],
    "total_cholesterol_mgdl": ["total_cholesterol_mgdl", "total_cholesterol"],
    "hdl_mgdl": ["hdl_mgdl", "hdl"],
    "ldl_mgdl": ["ldl_mgdl", "ldl"],
    "triglycerides_mgdl": ["triglycerides_mgdl", "triglycerides"],
    "cvd_risk_10yr_pct": ["cvd_risk_10yr_pct", "cvd_risk_10yr"],
    "cvd_risk_category": ["cvd_risk_category"],
    "on_antihypertensive": ["on_antihypertensive"],
    "on_statin": ["on_statin"],
    "on_antidiabetic": ["on_antidiabetic"],
    # target aliases:
    "diabetes_status": ["diabetes_status", "diabetic_status", "diabete_status", "diabetesstatus", "diabetes", "has_diabetes", "dm", "t2d", "diabetes_dx"],
}

CANON_COLS = [
    "age", "sex", "bmi", "waist_circumference",
    "systolic_bp", "diastolic_bp",
    "pulse_pressure",
    "bmi_category", "central_obesity", "smoking_status", "alcohol_use", "physical_activity",
    "family_history_diabetes", "family_history_cvd", "hypertension_status",
    "fasting_glucose_mgdl", "hba1c_pct",
    "total_cholesterol_mgdl", "hdl_mgdl", "ldl_mgdl", "triglycerides_mgdl",
    "cvd_risk_10yr_pct", "cvd_risk_category", "on_antihypertensive", "on_statin", "on_antidiabetic",
    "diabetes_status", "diabetic_status", "label"
]

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", c.strip().lower()).replace("-", "_") for c in df.columns]
    return df

def discover_input_files() -> list[str]:
    """
    Auto-discover CSVs in DATA_DIR so additional site files are included automatically.
    Excludes generated output files.
    """
    if not os.path.isdir(DATA_DIR):
        return DEFAULT_FILES

    blocked = {os.path.basename(p).lower() for p in OUT_FILES}
    files = []
    for name in os.listdir(DATA_DIR):
        if not name.lower().endswith(".csv"):
            continue
        if name.lower() in blocked:
            continue
        files.append(name)
    return sorted(files) if files else DEFAULT_FILES

def pick_first(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def map_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    out = pd.DataFrame(index=df.index)

    for canon, candidates in ALIASES.items():
        col = pick_first(df, candidates)
        if col is not None:
            out[canon] = df[col]
        else:
            out[canon] = np.nan

    # ---- Sex normalization ----
    if "sex" in out.columns:
        out["sex"] = out["sex"].astype(str).str.strip().str.lower()
        out["sex"] = out["sex"].replace({
            "male":"M", "m":"M", "1":"M", "man":"M",
            "female":"F", "f":"F", "0":"F", "woman":"F",
        })
        # leave unknowns as NaN
        out.loc[~out["sex"].isin(["M","F"]), "sex"] = np.nan

    # ---- Numeric coercion ----
    for c in [
        "age", "bmi", "waist_circumference", "systolic_bp", "diastolic_bp",
        "fasting_glucose_mgdl", "hba1c_pct", "total_cholesterol_mgdl", "hdl_mgdl",
        "ldl_mgdl", "triglycerides_mgdl", "cvd_risk_10yr_pct"
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    # ---- Clean unrealistic values (soft rules) ----
    out.loc[(out["age"] < 0) | (out["age"] > 120), "age"] = np.nan
    out.loc[(out["bmi"] < 10) | (out["bmi"] > 80), "bmi"] = np.nan
    out.loc[(out["systolic_bp"] < 70) | (out["systolic_bp"] > 260), "systolic_bp"] = np.nan
    out.loc[(out["diastolic_bp"] < 40) | (out["diastolic_bp"] > 160), "diastolic_bp"] = np.nan
    out["pulse_pressure"] = out["systolic_bp"] - out["diastolic_bp"]
    out.loc[(out["pulse_pressure"] < 10) | (out["pulse_pressure"] > 180), "pulse_pressure"] = np.nan

    # ---- Categorical normalization ----
    cat_cols = [
        "bmi_category", "central_obesity", "smoking_status", "alcohol_use", "physical_activity",
        "family_history_diabetes", "family_history_cvd", "hypertension_status",
        "cvd_risk_category", "on_antihypertensive", "on_statin", "on_antidiabetic",
    ]
    for c in cat_cols:
        out[c] = out[c].astype(str).str.strip().str.lower()
        out.loc[out[c].isin(["", "nan", "none", "null", "na", "n/a"]), c] = np.nan

    # ---- Target label creation ----
    # Keep 3-class diabetes_status for multiclass training.
    d = out["diabetes_status"].astype(str).str.strip().str.lower()
    non_diabetic = {"0", "false", "no", "n", "normal", "healthy", "not_diabetic", "non-diabetic", "nondiabetic"}
    prediabetic = {"prediabetes", "prediabetic", "pre-diabetes", "pre_diabetes", "impaired_glucose_tolerance"}
    diabetic = {"1", "true", "yes", "y", "diabetic", "diabetes", "positive", "t2d", "type2", "type_2", "type-2"}

    status = d.map(
        lambda v: "non_diabetic" if v in non_diabetic else (
            "prediabetic" if v in prediabetic else ("diabetic" if v in diabetic else np.nan)
        )
    )
    out["diabetes_status"] = status
    out["diabetic_status"] = status

    # Keep binary label for existing monitoring/validation workflows (t2d-confirmed vs others).
    out["label"] = out["diabetes_status"].map({
        "non_diabetic": 0,
        "prediabetic": 0,
        "diabetic": 1,
    })

    # ensure canonical ordering
    for c in CANON_COLS:
        if c not in out.columns:
            out[c] = np.nan
    out = out[CANON_COLS]

    return out

def main():
    files = discover_input_files()
    print("Input files:", files)
    dfs = []
    for f in files:
        path = os.path.join(DATA_DIR, f)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        df = pd.read_csv(path)
        df2 = map_to_canonical(df)
        df2["source_file"] = f
        dfs.append(df2)

    merged = pd.concat(dfs, ignore_index=True)

    # remove rows with missing label
    merged = merged.dropna(subset=["label"])
    merged["label"] = merged["label"].astype(int)
    before = len(merged)

    # Remove exact duplicates after canonical mapping.
    merged = merged.drop_duplicates().reset_index(drop=True)
    n_dedup = before - len(merged)

    # Keep rows with essential screening features + target.
    critical = ["age", "sex", "bmi", "waist_circumference", "systolic_bp", "diastolic_bp", "diabetes_status"]
    merged = merged.dropna(subset=critical).reset_index(drop=True)

    # Quick sanity stats
    print("Merged:", merged.shape)
    print("Deduplicated rows removed:", n_dedup)
    print("Class counts (diabetes_status):\n", merged["diabetes_status"].value_counts(dropna=False))
    print("Label counts (binary helper):\n", merged["label"].value_counts(dropna=False))
    print("Missingness %:\n", (merged.isna().mean()*100).round(1))

    for out_file in OUT_FILES:
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        merged.to_csv(out_file, index=False)
        print("Saved:", out_file)

    summary = {
        "n_rows": int(len(merged)),
        "n_features": int(merged.shape[1]),
        "classes": merged["diabetes_status"].value_counts(dropna=False).to_dict(),
        "label_binary": merged["label"].value_counts(dropna=False).to_dict(),
        "missing_pct": (merged.isna().mean() * 100).round(2).to_dict(),
        "input_files": files,
        "deduplicated_rows_removed": int(n_dedup),
    }
    summary_path = os.path.join("data", "anthropometric_data", "train_tabular.summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("Saved:", summary_path)

if __name__ == "__main__":
    main()
