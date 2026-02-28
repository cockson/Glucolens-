import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import get_db
from app.db.models import Outcome, User
from app.api.deps_billing import require_active_subscription
from app.services.linkage import link_outcome_to_prediction

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())

def _ensure_linked_prediction_column(db: Session):
    # Lightweight in-app migration for older DBs.
    try:
        db.execute(text("ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS linked_prediction_id VARCHAR"))
        db.commit()
    except SQLAlchemyError:
        db.rollback()

@router.post("/")
def record_outcome(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_active_subscription)):
    _ensure_linked_prediction_column(db)
    row = Outcome(
        id=_uuid(),
        referral_id=payload.get("referral_id"),
        org_id=user.org_id,
        facility_id=user.facility_id,
        patient_key=payload["patient_key"],
        outcome_label=payload["outcome_label"],
        notes=payload.get("notes"),
    )
    db.add(row)
    db.commit()
    new_id = link_outcome_to_prediction(db, row)
    return {"ok": True, "linked_prediction_id": new_id}

@router.get("/")
def list_outcomes(db: Session = Depends(get_db), user: User = Depends(require_active_subscription)):
    rows = db.query(Outcome).filter(Outcome.org_id == user.org_id).order_by(Outcome.recorded_at.desc()).limit(200).all()
    return [{
        "id": o.id,
        "patient_key": o.patient_key,
        "facility_id": o.facility_id,
        "referral_id": o.referral_id,
        "outcome_label": o.outcome_label,
        "recorded_at": o.recorded_at.isoformat(),
    } for o in rows]
