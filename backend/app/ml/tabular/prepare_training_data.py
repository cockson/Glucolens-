import os
import re
import numpy as np
import pandas as pd

DATA_DIR = "data/anthropometric_data"
FILES = [
    "ncd_high_ncd_burden.csv",
    "ncd_moderate_ncd_burden.csv",
    "ncd_low_ncd_burden.csv",
]
OUT_FILE = "data/ropometric_data/train_tabular.csv"

# ---- Column alias mapping (handles different naming across files) ----
ALIASES = {
    "age": ["age", "patient_age", "age_years", "ageyrs"],
    "sex": ["sex", "gender"],
    "bmi": ["bmi", "body_mass_index"],
    "waist_circumference": ["waist", "waist_circumference", "waist_cm"],
    "hip_circumference": ["hip", "hip_circumference", "hip_cm"],
    "systolic_bp": ["sbp", "systolic_bp", "systolic", "systolicbloodpressure"],
    "diastolic_bp": ["dbp", "diastolic_bp", "diastolic", "diastolicbloodpressure"],
    # target aliases:
    "diabetes": ["diabetes", "has_diabetes", "dm", "t2d", "diabetes_dx"],
}

CANON_COLS = [
    "age", "sex", "bmi", "waist_circumference", "hip_circumference",
    "systolic_bp", "diastolic_bp",
    "label"  # we will create this
]

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", c.strip().lower()) for c in df.columns]
    return df

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
    for c in ["age","bmi","waist_circumference","hip_circumference","systolic_bp","diastolic_bp"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # ---- Clean unrealistic values (soft rules) ----
    out.loc[(out["age"] < 0) | (out["age"] > 120), "age"] = np.nan
    out.loc[(out["bmi"] < 10) | (out["bmi"] > 80), "bmi"] = np.nan
    out.loc[(out["systolic_bp"] < 70) | (out["systolic_bp"] > 260), "systolic_bp"] = np.nan
    out.loc[(out["diastolic_bp"] < 40) | (out["diastolic_bp"] > 160), "diastolic_bp"] = np.nan

    # ---- Target label creation ----
    # Preferred: dataset contains diabetes indicator.
    # If diabetes is missing, we fall back to a conservative heuristic (NOT ideal, but keeps pipeline runnable).
    if out["diabetes"].notna().any():
        # normalize diabetes column to 0/1
        d = out["diabetes"].astype(str).str.strip().str.lower()
        out["label"] = d.map(lambda v: 1 if v in ["1","true","yes","y","diabetic","t2d"] else 0)
        out["label"] = pd.to_numeric(out["label"], errors="coerce").fillna(0).astype(int)
    else:
        out["label"] = (
            (out["bmi"].fillna(0) >= 30) &
            (out["systolic_bp"].fillna(0) >= 140)
        ).astype(int)

    # drop diabetes helper
    out = out.drop(columns=["diabetes"], errors="ignore")

    # ensure canonical ordering
    for c in CANON_COLS:
        if c not in out.columns:
            out[c] = np.nan
    out = out[CANON_COLS]

    return out

def main():
    dfs = []
    for f in FILES:
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

    # Quick sanity stats
    print("Merged:", merged.shape)
    print("Label counts:\n", merged["label"].value_counts(dropna=False))
    print("Missingness %:\n", (merged.isna().mean()*100).round(1))

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    merged.to_csv(OUT_FILE, index=False)
    print("Saved:", OUT_FILE)

if __name__ == "__main__":
    main()