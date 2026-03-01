import argparse
import datetime as dt
import json
import uuid

import numpy as np
import pandas as pd

from app.db.session import SessionLocal
from app.db.models import PredictionRecord, Outcome


CLASS_COL_CANDIDATES = ["diabetes_status", "diabetic_status", "label"]


def _uuid() -> str:
    return str(uuid.uuid4())


def _pick_status_column(df: pd.DataFrame) -> str:
    for c in CLASS_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise ValueError(
        f"Could not find target class column. Tried: {CLASS_COL_CANDIDATES}"
    )


def _map_to_status(v) -> str | None:
    s = str(v).strip().lower()
    non_diabetic = {
        "0",
        "no",
        "n",
        "negative",
        "false",
        "normal",
        "healthy",
        "non_diabetic",
        "not_diabetic",
        "non-diabetic",
        "nondiabetic",
    }
    prediabetic = {"prediabetes", "prediabetic", "pre-diabetes", "pre_diabetes", "impaired_glucose_tolerance"}
    diabetic = {
        "1",
        "yes",
        "y",
        "diabetic",
        "diabetes",
        "positive",
        "true",
        "t2d",
        "type2",
        "type_2",
        "type-2",
    }
    if s in non_diabetic:
        return "non_diabetic"
    if s in prediabetic:
        return "prediabetic"
    if s in diabetic:
        return "diabetic"
    return None


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.001, 0.999))


def _sample_probs(status: str, rng: np.random.Generator):
    # Base risk by class; add realistic noise.
    if status == "non_diabetic":
        tab = _clip01(rng.normal(0.08, 0.05))
        ret = _clip01(rng.normal(0.10, 0.07))
        skin = _clip01(rng.normal(0.12, 0.08))
        geno = _clip01(rng.normal(0.16, 0.10))
    elif status == "prediabetic":
        tab = _clip01(rng.normal(0.40, 0.10))
        ret = _clip01(rng.normal(0.44, 0.11))
        skin = _clip01(rng.normal(0.42, 0.12))
        geno = _clip01(rng.normal(0.46, 0.13))
    else:
        tab = _clip01(rng.normal(0.85, 0.07))
        ret = _clip01(rng.normal(0.82, 0.08))
        skin = _clip01(rng.normal(0.78, 0.10))
        geno = _clip01(rng.normal(0.80, 0.10))
    return tab, ret, skin, geno


def _quality_flag(status: str, modality: str, rng: np.random.Generator) -> int:
    # Slightly lower quality for sick cases to simulate real acquisition challenges.
    base = 0.95
    if status == "diabetic":
        base = 0.90
    if modality == "genomics":
        base -= 0.02
    if modality in {"retina", "skin"}:
        base -= 0.01
    return int(rng.random() < base)


def _make_pred_record(
    *,
    patient_key: str,
    modality: str,
    org_id: str,
    facility_id: str,
    country_code: str,
    model_version: str,
    t2d_prob: float,
    quality_passed: int,
    source_row: dict,
) -> PredictionRecord:
    if modality == "tabular":
        probs = {
            "non_diabetic": _clip01(1.0 - t2d_prob),
            "prediabetic": _clip01(max(0.05, min(0.35, 0.5 - abs(t2d_prob - 0.5)))),
            "diabetic": t2d_prob,
            "t2d": t2d_prob,
        }
        # Normalize 3-class probabilities.
        s3 = probs["non_diabetic"] + probs["prediabetic"] + probs["diabetic"]
        probs["non_diabetic"] /= s3
        probs["prediabetic"] /= s3
        probs["diabetic"] /= s3
        probs["t2d"] = probs["diabetic"]
        out = {
            "predicted_label": max(
                ["non_diabetic", "prediabetic", "diabetic"],
                key=lambda k: probs[k],
            ),
            "probabilities": probs,
            "quality_gate": {"passed": True},
        }
    elif modality == "retina":
        out = {
            "predicted_label": "positive" if t2d_prob >= 0.5 else "negative",
            "probabilities": {"negative": _clip01(1.0 - t2d_prob), "positive": t2d_prob, "t2d": t2d_prob},
            "quality_gate": {"passed": bool(quality_passed)},
        }
        probs = out["probabilities"]
    elif modality == "skin":
        out = {
            "predicted_label": "positive" if t2d_prob >= 0.5 else "negative",
            "probabilities": {"negative": _clip01(1.0 - t2d_prob), "positive": t2d_prob},
            "quality_gate": {"passed": bool(quality_passed)},
        }
        probs = out["probabilities"]
    else:  # genomics
        out = {
            "predicted_label": "screen_positive_refer" if t2d_prob >= 0.5 else "screen_negative",
            "probability": t2d_prob,
            "quality_gate": {"passed": bool(quality_passed)},
        }
        probs = {"t2d": t2d_prob}

    in_payload = {
        "patient_key": patient_key,
        "source": "dev_synth_linked_outcomes",
        "features": {k: source_row.get(k) for k in ("age", "sex", "bmi", "waist_circumference")},
    }

    return PredictionRecord(
        id=_uuid(),
        created_at=dt.datetime.utcnow(),
        actor_user_id=None,
        org_id=org_id,
        facility_id=facility_id,
        country_code=country_code,
        modality=modality,
        model_name=f"dev_synth_{modality}",
        model_version=model_version,
        consent_version="dev",
        consent_json=json.dumps({"dev_only": True}, sort_keys=True),
        input_json=json.dumps(in_payload, sort_keys=True),
        output_json=json.dumps(out, sort_keys=True),
        predicted_label=str(out.get("predicted_label", "")),
        proba_json=json.dumps(probs, sort_keys=True),
    )


