import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression

# DeLong (binary)
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
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score).astype(float)

    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    m, n = len(pos), len(neg)
    if m == 0 or n == 0:
        return np.nan, np.nan, np.nan

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
    lo = auc - z*se
    hi = auc + z*se
    return float(auc), float(max(0, lo)), float(min(1, hi))

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
    eps = 1e-6
    p = np.clip(p, eps, 1-eps)
    logit = np.log(p/(1-p)).reshape(-1,1)
    lr = LogisticRegression(solver="lbfgs")
    lr.fit(logit, y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])

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

def compute_external_metrics(y_true, p_t2d):
    y_true = np.asarray(y_true).astype(int)
    p_t2d = np.asarray(p_t2d).astype(float)

    auc = roc_auc_score(y_true, p_t2d) if len(np.unique(y_true)) == 2 else None
    auprc = average_precision_score(y_true, p_t2d) if len(np.unique(y_true)) == 2 else None

    brier = float(brier_score_loss(y_true, p_t2d))
    ece = expected_calibration_error(y_true, p_t2d)
    slope, intercept = calibration_slope_intercept(y_true, p_t2d)

    # log loss expects [p0, p1]
    ll = float(log_loss(y_true, np.vstack([1-p_t2d, p_t2d]).T, labels=[0,1]))

    auc_ci = None
    if len(np.unique(y_true)) == 2:
        a, lo, hi = delong_auc_ci(y_true, p_t2d, alpha=0.95)
        auc_ci = {"auroc": a, "ci_low": lo, "ci_high": hi}

    dca = decision_curve_net_benefit(y_true, p_t2d)

    return {
        "n": int(len(y_true)),
        "positive_rate": float(y_true.mean()),
        "auroc": auc,
        "auprc": auprc,
        "auroc_delong_95ci": auc_ci,
        "brier": brier,
        "ece": ece,
        "cal_slope": slope,
        "cal_intercept": intercept,
        "log_loss": ll,
        "decision_curve": dca
    }