from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import admin
from app.core.config import settings
from app.db.init_db import init_db
from app.api.routes import auth, tenancy, billing, referral, outcome
from app.api.routes import audit
from app.api.routes import predict
from app.api.routes import monitor
from app.api.routes import validation
from app.api.routes import fusion, thresholds, skin, genomics
import redis.asyncio as redis
from fastapi_limiter import FastAPILimiter
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.api.routes import retina
from app.gpt.router import router as gpt_router
from urllib.parse import urlsplit


# Optional: rate limiting (only enable if limiter exists)
try:
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.errors import RateLimitExceeded
    from app.core.rate_limit import limiter  # must define `limiter`
    RATE_LIMITING_ENABLED = True
except Exception:
    RATE_LIMITING_ENABLED = False


app = FastAPI(title=settings.APP_NAME)
app.add_middleware(SecurityHeadersMiddleware)


# --- Rate limiting (optional) ---
if RATE_LIMITING_ENABLED:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


# --- Security headers ---
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.ENV == "prod":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# --- CORS ---
def _normalize_origin(origin: str) -> str | None:
    candidate = origin.strip()
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


origins = []
for candidate in settings.CORS_ALLOW_ORIGINS.split(","):
    normalized_origin = _normalize_origin(candidate)
    if normalized_origin and normalized_origin not in origins:
        origins.append(normalized_origin)

for candidate in (
    settings.FRONTEND_BASE_URL,
    "https://glucolens.pages.com",
    "https://glucolens.pages.dev",
):
    normalized_origin = _normalize_origin(candidate)
    if normalized_origin and normalized_origin not in origins:
        origins.append(normalized_origin)

origin_regex_parts = [
    r"^https://(?:[a-zA-Z0-9-]+\.)?[a-zA-Z0-9-]+\.pages\.dev$",
    r"^https://[a-zA-Z0-9-]+-\d+\.app\.github\.dev$",
]
if settings.ENV == "dev":
    # Developer convenience: allow localhost across ports.
    origin_regex_parts.insert(0, r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")

allow_origin_regex = "|".join(origin_regex_parts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# --- Health ---
@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}



# --- Startup ---
@app.on_event("startup")
async def on_startup():
    # Ensure schema exists for environments that do not run separate migrations.
    init_db()

    if settings.REDIS_URL:
        try:
            r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            await FastAPILimiter.init(r)
        except Exception as exc:
            print(f"Rate limiter disabled: {exc}")


# --- Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tenancy.router, prefix="/api/tenancy", tags=["tenancy"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(referral.router, prefix="/api/referrals", tags=["referrals"])
app.include_router(outcome.router, prefix="/api/outcomes", tags=["outcomes"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(predict.router, prefix="/api/predict", tags=["predict"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitoring"])
app.include_router(validation.router, prefix="/api/validation", tags=["validation"])
app.include_router(retina.router, prefix="/api/retina", tags=["retina"])
app.include_router(fusion.router, prefix="/api/fusion", tags=["fusion"])
app.include_router(thresholds.router, prefix="/api/thresholds", tags=["thresholds"])
app.include_router(skin.router, prefix="/api/skin", tags=["skin"])
app.include_router(genomics.router, prefix="/api/genomics", tags=["genomics"])
app.include_router(gpt_router, prefix="/api")
