import re

import pandas as pd
import numpy as np


CLINICAL_OVERLAP_FEATURES = {
    "age",
    "age_years",
    "patient_age",
    "bmi",
    "body_mass_index",
    "hba1c",
    "hba1c_pct",
    "hba1c_percent",
    "fasting_glucose",
    "fasting_glucose_mgdl",
    "fbg",
    "fbg_mgdl",
    "glucose",
    "glucose_mgdl",
    "sex",
    "gender",
    "waist",
    "waist_circumference",
    "waist_circumference_cm",
    "systolic_bp",
    "diastolic_bp",
    "sbp",
    "dbp",
}

CLINICAL_OVERLAP_PATTERNS = (
    re.compile(r"(^|_)hba1c($|_)", re.IGNORECASE),
    re.compile(r"(^|_)(fasting_)?glucose($|_)", re.IGNORECASE),
    re.compile(r"(^|_)fbg($|_)", re.IGNORECASE),
    re.compile(r"(^|_)bmi($|_)", re.IGNORECASE),
    re.compile(r"(^|_)(age|sex|gender)($|_)", re.IGNORECASE),
    re.compile(r"(^|_)(waist|systolic|diastolic|sbp|dbp)($|_)", re.IGNORECASE),
)

GENOMIC_ID_RE = re.compile(r"(^rs\d+$|_rs\d+$|^prs_|_prs$|polygenic|genotype|snp)", re.IGNORECASE)


def normalize_feature_name(column: str) -> str:
    return str(column).strip().lower().replace("-", "_").replace(" ", "_")


def is_clinical_overlap_feature(column: str) -> bool:
    normalized = normalize_feature_name(column)
    if normalized in CLINICAL_OVERLAP_FEATURES:
        return True
    return any(pattern.search(normalized) for pattern in CLINICAL_OVERLAP_PATTERNS)


def is_genomic_feature(column: str) -> bool:
    normalized = normalize_feature_name(column)
    if is_clinical_overlap_feature(column):
        return False
    return bool(GENOMIC_ID_RE.search(normalized))

def prepare_genomics(df: pd.DataFrame):
    # Drop obvious metadata and any clinical/anthropometric overlap.
    meta = ["id", "patient", "subject", "sample", "name", "status", "target", "outcome", "label"]
    keep = [
        c for c in df.columns
        if not any(m in str(c).lower() for m in meta)
        and is_genomic_feature(str(c))
    ]
    if not keep:
        raise ValueError("No genomic-only features found after removing clinical overlap columns.")

    X = df[keep].copy()

    # Numeric coercion
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")

    # Missing handling
    X = X.fillna(X.median())

    return X
