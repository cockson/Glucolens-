import uuid, json
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.db.models import User, PredictionRecord
from app.api.deps import get_current_user
from app.api.deps_billing import require_active_subscription

from app.ml.tabular.serve import predict_with_explain
from app.ml.retina.serve import predict_retina
from app.ml.skin.serve import predict_skin
from app.ml.genomics.serve import predict_genomics
from app.ml.fusion.serve import fusion_predict
from app.core.thresholds import DEFAULT_FUSION_THRESHOLD, COUNTRY_THRESHOLDS
from fastapi.responses import StreamingResponse
from app.ml.fusion.report import render_fusion_report_pdf
from app.db.models import ThresholdPolicy


router = APIRouter()

def _uuid(): return str(uuid.uuid4())

@router.post("/predict")
def fusion_predict_endpoint(
    # tabular form inputs (JSON-like)
    payload: str = Form(...),
    retina: UploadFile | None = File(None),
    skin: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    payload_obj = json.loads(payload)
    tab = predict_with_explain(payload_obj)
    p_tab = tab["probabilities"]["t2d"]

    p_ret = None
    retina_ok = False
    retina_out = None
    if retina is not None:
        img_bytes = retina.file.read()
        retina_out = predict_retina(img_bytes)
        q = retina_out.get("quality_gate", {})
        retina_ok = bool(q.get("passed", False))
        p_ret = retina_out.get("probabilities", {}).get("t2d")

    skin_out = None
    p_skin = None
    skin_ok = False
    if skin is not None:
        skin_bytes = skin.file.read()
        skin_out = predict_skin(skin_bytes)
        q = skin_out.get("quality_gate", {})
        skin_ok = bool(q.get("passed", False))
        p_skin = (skin_out.get("probabilities") or {}).get("positive")

    genomics_out = None
    p_genomics = None
    geno_ok = False
    genomics_payload = payload_obj.get("genomics")
    if isinstance(genomics_payload, dict) and genomics_payload:
        try:
            genomics_out = predict_genomics(genomics_payload)
            p_genomics = genomics_out.get("probability")
            geno_ok = p_genomics is not None
        except Exception as e:
            genomics_out = {"error": f"genomics_inference_failed: {type(e).__name__}"}

    thr_default = COUNTRY_THRESHOLDS.get(getattr(user, "country_code", "") or "", DEFAULT_FUSION_THRESHOLD)
    thr, thr_meta = get_active_threshold(db, user)
    if thr_meta["scope"] == "default":
        thr = thr_default

    fused = fusion_predict(
        p_tabular=p_tab,
        p_retina=p_ret,
        retina_ok=retina_ok,
        p_skin=p_skin,
        skin_ok=skin_ok,
        p_genomics=p_genomics,
        geno_ok=geno_ok,
        threshold=thr,
    )

    out = {
        "fusion": fused,
        "threshold_used": thr,
        "threshold_meta": thr_meta,
        "tabular": tab,
        "retina": retina_out,
        "skin": skin_out,
        "genomics": genomics_out,
    }

    rec = PredictionRecord(
        id=_uuid(),
        actor_user_id=user.id,
        org_id=user.org_id,
        facility_id=user.facility_id,
        country_code=getattr(user, "country_code", None),
        modality="fusion",
        model_name="fusion",
        model_version="v3",
        consent_version=None,
        consent_json=json.dumps({}, sort_keys=True),
        input_json=json.dumps({"payload": "tabular+optional_retina+optional_skin+optional_genomics", "patient_key": payload_obj.get("patient_key")}, sort_keys=True),
        output_json=json.dumps(out, sort_keys=True),
        predicted_label=fused["final_label"],
        proba_json=json.dumps({"fusion": fused.get("final_proba")}, sort_keys=True),
    )
    db.add(rec)
    db.commit()


    out["prediction_id"] = rec.id
    return out


@router.get("/report/{prediction_id}")
def fusion_report(
    prediction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    rec = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Prediction not found")
    out = json.loads(rec.output_json)
    pdf = render_fusion_report_pdf(out)
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="glucolens_fusion_report_{prediction_id}.pdf"'},
    )


def get_active_threshold(db, user):
    # If DB migrations for threshold governance are not applied yet,
    # silently fall back to defaults so prediction endpoint still works.
    try:
        if not inspect(db.bind).has_table("threshold_policies"):
            return float(DEFAULT_FUSION_THRESHOLD), {"policy_id": None, "scope": "default"}
    except SQLAlchemyError:
        db.rollback()
        return float(DEFAULT_FUSION_THRESHOLD), {"policy_id": None, "scope": "default"}

    # facility-level first
    row = None
    try:
        if user.facility_id:
            row = db.query(ThresholdPolicy).filter(
                ThresholdPolicy.org_id == user.org_id,
                ThresholdPolicy.facility_id == user.facility_id,
                ThresholdPolicy.modality == "fusion",
                ThresholdPolicy.status == "approved"
            ).order_by(ThresholdPolicy.created_at.desc()).first()

        # country-level fallback
        if row is None:
            cc = getattr(user, "country_code", None)
            if cc:
                row = db.query(ThresholdPolicy).filter(
                    ThresholdPolicy.org_id == user.org_id,
                    ThresholdPolicy.country_code == cc,
                    ThresholdPolicy.facility_id.is_(None),
                    ThresholdPolicy.modality == "fusion",
                    ThresholdPolicy.status == "approved"
                ).order_by(ThresholdPolicy.created_at.desc()).first()
    except SQLAlchemyError:
        db.rollback()
        return float(DEFAULT_FUSION_THRESHOLD), {"policy_id": None, "scope": "default"}

    if row:
        return float(row.threshold), {"policy_id": row.id, "scope": "facility" if row.facility_id else "country"}

    return float(DEFAULT_FUSION_THRESHOLD), {"policy_id": None, "scope": "default"}
