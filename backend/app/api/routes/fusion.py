import uuid, json, traceback, math
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.db.models import User, PredictionRecord
from app.api.deps import get_current_user
from app.api.deps_billing import require_active_subscription

from app.ml.tabular.serve import predict_tabular
from app.ml.retina.serve import predict_retina
from app.ml.skin.serve import predict_skin
from app.ml.genomics.serve import predict_genomics
from app.ml.fusion.serve import fusion_predict, load_model_card as load_fusion_model_card, load_performance as load_fusion_performance
from app.core.thresholds import DEFAULT_FUSION_THRESHOLD, COUNTRY_THRESHOLDS
from fastapi.responses import StreamingResponse
from app.ml.fusion.report import render_fusion_report_pdf
from app.db.models import ThresholdPolicy
from app.services.prediction_records import save_prediction_record
from app.services.screening_program import build_screening_plan, derive_tabular_features


router = APIRouter()

def _uuid(): return str(uuid.uuid4())

def _to_float(v):
    try:
        x = float(v)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return None

def _fallback_tabular(payload_obj: dict, reason: str):
    # Deterministic heuristic fallback to avoid hard 500 when model schema drifts.
    age = _to_float(payload_obj.get("age"))
    bmi = _to_float(payload_obj.get("bmi"))
    fpg = _to_float(payload_obj.get("fasting_glucose_mgdl"))
    hba1c = _to_float(payload_obj.get("hba1c_pct"))
    sbp = _to_float(payload_obj.get("systolic_bp"))
    dbp = _to_float(payload_obj.get("diastolic_bp"))
    fam = str(payload_obj.get("family_history_diabetes", "")).strip().lower() in {"1", "true", "yes", "y"}

    score = 0.08
    if age is not None: score += min(max((age - 35.0) / 150.0, 0.0), 0.25)
    if bmi is not None: score += min(max((bmi - 24.0) / 80.0, 0.0), 0.25)
    if fpg is not None: score += min(max((fpg - 95.0) / 220.0, 0.0), 0.35)
    if hba1c is not None: score += min(max((hba1c - 5.4) / 8.0, 0.0), 0.35)
    if sbp is not None and dbp is not None:
        pp = sbp - dbp
        score += min(max((pp - 40.0) / 120.0, 0.0), 0.08)
    if fam:
        score += 0.08

    p_t2d = float(min(max(score, 0.01), 0.99))
    label = "diabetic" if p_t2d >= 0.65 else ("prediabetic" if p_t2d >= 0.40 else "non_diabetic")
    return {
        "model_name": "tabular_fallback_heuristic",
        "model_version": "v1",
        "predicted_label": label,
        "probabilities": {
            "non_diabetic": float(max(0.0, 1.0 - p_t2d - 0.10)),
            "prediabetic": float(0.10 if p_t2d >= 0.20 else 0.05),
            "diabetic": p_t2d,
            "t2d": p_t2d,
        },
        "fallback_reason": reason,
    }

@router.get("/model-card")
def fusion_model_card(user: User = Depends(get_current_user)):
    try:
        return load_fusion_model_card()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/performance")
def fusion_performance(user: User = Depends(get_current_user)):
    try:
        return load_fusion_performance()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

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

    try:
        payload_obj = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload must be valid JSON")
    if not isinstance(payload_obj, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    tabular_inputs = derive_tabular_features({k: v for k, v in payload_obj.items() if k != "genomics"})
    genomics_inputs = payload_obj.get("genomics") if isinstance(payload_obj.get("genomics"), dict) else None

    prediction_id = None
    try:
        try:
            tab = predict_tabular(payload_obj)
        except Exception as tab_err:
            tab = _fallback_tabular(payload_obj, f"{type(tab_err).__name__}: {str(tab_err)}")
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
            "tabular_inputs": tabular_inputs,
            "retina": retina_out,
            "skin": skin_out,
            "genomics": genomics_out,
            "screening_plan": build_screening_plan(
                fusion=fused,
                tabular=tab,
                threshold=thr,
            ),
        }

        prediction_id = save_prediction_record(
            db,
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
            input_json=json.dumps(
                {
                    "tabular_inputs": tabular_inputs,
                    "genomics_inputs": genomics_inputs,
                    "patient_key": payload_obj.get("patient_key"),
                    "has_retina": retina is not None,
                    "has_skin": skin is not None,
                },
                sort_keys=True,
            ),
            output_json=json.dumps(out, sort_keys=True),
            predicted_label=fused["final_label"],
            proba_json=json.dumps({"fusion": fused.get("final_proba")}, sort_keys=True),
        )
    except HTTPException:
        raise
    except FileNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"fusion_model_unavailable: {str(e)}")
    except Exception as e:
        db.rollback()
        detail = f"fusion_predict_failed: {type(e).__name__}: {str(e)}"
        # Include the final traceback line to speed up production debugging.
        try:
            tb_last = traceback.format_exc().strip().splitlines()[-1]
            if tb_last and tb_last not in detail:
                detail = f"{detail} | {tb_last}"
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=detail)

    out["prediction_id"] = prediction_id
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
    if not isinstance(out.get("tabular_inputs"), dict):
        try:
            inp = json.loads(rec.input_json or "{}")
        except Exception:
            inp = {}
        if isinstance(inp.get("tabular_inputs"), dict):
            out["tabular_inputs"] = inp["tabular_inputs"]
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
