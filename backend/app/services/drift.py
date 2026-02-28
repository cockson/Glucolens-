import json
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

def psi(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]
    if len(expected) < 50 or len(actual) < 50:
        return None

    quantiles = np.linspace(0, 1, bins+1)
    cuts = np.quantile(expected, quantiles)
    cuts[0] = -np.inf
    cuts[-1] = np.inf

    e_counts, _ = np.histogram(expected, bins=cuts)
    a_counts, _ = np.histogram(actual, bins=cuts)

    e_perc = e_counts / (e_counts.sum() + 1e-9)
    a_perc = a_counts / (a_counts.sum() + 1e-9)

    val = np.sum((a_perc - e_perc) * np.log((a_perc + 1e-9) / (e_perc + 1e-9)))
    return float(val)

def compute_drift_snapshot(baseline_df: pd.DataFrame, current_df: pd.DataFrame, features: list[str]):
    out = {}
    for f in features:
        if f not in baseline_df.columns or f not in current_df.columns:
            continue
        b = pd.to_numeric(baseline_df[f], errors="coerce").values
        c = pd.to_numeric(current_df[f], errors="coerce").values

        p = psi(b, c)
        ks = None
        if len(b[~np.isnan(b)]) >= 50 and len(c[~np.isnan(c)]) >= 50:
            ks_stat, ks_p = ks_2samp(b[~np.isnan(b)], c[~np.isnan(c)])
            ks = {"stat": float(ks_stat), "p_value": float(ks_p)}
        out[f] = {"psi": p, "ks": ks}
    return out