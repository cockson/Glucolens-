import os, json
import pandas as pd
from sqlalchemy import text
from app.db.session import SessionLocal
from app.db.models import Outcome, PredictionRecord

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(REPO_ROOT, "data", "fusion_train.csv")
COLUMNS = ["p_tabular", "p_retina", "retina_ok", "label"]


def _has_outcome_linked_prediction_id(db) -> bool:
    try:
        # PostgreSQL-safe check for existing column in current schema.
        q = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'outcomes' AND column_name = 'linked_prediction_id'
            LIMIT 1
            """
        )
        return db.execute(q).first() is not None
    except Exception:
        return False


def _load_outcomes(db, has_link_col: bool):
    if has_link_col:
        return db.query(Outcome).filter(Outcome.linked_prediction_id.isnot(None)).all()

    # Avoid ORM model select when DB schema is behind model definition.
    q = text(
        """
        SELECT id, referral_id, org_id, facility_id, patient_key, outcome_label, notes, recorded_at
        FROM outcomes
        """
    )
    return db.execute(q).mappings().all()


def _extract_t2d_proba(rec: PredictionRecord):
    try:
        out = json.loads(rec.output_json or "{}")
        p = (out.get("probabilities") or {}).get("t2d")
        if p is not None:
            return float(p)
    except Exception:
        pass
    try:
        pjson = json.loads(rec.proba_json or "{}")
        p = pjson.get("t2d")
        if p is not None:
            return float(p)
    except Exception:
        pass
    return None


def _find_tabular_record(db, org_id, patient_key, recorded_at):
    if patient_key:
        rec = db.query(PredictionRecord).filter(
            PredictionRecord.org_id == org_id,
            PredictionRecord.modality == "tabular",
            PredictionRecord.input_json.contains(patient_key),
        ).order_by(PredictionRecord.created_at.desc()).first()
        if rec:
            return rec
    q = db.query(PredictionRecord).filter(
        PredictionRecord.org_id == org_id,
        PredictionRecord.modality == "tabular",
    )
    if recorded_at is not None:
        q = q.filter(PredictionRecord.created_at <= recorded_at)
    return q.order_by(PredictionRecord.created_at.desc()).first()


def _find_retina_record(db, org_id, patient_key, recorded_at):
    if patient_key:
        rec = db.query(PredictionRecord).filter(
            PredictionRecord.org_id == org_id,
            PredictionRecord.modality == "retina",
            PredictionRecord.input_json.contains(patient_key),
        ).order_by(PredictionRecord.created_at.desc()).first()
        if rec:
            return rec
    q = db.query(PredictionRecord).filter(
        PredictionRecord.org_id == org_id,
        PredictionRecord.modality == "retina",
    )
    if recorded_at is not None:
        q = q.filter(PredictionRecord.created_at <= recorded_at)
    return q.order_by(PredictionRecord.created_at.desc()).first()

def main():
    db = SessionLocal()
    rows = []
    try:
        has_link_col = _has_outcome_linked_prediction_id(db)
        if not has_link_col:
            print("Warning: outcomes.linked_prediction_id missing in DB; falling back to patient_key matching.")
        outcomes = _load_outcomes(db, has_link_col)

        for o in outcomes:
            rec = None
            if has_link_col and getattr(o, "linked_prediction_id", None):
                rec = db.query(PredictionRecord).filter(PredictionRecord.id == o.linked_prediction_id).first()
            else:
                org_id = o.org_id if has_link_col else o["org_id"]
                patient_key = o.patient_key if has_link_col else o["patient_key"]
                recorded_at = o.recorded_at if has_link_col else o["recorded_at"]
                rec = _find_tabular_record(db, org_id=org_id, patient_key=patient_key, recorded_at=recorded_at)
            if not rec:
                continue
            # We need matching tabular+retina for same patient_key; MVP: use latest records by patient_key substring.
            # If you already store patient_key separately, replace this logic.
            # Here we use the linked record as "tabular" and look up nearest retina record for same org/patient key.
            p_tab = _extract_t2d_proba(rec)
            if p_tab is None:
                continue

            # Find retina record for same org and patient key (substring)
            patient_key = o.patient_key if has_link_col else o["patient_key"]
            recorded_at = o.recorded_at if has_link_col else o["recorded_at"]
            q = _find_retina_record(
                db,
                org_id=rec.org_id,
                patient_key=patient_key,
                recorded_at=recorded_at,
            )

            p_ret = None
            retina_ok = 0
            if q:
                p_ret = _extract_t2d_proba(q)
                try:
                    r = json.loads(q.output_json or "{}")
                    retina_ok = 1 if (r.get("quality_gate", {}) or {}).get("passed") else 0
                except Exception:
                    retina_ok = 0

            outcome_label = o.outcome_label if has_link_col else o["outcome_label"]
            label = 1 if outcome_label in ["confirmed_t2d"] else 0
            rows.append({"p_tabular": float(p_tab), "p_retina": (float(p_ret) if p_ret is not None else None), "retina_ok": int(retina_ok), "label": int(label)})

        df = pd.DataFrame(rows, columns=COLUMNS)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        df.to_csv(OUT, index=False)
        print("Saved", OUT, "rows:", len(df))
    finally:
        db.close()

if __name__ == "__main__":
    main()