def _clear_previous(db):
    deleted_outcomes = (
        db.query(Outcome)
        .filter(Outcome.notes.like("DEV_SYNTH_LINKED_OUTCOME%"))
        .delete(synchronize_session=False)
    )
    deleted_preds = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.model_name.like("dev_synth_%"))
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted_preds), int(deleted_outcomes)


def main():
    ap = argparse.ArgumentParser(description="Generate development linked outcomes for fusion training.")
    ap.add_argument(
        "--csv",
        default="data/anthropometric_data/train_tabular.csv",
        help="Path to prepared tabular training CSV.",
    )
    ap.add_argument("--max-rows", type=int, default=3000, help="Max patient rows to synthesize.")
    ap.add_argument("--seed", type=int, default=42, help="Random seed.")
    ap.add_argument("--org-id", default="dev_org_1")
    ap.add_argument("--facility-id", default="dev_facility_1")
    ap.add_argument("--country-code", default="NG")
    ap.add_argument("--clear-previous", action="store_true", help="Delete previously generated synthetic rows.")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    status_col = _pick_status_column(df)
    mapped = df[status_col].map(_map_to_status)
    df = df.loc[mapped.notna()].copy()
    df["__status__"] = mapped[mapped.notna()]
    if df.empty:
        raise SystemExit("No valid status labels found in source CSV.")

    # Balanced sample by class for robust fusion training.
    rng = np.random.default_rng(args.seed)
    classes = ["non_diabetic", "prediabetic", "diabetic"]
    n_per_class = max(1, args.max_rows // len(classes))
    sampled = []
    for c in classes:
        part = df[df["__status__"] == c]
        if part.empty:
            continue
        take = min(n_per_class, len(part))
        sampled.append(part.sample(n=take, random_state=args.seed))
    work = pd.concat(sampled, ignore_index=True)
    if len(work) < args.max_rows and len(df) > len(work):
        needed = min(args.max_rows - len(work), len(df) - len(work))
        extra = df.drop(work.index, errors="ignore").sample(n=needed, random_state=args.seed)
        work = pd.concat([work, extra], ignore_index=True)

    model_version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db = SessionLocal()
    try:
        if args.clear_previous:
            d_pred, d_out = _clear_previous(db)
            print(f"Cleared previous synthetic rows: prediction_records={d_pred}, outcomes={d_out}")

        n_rows = 0
        class_counts = {"non_diabetic": 0, "prediabetic": 0, "diabetic": 0}

        for i, row in work.reset_index(drop=True).iterrows():
            status = row["__status__"]
            class_counts[status] += 1
            patient_key = f"devpk_{model_version}_{i:06d}"
            tab, ret, skin, geno = _sample_probs(status, rng)

            rec_tab = _make_pred_record(
                patient_key=patient_key,
                modality="tabular",
                org_id=args.org_id,
                facility_id=args.facility_id,
                country_code=args.country_code,
                model_version=model_version,
                t2d_prob=tab,
                quality_passed=1,
                source_row=row.to_dict(),
            )
            rec_ret = _make_pred_record(
                patient_key=patient_key,
                modality="retina",
                org_id=args.org_id,
                facility_id=args.facility_id,
                country_code=args.country_code,
                model_version=model_version,
                t2d_prob=ret,
                quality_passed=_quality_flag(status, "retina", rng),
                source_row=row.to_dict(),
            )
            rec_skin = _make_pred_record(
                patient_key=patient_key,
                modality="skin",
                org_id=args.org_id,
                facility_id=args.facility_id,
                country_code=args.country_code,
                model_version=model_version,
                t2d_prob=skin,
                quality_passed=_quality_flag(status, "skin", rng),
                source_row=row.to_dict(),
            )
            rec_geno = _make_pred_record(
                patient_key=patient_key,
                modality="genomics",
                org_id=args.org_id,
                facility_id=args.facility_id,
                country_code=args.country_code,
                model_version=model_version,
                t2d_prob=geno,
                quality_passed=_quality_flag(status, "genomics", rng),
                source_row=row.to_dict(),
            )

            db.add(rec_tab)
            db.add(rec_ret)
            db.add(rec_skin)
            db.add(rec_geno)

            outcome_label = "confirmed_t2d" if status == "diabetic" else "not_t2d"
            out = Outcome(
                id=_uuid(),
                referral_id=None,
                org_id=args.org_id,
                facility_id=args.facility_id,
                patient_key=patient_key,
                outcome_label=outcome_label,
                notes=f"DEV_SYNTH_LINKED_OUTCOME status={status}",
                recorded_at=dt.datetime.utcnow(),
                linked_prediction_id=rec_tab.id,
            )
            db.add(out)
            n_rows += 1

            if n_rows % 500 == 0:
                db.commit()

        db.commit()
        print("Generated synthetic linked rows.")
        print(f"Patients: {n_rows}")
        print(f"Class counts: {class_counts}")
        print("Created 4 prediction_records per patient (tabular/retina/skin/genomics) + 1 outcome.")
        print("Next: python -m app.ml.fusion.export_fusion_train")
        print("Then: python -m app.ml.fusion.train_fusion")
    finally:
        db.close()


if __name__ == "__main__":
    main()
