from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings


#In dev, you can let it fall back to in-memory if Redis isn't reachable
#but since you said you installed Redis, keeping Redis is fine.
def _storage_uri() -> str | None:
    return settings.REDIS_URL

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri(),
    strategy="fixed-window",
    default_limits=[],
)