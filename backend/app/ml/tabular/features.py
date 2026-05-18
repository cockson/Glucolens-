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
    "systolic_bp",
    "diastolic_bp",
    "bmi_category",
    "family_history_diabetes",
    "physical_activity",
    "smoking_status",
]

# Diagnostic labs/treatment fields are intentionally excluded from model input.
# They may be collected for reporting, but using them to predict a current
# diabetes screening target leaks the answer.
DIAGNOSTIC_LEAKAGE_FEATURES = [
    "fasting_glucose_mgdl",
    "hba1c_pct",
    "on_antidiabetic",
]

# Put genomics features you actually have (example placeholders):
GENO_FEATURES = [
    # "prs_t2d", "snp_rs7903146", ...
]

TARGET_COL = "diabetes_status"  # for training
CLASSES = ["non_diabetic", "prediabetic", "diabetic"]
