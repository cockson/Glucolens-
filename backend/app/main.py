from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import admin
from app.core.config import settings
from app.db.init_db import init_db
from app.api.routes import auth, tenancy, billing, referral, outcome

# Optional: rate limiting (only enable if limiter exists)
try:
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.errors import RateLimitExceeded
    from app.core.rate_limit import limiter  # must define `limiter`
    RATE_LIMITING_ENABLED = True
except Exception:
    RATE_LIMITING_ENABLED = False


app = FastAPI(title=settings.APP_NAME)


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
origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
def _startup():
    init_db()


# --- Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tenancy.router, prefix="/api/tenancy", tags=["tenancy"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(referral.router, prefix="/api/referrals", tags=["referrals"])
app.include_router(outcome.router, prefix="/api/outcomes", tags=["outcomes"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])