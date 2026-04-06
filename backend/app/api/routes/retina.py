import uuid, json
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import os 
import pandas as pd
import math
from app.db.session import get_db
from app.db.models import User, PredictionRecord
from app.api.deps import get_current_user
from app.api.deps_billing import require_active_subscription

from app.ml.retina.serve import predict_retina, load_model_card
from app.ml.retina.report import render_retina_report_pdf
from app.services.prediction_records import save_prediction_record

router = APIRouter()
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _uuid(): return str(uuid.uuid4())

def _sanitize_json(value):
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    return value

@router.get("/model-card")
def retina_model_card(user: User = Depends(get_current_user)):
    try:
        return load_model_card()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/predict")
def retina_predict(
    file: UploadFile = File(...),
    patient_key: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file")

    img_bytes = file.file.read()
    try:
        result = predict_retina(img_bytes)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"retina_model_unavailable: {str(e)}")

    prediction_id = save_prediction_record(
        db,
        id=_uuid(),
        actor_user_id=user.id,
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=getattr(user, "country_code", None),
        modality="retina",
        model_name=result["model_name"],
        model_version=result["model_version"],
        consent_version=None,
        consent_json=json.dumps({}, sort_keys=True),
        input_json=json.dumps({"input": "retina_image_uploaded", "patient_key": patient_key}, sort_keys=True),
        output_json=json.dumps(result, sort_keys=True),
        predicted_label=result["predicted_label"],
        proba_json=json.dumps(result["probabilities"], sort_keys=True),
    )
    result["prediction_id"] = prediction_id
    return result

@router.get("/report/{prediction_id}")
def retina_report(prediction_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    rec = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred = json.loads(rec.output_json)
    pdf_bytes = render_retina_report_pdf(prediction=pred)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="glucolens_retina_report_{prediction_id}.pdf"'}
    )

@router.get("/performance")
def retina_performance(user: User = Depends(get_current_user)):
    candidates = [
        os.path.join(REPO_ROOT, "artifacts", "retina", "performance.json"),
        os.path.join(REPO_ROOT, "backend", "artifacts", "retina", "performance.json"),
    ]
    comp_candidates = [
        os.path.join(REPO_ROOT, "artifacts", "retina", "comparison.csv"),
        os.path.join(REPO_ROOT, "backend", "artifacts", "retina", "comparison.csv"),
    ]
    path = next((p for p in candidates if os.path.isfile(p)), None)
    comp = next((p for p in comp_candidates if os.path.isfile(p)), None)
    if not path:
        raise HTTPException(status_code=404, detail="Retina performance.json not found. Run evaluate_retina_pro.")
    with open(path, "r", encoding="utf-8") as f:
        perf = _sanitize_json(json.load(f))
    comp_rows = []
    if comp:
        comp_rows = _sanitize_json(pd.read_csv(comp).to_dict(orient="records"))
    return {"performance": perf, "comparison": comp_rows}
