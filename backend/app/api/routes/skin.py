import uuid, json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, PredictionRecord
from app.api.deps import get_current_user
from app.api.deps_billing import require_active_subscription

from app.ml.skin.serve import predict_skin, load_model_card, load_performance
from app.ml.skin.report import render_skin_report_pdf

router = APIRouter()
def _uuid(): return str(uuid.uuid4())

@router.get("/model-card")
def skin_model_card(user: User = Depends(get_current_user)):
    return load_model_card()

@router.get("/performance")
def skin_performance(user: User = Depends(get_current_user)):
    return load_performance()

@router.post("/predict")
def skin_predict(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file")

    img_bytes = file.file.read()
    result = predict_skin(img_bytes)

    rec = PredictionRecord(
        id=_uuid(),
        actor_user_id=user.id,
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=getattr(user, "country_code", None),
        modality="skin",
        model_name=result["model_name"],
        model_version=result["model_version"],
        consent_version=None,
        consent_json=json.dumps({}, sort_keys=True),
        input_json=json.dumps({"input":"skin_image_uploaded"}, sort_keys=True),
        output_json=json.dumps(result, sort_keys=True),
        predicted_label=result["predicted_label"],
        proba_json=json.dumps(result["probabilities"], sort_keys=True),
    )
    db.add(rec); db.commit()

    result["prediction_id"] = rec.id
    return result

@router.get("/report/{prediction_id}")
def skin_report(prediction_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    rec = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred = json.loads(rec.output_json)
    pdf = render_skin_report_pdf(prediction=pred)
    return StreamingResponse(iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="glucolens_skin_report_{prediction_id}.pdf"'})
