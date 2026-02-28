import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from sklearn.linear_model import LogisticRegression

def build_preprocess(numeric_cols, categorical_cols):
    num = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler())
    ])

    cat = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore"))
    ])

    return ColumnTransformer(
        transformers=[
            ("num", num, numeric_cols),
            ("cat", cat, categorical_cols),
        ],
        remainder="drop",
        sparse_threshold=0.3,
    )

def build_baseline_model():
    # Strong baseline for tabular: Logistic Regression + class_weight for imbalance
    return LogisticRegression(
        max_iter=500,
        class_weight="balanced",
        solver="lbfgs",
    )