import datetime as dt
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter
from slowapi.util import get_remote_address
from app.db.session import get_db
from fastapi import Request
from app.db.models import User, Role, Org, Facility, RefreshToken, FacilityType
from app.core.security import (
    hash_password, verify_password,
    create_access_token, new_refresh_token, hash_refresh_token
)
from app.schemas.auth import (
    RegisterPublicIn, RegisterBusinessIn,
    LoginIn, TokenOut, RefreshIn, MeOut
)
from app.api.deps import get_current_user


router = APIRouter()


# ---------- Helpers ----------
def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


# ---------- Public Registration ----------
@router.post("/register-public")
@limiter.limit("5/minute")
def register_public(request: Request, payload: RegisterPublicIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=_uuid(),
        email=email,
        password_hash=hash_password(payload.password),
        role=Role.public,
        org_id=None,
        facility_id=None,
    )

    try:
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        org_id=user.org_id,
        facility_id=user.facility_id
    )


# ---------- Business Registration ----------
@router.post("/register-business")
@limiter.limit("3/minute")
def register_business(request: Request, payload: RegisterBusinessIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        # Create organization
        org = Org(
            id=_uuid(),
            name=payload.org_name,
            country_code=payload.country_code.upper(),
        )
        db.add(org)
        db.flush()

        # Create facility
        facility = Facility(
            id=_uuid(),
            org_id=org.id,
            name=payload.facility_name,
            facility_type=FacilityType(payload.facility_type),
            site_code=payload.site_code,
        )
        db.add(facility)
        db.flush()

        # Create admin user
        user = User(
            id=_uuid(),
            email=email,
            password_hash=hash_password(payload.password),
            role=Role.org_admin,
            org_id=org.id,
            facility_id=facility.id,
        )
        db.add(user)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        org_id=user.org_id,
        facility_id=user.facility_id
    )


# ---------- Login ----------
@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")  # brute-force protection
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    user = db.query(User).filter(User.email == email).first()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")


    # TODO: Add subscription lockout check here later

    access = create_access_token(
        user.id,
        user.role.value,
        user.org_id,
        user.facility_id
    )

    raw_refresh = new_refresh_token()

    token_row = RefreshToken(
        id=_uuid(),
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        revoked=False,
        created_at=_utcnow(),
        expires_at=_utcnow() + dt.timedelta(days=30),
    )

    try:
        db.add(token_row)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return TokenOut(
        access_token=access,
        refresh_token=raw_refresh
    )


# ---------- Refresh Token ----------
@router.post("/refresh", response_model=TokenOut)
@limiter.limit("10/minute")
def refresh(request: Request, payload: RefreshIn, db: Session = Depends(get_db)):
    incoming_hash = hash_refresh_token(payload.refresh_token)

    token_row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == incoming_hash
    ).first()

    if not token_row or token_row.revoked:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_row.expires_at < _utcnow():
        token_row.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Expired refresh token")

    user = db.query(User).filter(User.id == token_row.user_id).first()

    if not user or not user.is_active:
        token_row.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="User inactive")

    # Rotate refresh token
    token_row.revoked = True

    new_raw = new_refresh_token()

    new_row = RefreshToken(
        id=_uuid(),
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw),
        revoked=False,
        created_at=_utcnow(),
        expires_at=_utcnow() + dt.timedelta(days=30),
    )

    access = create_access_token(
        user.id,
        user.role.value,
        user.org_id,
        user.facility_id
    )

    try:
        db.add(new_row)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return TokenOut(
        access_token=access,
        refresh_token=new_raw
    )


# ---------- Logout ----------
@router.post("/logout")
@limiter.limit("30/minute")
def logout(request: Request, payload: RefreshIn, db: Session = Depends(get_db)):
    incoming_hash = hash_refresh_token(payload.refresh_token)

    token_row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == incoming_hash
    ).first()

    if token_row:
        token_row.revoked = True
        db.commit()

    return {"ok": True}


# ---------- Current User ----------
@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        org_id=user.org_id,
        facility_id=user.facility_id
    )


# ---------- Health ----------
@router.get("/ping")
def ping():
    return {"module": "auth", "ok": True}