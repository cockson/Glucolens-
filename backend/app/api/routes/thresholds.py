import uuid, json, datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Role, ThresholdPolicy
from app.api.deps import get_current_user, require_role
from app.api.deps_billing import require_active_subscription
from app.services.thresholds import compute_dca_threshold_from_outcomes

router = APIRouter()

def _uuid(): return str(uuid.uuid4())

@router.post("/compute")
def compute_threshold(
    facility_id: str | None = None,
    days: int = 180,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.super_admin, Role.org_admin))
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    thr, evidence = compute_dca_threshold_from_outcomes(db, user.org_id, facility_id, days=days)
    if thr is None:
        raise HTTPException(status_code=400, detail=evidence.get("error","Failed to compute threshold"))

    row = ThresholdPolicy(
        id=_uuid(),
        org_id=user.org_id,
        facility_id=facility_id,
        country_code=getattr(user,"country_code",None),
        modality="fusion",
        model_name="fusion",
        model_version="v1",
        method="dca_net_benefit_max",
        threshold=float(thr),
        status="proposed",
        approved_by_user_id=None,
        approved_at=None,
        evidence_json=json.dumps(evidence, sort_keys=True)
    )
    db.add(row)
    db.commit()
    return {"ok": True, "policy_id": row.id, "threshold": thr, "evidence": evidence}

@router.get("/policies")
def list_policies(db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    rows = db.query(ThresholdPolicy).filter(ThresholdPolicy.org_id == user.org_id).order_by(ThresholdPolicy.created_at.desc()).all()
    return [{
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "facility_id": r.facility_id,
        "country_code": r.country_code,
        "threshold": r.threshold,
        "status": r.status,
        "method": r.method,
        "model_name": r.model_name,
        "model_version": r.model_version,
        "evidence": json.loads(r.evidence_json)
    } for r in rows]

@router.post("/approve/{policy_id}")
def approve_policy(policy_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    p = db.query(ThresholdPolicy).filter(ThresholdPolicy.id == policy_id, ThresholdPolicy.org_id == user.org_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")

    # retire any previous approved policy for same scope
    db.query(ThresholdPolicy).filter(
        ThresholdPolicy.org_id == user.org_id,
        ThresholdPolicy.modality == p.modality,
        ThresholdPolicy.facility_id == p.facility_id,
        ThresholdPolicy.country_code == p.country_code,
        ThresholdPolicy.status == "approved"
    ).update({"status":"retired"})

    p.status = "approved"
    p.approved_by_user_id = user.id
    p.approved_at = dt.datetime.utcnow()
    db.commit()

    return {"ok": True, "approved_policy_id": p.id, "threshold": p.threshold}
