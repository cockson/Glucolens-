import pandas as pd
import numpy as np

def prepare_genomics(df: pd.DataFrame):
    # Drop obvious metadata
    meta = ["id","patient","subject","sample","name"]
    keep = [c for c in df.columns if not any(m in c.lower() for m in meta)]

    X = df[keep].copy()

    # Numeric coercion
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")

    # Missing handling
    X = X.fillna(X.median())

    return X