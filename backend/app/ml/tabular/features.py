"""
Single source of truth for tabular features.

You will align these with the anthropometric/genomics columns you actually have.
If a column is missing at predict-time, we fill it with NaN and impute.
"""

# Put anthropometric features you *know* you have:
ANTHRO_FEATURES = [
    "age",
    "sex",        # e.g., "M"/"F" or 0/1
    "bmi",
    "waist_circumference",
    "hip_circumference",
    "whr",        # waist-hip ratio (optional)
    "systolic_bp",
    "diastolic_bp",
]

# Put genomics features you actually have (example placeholders):
GENO_FEATURES = [
    # "prs_t2d", "snp_rs7903146", ...
]

TARGET_COL = "diabetes_status"  # for training
CLASSES = ["not_diabetic", "t2d"]  # per your note: current datasets are T2D-labeled; keep binary for now
