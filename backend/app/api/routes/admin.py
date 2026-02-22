import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Role
from app.core.security import hash_password

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())

@router.post("/seed-super-admin")
def seed_super_admin(payload: dict, db: Session = Depends(get_db)):
    # Protect by requiring a one-time setup token from env if you want.
    # For now: ONLY run locally once, then delete/disable route.
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    if not email or len(password) < 8:
        raise HTTPException(status_code=400, detail="email+password required")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        existing.role = Role.super_admin
        existing.password_hash = hash_password(password)
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