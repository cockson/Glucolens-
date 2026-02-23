import datetime as dt
import hashlib
import secrets
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Use a stable passlib-native scheme to avoid bcrypt backend version issues.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(subject: str, role: str, org_id: str | None, facility_id: str | None) -> str:
    # Use timezone-aware UTC to avoid local-time reinterpretation issues.
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + dt.timedelta(minutes=settings.JWT_ACCESS_TTL_MIN)
    payload = {
        "sub": subject,
        "role": role,
        "org_id": org_id,
        "facility_id": facility_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)

def new_refresh_token() -> str:
    # raw token returned to client
    return secrets.token_urlsafe(48)

def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
