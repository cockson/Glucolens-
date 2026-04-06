import uuid, json
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, PredictionRecord
from app.api.deps import get_current_user
from app.api.deps_billing import require_active_subscription

from app.ml.genomics.serve import predict_genomics, load_model_card, load_performance
from app.ml.genomics.report import render_genomics_report_pdf
from app.services.prediction_records import save_prediction_record

router = APIRouter()


def _uuid():
    return str(uuid.uuid4())


def _parse_row_csv_bytes(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="ignore").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise HTTPException(status_code=400, detail="CSV must include header and one data row.")
    headers = [h.strip() for h in lines[0].split(",")]
    values = [v.strip() for v in lines[1].split(",")]
    if len(values) < len(headers):
        values = values + [""] * (len(headers) - len(values))
    row = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        v = values[i] if i < len(values) else ""
        if v == "":
            continue
        try:
            row[h] = float(v)
        except ValueError:
            row[h] = v
    return row


@router.get("/model-card")
def genomics_model_card(user: User = Depends(get_current_user)):
    try:
        return load_model_card()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/performance")
def genomics_performance(user: User = Depends(get_current_user)):
    try:
        return load_performance()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/predict")
def genomics_predict(
    payload: str | None = Form(None),
    row_csv: UploadFile | None = File(None),
    patient_key: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    if not payload and row_csv is None:
        raise HTTPException(status_code=400, detail="Provide payload JSON or row_csv file.")

    input_payload = {}
    if payload:
        try:
            input_payload = json.loads(payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="payload must be valid JSON object")
        if not isinstance(input_payload, dict):
            raise HTTPException(status_code=400, detail="payload must be a JSON object")

    if row_csv is not None:
        row = _parse_row_csv_bytes(row_csv.file.read())
        input_payload = {**row, **input_payload}

    try:
        result = predict_genomics(input_payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"genomics_model_unavailable: {str(e)}")
    result["model_name"] = "genomics"
    result["model_version"] = "v1"

    prediction_id = save_prediction_record(
        db,
        id=_uuid(),
        actor_user_id=user.id,
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=getattr(user, "country_code", None),
        modality="genomics",
        model_name=result["model_name"],
        model_version=result["model_version"],
        consent_version=None,
        consent_json=json.dumps({}, sort_keys=True),
        input_json=json.dumps({"input": "genomics_feature_vector", "patient_key": patient_key, "n_features": len(input_payload)}, sort_keys=True),
        output_json=json.dumps(result, sort_keys=True),
        predicted_label=result["predicted_label"],
        proba_json=json.dumps({"positive": result.get("probability")}, sort_keys=True),
    )
    result["prediction_id"] = prediction_id
    return result


@router.get("/report/{prediction_id}")
def genomics_report(
    prediction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    rec = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred = json.loads(rec.output_json)
    pdf = render_genomics_report_pdf(prediction=pred)
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="glucolens_genomics_report_{prediction_id}.pdf"'},
    )
