import uuid
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import Facility, Org, Outcome, PredictionRecord, Referral, Role, User
from app.db.session import get_db
from app.services.model_audit import build_model_audit


router = APIRouter()
ADMIN_ROLES = (Role.facility_admin, Role.org_admin, Role.super_admin)


def _uuid() -> str:
    return str(uuid.uuid4())


def _scoped_query(query, model, user: User):
    if user.role == Role.super_admin:
        return query
    if user.role == Role.org_admin:
        if hasattr(model, "org_id"):
            return query.filter(model.org_id == user.org_id)
        return query
    if user.role == Role.facility_admin:
        if hasattr(model, "facility_id"):
            return query.filter(model.facility_id == user.facility_id)
        if hasattr(model, "org_id"):
            return query.filter(model.org_id == user.org_id)
    return query


@router.post("/seed-super-admin")
def seed_super_admin(
    payload: dict,
    x_setup_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.SETUP_TOKEN or x_setup_token != settings.SETUP_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    if not email or len(password) < 8:
        raise HTTPException(status_code=400, detail="email+password required")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        existing.role = Role.super_admin
        existing.password_hash = hash_password(password)
        existing.is_active = True
        db.commit()
        return {"ok": True, "updated": True}

    user = User(
        id=_uuid(),
        email=email,
        password_hash=hash_password(password),
        role=Role.super_admin,
        org_id=None,
        facility_id=None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return {"ok": True, "created": True}


@router.get("/summary")
def admin_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*ADMIN_ROLES)),
):
    users_q = _scoped_query(db.query(User), User, user)
    orgs_q = db.query(Org) if user.role == Role.super_admin else db.query(Org).filter(Org.id == user.org_id)
    fac_q = _scoped_query(db.query(Facility), Facility, user)
    preds_q = _scoped_query(db.query(PredictionRecord), PredictionRecord, user)
    refs_q = _scoped_query(db.query(Referral), Referral, user)
    outcomes_q = _scoped_query(db.query(Outcome), Outcome, user)

    predictions = preds_q.all()
    by_modality: dict[str, int] = {}
    by_label: dict[str, int] = {}
    for rec in predictions:
        by_modality[rec.modality] = by_modality.get(rec.modality, 0) + 1
        by_label[rec.predicted_label] = by_label.get(rec.predicted_label, 0) + 1

    return {
        "scope": user.role.value,
        "counts": {
            "orgs": orgs_q.count(),
            "facilities": fac_q.count(),
            "users": users_q.count(),
            "predictions": len(predictions),
            "referrals": refs_q.count(),
            "outcomes": outcomes_q.count(),
        },
        "predictions_by_modality": by_modality,
        "predictions_by_label": by_label,
    }


@router.get("/users")
def admin_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*ADMIN_ROLES)),
):
    rows = _scoped_query(db.query(User), User, user).order_by(User.created_at.desc()).limit(100).all()
    return [
        {
            "id": row.id,
            "email": row.email,
            "role": row.role.value,
            "org_id": row.org_id,
            "facility_id": row.facility_id,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/model-audit")
def model_audit(user: User = Depends(require_role(*ADMIN_ROLES))):
    return build_model_audit()
