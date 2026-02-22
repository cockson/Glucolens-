import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Referral, Facility, User
from app.api.deps_billing import require_active_subscription
from app.services.qr import qr_png_base64
from app.core.config import settings

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())

@router.post("/")
def create_referral(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_active_subscription)):
    # Pharmacy creates referral; hospital can be optional (nearest search in frontend)
    to_facility_id = payload.get("to_facility_id")

    if to_facility_id:
        to_fac = db.query(Facility).filter(Facility.id == to_facility_id).first()
        if not to_fac:
            raise HTTPException(status_code=404, detail="Target facility not found")

    row = Referral(
        id=_uuid(),
        org_id=user.org_id,
        from_facility_id=user.facility_id,
        to_facility_id=to_facility_id,
        patient_key=payload["patient_key"],
        risk_score=int(payload["risk_score"]),
        reason=payload.get("reason", "Diabetes screening referral"),
        status="open",
    )
    db.add(row)
    db.commit()

    # QR points to frontend referral page (hospital scans)
    url = f"{settings.FRONTEND_BASE_URL}/referral/{row.id}"
    qr_b64 = qr_png_base64(url)

    return {"id": row.id, "status": row.status, "referral_url": url, "qr_png_base64": qr_b64}

@router.get("/{referral_id}")
def get_referral(referral_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_subscription)):
    row = db.query(Referral).filter(Referral.id == referral_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Referral not found")

    # Access: org users can view their org’s referrals
    if user.org_id != row.org_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    return {
        "id": row.id,
        "org_id": row.org_id,
        "from_facility_id": row.from_facility_id,
        "to_facility_id": row.to_facility_id,
        "patient_key": row.patient_key,
        "risk_score": row.risk_score,
        "reason": row.reason,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }

@router.post("/{referral_id}/accept")
def accept_referral(referral_id: str, db: Session = Depends(get_db), user: User = Depends(require_active_subscription)):
    row = db.query(Referral).filter(Referral.id == referral_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Referral not found")

    # Hospital/clinic accepts; must be in same org (or you can relax later for cross-org referrals)
    if user.org_id != row.org_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    row.status = "accepted"
    # lock to accepting facility if not set
    if not row.to_facility_id:
        row.to_facility_id = user.facility_id

    db.commit()
    return {"ok": True, "status": row.status, "to_facility_id": row.to_facility_id}