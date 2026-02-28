import json
import numpy as np
from sqlalchemy.orm import Session
from sklearn.metrics import roc_auc_score, brier_score_loss

def _safe_json(s):
    try: return json.loads(s)
    except: return None

def compute_outcome_monitoring(db: Session, org_id: str, days: int = 30):
    """
    Calculates observed outcome rates vs predicted risk for linked outcomes.
    """
    from datetime import datetime, timedelta
    from app.db.models import Outcome, PredictionRecord

    since = datetime.utcnow() - timedelta(days=days)

    outcomes = db.query(Outcome).filter(
        Outcome.org_id == org_id,
        Outcome.recorded_at >= since,
        Outcome.linked_prediction_id.isnot(None)
    ).all()

    if not outcomes:
        return {"n": 0, "message": "No linked outcomes in window"}

    y = []
    p = []

    for o in outcomes:
        rec = db.query(PredictionRecord).filter(PredictionRecord.id == o.linked_prediction_id).first()
        if not rec:
            continue
        out = _safe_json(rec.output_json) or {}
        probs = out.get("probabilities") or {}
        pt2d = probs.get("t2d")
        if pt2d is None:
            continue

        # map outcome labels to binary (t2d positive)
        y.append(1 if o.outcome_label in ["confirmed_t2d"] else 0)
        p.append(float(pt2d))

    y = np.asarray(y)
    p = np.asarray(p)

    if len(np.unique(y)) < 2:
        auroc = None
    else:
        auroc = float(roc_auc_score(y, p))

    brier = float(brier_score_loss(y, p))

    # calibration buckets
    bins = np.linspace(0, 1, 11)
    bucket = []
    for i in range(10):
        lo, hi = bins[i], bins[i+1]
        mask = (p >= lo) & (p < hi) if i < 9 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        bucket.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "n": int(mask.sum()),
            "avg_pred": float(p[mask].mean()),
            "obs_rate": float(y[mask].mean())
        })

    return {
        "n": int(len(y)),
        "days": days,
        "auroc": auroc,
        "brier": brier,
        "calibration_buckets": bucket
    }