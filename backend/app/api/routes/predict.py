import uuid
import json
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import PredictionRecord, User
from app.api.deps_billing import require_active_subscription
from app.api.deps import get_current_user
from app.ml.tabular.serve import predict_with_explain
from fastapi.responses import StreamingResponse
from app.ml.tabular.serve import load_model_card, load_performance
from app.ml.tabular.report import render_tabular_report_pdf
from app.db.models import Role

router = APIRouter()

def _uuid() -> str:
    return str(uuid.uuid4())


def _predict_and_store(payload: dict, db: Session, user: User):
    try:
        result = predict_with_explain(payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"tabular_model_unavailable: {str(e)}")

    rec = PredictionRecord(
        id=_uuid(),
        actor_user_id=user.id,
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=payload.get("country_code"),
        modality="tabular",
        model_name=result["model_name"],
        model_version=result["model_version"],
        consent_version=(payload.get("consent") or {}).get("version"),
        consent_json=json.dumps(payload.get("consent") or {}, sort_keys=True),
        input_json=json.dumps(payload, sort_keys=True),
        output_json=json.dumps(result, sort_keys=True),
        predicted_label=result["predicted_label"],
        proba_json=json.dumps(result["probabilities"], sort_keys=True),
    )
    db.add(rec)
    db.commit()
    result["prediction_id"] = rec.id
    return result


@router.get("/tabular/model-card")
def tabular_model_card(user: User = Depends(get_current_user)):
    # model card can be visible to any authenticated user (public included)
    try:
        return load_model_card()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tabular/public", dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def predict_tabular_public(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Public-only endpoint with tighter rate limit.
    """
    if user.role != "public":
        raise HTTPException(status_code=403, detail="Use /api/predict/tabular for business users")

    return _predict_and_store(payload=payload, db=db, user=user)


@router.post("/tabular", dependencies=[Depends(RateLimiter(times=60, seconds=60))])
def predict_tabular(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Accepts a dict of feature->value. Missing features allowed.
    Returns calibrated probabilities + SHAP top features.
    Persists non-PHI payload + output for monitoring.
    """
    if user.role == "public":
        raise HTTPException(status_code=403, detail="Use /api/predict/tabular/public for public users")

    require_active_subscription(user=user, db=db)
    return _predict_and_store(payload=payload, db=db, user=user)


@router.get("/tabular/performance")
def tabular_performance(user: User = Depends(get_current_user)):
    try:
        perf, comp = load_performance()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"performance": perf, "comparison": comp}

@router.get("/tabular/report/{prediction_id}")
def tabular_report(prediction_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # business users require active subscription to download clinical PDF
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    rec = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred = json.loads(rec.output_json)
    model_card = load_model_card()
    perf = load_performance()[0]

    pdf_bytes = render_tabular_report_pdf(prediction=pred, model_card=model_card, performance=perf)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="glucolens_tabular_report_{prediction_id}.pdf"'}
    )

