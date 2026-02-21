from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.init_db import init_db
from app.core.config import settings
from app.api.routes import auth, tenancy, billing, referral, outcome

app = FastAPI(title=settings.APP_NAME)

# CORS allowlist (production-safe: never "*")
origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}

@app.on_event("startup")
def _startup():
    init_db()

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tenancy.router, prefix="/api/tenancy", tags=["tenancy"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(referral.router, prefix="/api/referrals", tags=["referrals"])
app.include_router(outcome.router, prefix="/api/outcomes", tags=["outcomes"])




