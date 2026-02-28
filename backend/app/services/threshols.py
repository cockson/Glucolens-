import json
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.db.models import Outcome, PredictionRecord
from app.services.validation_metrics import decision_curve_net_benefit

def compute_dca_threshold_from_outcomes(
    db: Session,
    org_id: str,
    facility_id: str | None,
    days: int = 180,
):
    """
    Uses linked outcomes -> gathers fusion probabilities (or tab+ret fusion if stored)
    and finds threshold maximizing net benefit.
    """
    since = datetime.utcnow() - timedelta(days=days)

    q = db.query(Outcome).filter(
        Outcome.org_id == org_id,
        Outcome.recorded_at >= since,
        Outcome.linked_prediction_id.isnot(None),
    )
    if facility_id:
        q = q.filter(Outcome.facility_id == facility_id)

    outcomes = q.all()
    if len(outcomes) < 50:
        return None, {"error": "Not enough linked outcomes (need >=50)"}

    y = []
    p = []
    for o in outcomes:
        rec = db.query(PredictionRecord).filter(PredictionRecord.id == o.linked_prediction_id).first()
        if not rec:
            continue

        out = json.loads(rec.output_json)

        # Prefer fusion proba if record is fusion; else fallback to tabular proba
        if rec.modality == "fusion":
            fp = (out.get("fusion") or {}).get("final_proba")
            if fp is None:
                continue
            prob = float(fp)
        else:
            prob = float((out.get("probabilities") or {}).get("t2d", 0.0))

        label = 1 if o.outcome_label in ["confirmed_t2d"] else 0
        y.append(label)
        p.append(prob)

    if len(set(y)) < 2:
        return None, {"error": "Need both classes in linked outcomes"}

    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)

    curve = decision_curve_net_benefit(y, p, thresholds=np.linspace(0.05, 0.95, 19))
    best = max(curve, key=lambda r: r["net_benefit"])
    thr = float(best["threshold"])

    evidence = {
        "window_days": days,
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "best_threshold": thr,
        "best_net_benefit": float(best["net_benefit"]),
        "curve": curve
    }
    return thr, evidence