import uuid, json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import pandas as pd

from app.db.session import get_db
from app.db.models import User, PredictionRecord, DriftSnapshot
from app.api.deps_billing import require_active_subscription
from app.api.deps import get_current_user

from app.services.monitoring import compute_outcome_monitoring
from app.services.drift import compute_drift_snapshot
from app.ml.tabular.serve import load_registry
from app.ml.tabular.serve import load_model_card

router = APIRouter()

def _uuid(): return str(uuid.uuid4())

@router.get("/outcomes")
def outcome_monitor(days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    if not user.org_id:
        return {"n": 0, "message": "No org_id"}
    return compute_outcome_monitoring(db, user.org_id, days=days)

@router.get("/simulation/flagged")
def simulate_flagged(threshold: float = 0.5, days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    if not user.org_id:
        return {"n": 0, "message": "No org_id"}

    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(PredictionRecord).filter(
        PredictionRecord.org_id == user.org_id,
        PredictionRecord.created_at >= since,
        PredictionRecord.modality == "tabular"
    ).all()

    flagged = 0
    for r in rows:
        out = json.loads(r.output_json)
        pt2d = out.get("probabilities", {}).get("t2d", 0)
        if float(pt2d) >= threshold:
            flagged += 1

    return {
        "days": days,
        "threshold": threshold,
        "predictions_total": len(rows),
        "patients_flagged": flagged,
        "message": f"If deployed in this org, {flagged} patients flagged in the last {days} days"
    }

@router.post("/drift/snapshot")
def drift_snapshot(window_days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    if not user.org_id:
        raise HTTPException(status_code=400, detail="No org_id")

    reg = load_registry()
    model_name = reg["model_name"]
    model_version = reg["model_version"]

    card = load_model_card()
    features = card.get("features") or []

    # Baseline: use earliest N predictions as baseline for now (MVP)
    all_rows = db.query(PredictionRecord).filter(
        PredictionRecord.org_id == user.org_id,
        PredictionRecord.modality == "tabular"
    ).order_by(PredictionRecord.created_at.asc()).all()

    if len(all_rows) < 100:
        raise HTTPException(status_code=400, detail="Not enough predictions to compute drift (need >=100)")

    baseline_rows = all_rows[: min(500, len(all_rows)//2)]
    current_rows = all_rows[-min(500, len(all_rows)//2):]

    def to_df(rows):
        xs = []
        for r in rows:
            try:
                payload = json.loads(r.input_json)
                xs.append(payload)
            except:
                pass
        return pd.DataFrame(xs)

    baseline_df = to_df(baseline_rows)
    current_df = to_df(current_rows)

    metrics = compute_drift_snapshot(baseline_df, current_df, features)

    snap = DriftSnapshot(
        id=_uuid(),
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=user.country_code if hasattr(user, "country_code") else None,
        modality="tabular",
        model_name=model_name,
        model_version=model_version,
        window=f"last_{window_days}d",
        baseline_window="historical",
        metrics_json=json.dumps(metrics, sort_keys=True),
    )
    db.add(snap)
    db.commit()

    return {"ok": True, "snapshot_id": snap.id, "metrics": metrics}

@router.get("/drift/latest")
def drift_latest(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    if not user.org_id:
        return {"ok": True, "message": "No org_id"}

    row = db.query(DriftSnapshot).filter(
        DriftSnapshot.org_id == user.org_id
    ).order_by(DriftSnapshot.created_at.desc()).first()

    if not row:
        return {"ok": True, "message": "No drift snapshots"}

    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "model_name": row.model_name,
        "model_version": row.model_version,
        "window": row.window,
        "baseline_window": row.baseline_window,
        "metrics": json.loads(row.metrics_json),
    }