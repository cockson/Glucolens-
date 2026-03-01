from sqlalchemy.orm import Session
from app.db.models import PredictionRecord, Outcome

def link_outcome_to_prediction(db: Session, outcome: Outcome):
    """
    Link by (org_id, patient_key) and optionally referral_id.
    Choose the nearest prior prediction record.
    """
    # Prefer fusion predictions for downstream fusion outcome monitoring,
    # then fall back to tabular if no fusion record is found.
    base = db.query(PredictionRecord).filter(
        PredictionRecord.org_id == outcome.org_id,
    )

    # patient_key is stored inside input_json; for MVP we do substring match.
    # For production: store patient_key separately in PredictionRecord.
    base = base.filter(PredictionRecord.input_json.contains(outcome.patient_key))

    # nearest prior prediction by timestamp
    q_fusion = base.filter(PredictionRecord.modality == "fusion")
    rec = q_fusion.order_by(PredictionRecord.created_at.desc()).first()
    if rec is None:
        q_tabular = base.filter(PredictionRecord.modality == "tabular")
        rec = q_tabular.order_by(PredictionRecord.created_at.desc()).first()
    if rec:
        outcome.linked_prediction_id = rec.id
        db.commit()
        return rec.id
    return None
