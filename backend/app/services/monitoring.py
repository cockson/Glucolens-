import json
import numpy as np
from sqlalchemy.orm import Session
from sklearn.metrics import roc_auc_score, brier_score_loss

def _safe_json(s):
    try: return json.loads(s)
    except: return None

def _binary_label(outcome_label: str) -> int:
    return 1 if outcome_label in ["confirmed_t2d"] else 0

def _extract_tabular_prob(rec) -> float | None:
    out = _safe_json(rec.output_json) or {}
    probs = out.get("probabilities") or {}
    pt2d = probs.get("t2d")
    if pt2d is None:
        # Fallback for records that only persisted proba_json.
        pjson = _safe_json(rec.proba_json) or {}
        pt2d = pjson.get("t2d")
    if pt2d is None:
        return None
    try:
        return float(pt2d)
    except Exception:
        return None

def _extract_fusion_prob(rec) -> float | None:
    out = _safe_json(rec.output_json) or {}
    fp = (out.get("fusion") or {}).get("final_proba")
    if fp is None:
        pjson = _safe_json(rec.proba_json) or {}
        fp = pjson.get("fusion")
    if fp is None:
        return None
    try:
        return float(fp)
    except Exception:
        return None

def _metric_pack(y_list, p_list):
    if not y_list or not p_list or len(y_list) != len(p_list):
        return {
            "n": 0,
            "auroc": None,
            "brier": None,
            "calibration_buckets": [],
        }
    y = np.asarray(y_list, dtype=int)
    p = np.asarray(p_list, dtype=float)

    if len(np.unique(y)) < 2:
        auroc = None
    else:
        auroc = float(roc_auc_score(y, p))
    brier = float(brier_score_loss(y, p))

    bins = np.linspace(0, 1, 11)
    bucket = []
    for i in range(10):
        lo, hi = bins[i], bins[i+1]
        mask = (p >= lo) & (p < hi) if i < 9 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        bucket.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "n": int(mask.sum()),
            "avg_pred": float(p[mask].mean()),
            "obs_rate": float(y[mask].mean())
        })
    return {
        "n": int(len(y)),
        "auroc": auroc,
        "brier": brier,
        "calibration_buckets": bucket,
    }

def compute_outcome_monitoring(db: Session, org_id: str, days: int = 30):
    """
    Calculates observed outcome rates vs predicted risk for linked outcomes.
    Reports both tabular and fusion performance when available.
    """
    from datetime import datetime, timedelta
    from app.db.models import Outcome, PredictionRecord

    since = datetime.utcnow() - timedelta(days=days)

    outcomes_all = db.query(Outcome).filter(
        Outcome.org_id == org_id,
        Outcome.recorded_at >= since,
    ).all()

    outcomes_linked = db.query(Outcome).filter(
        Outcome.org_id == org_id,
        Outcome.recorded_at >= since,
        Outcome.linked_prediction_id.isnot(None)
    ).all()

    n_total = len(outcomes_all)
    n_linked = len(outcomes_linked)
    if n_total == 0:
        return {
            "n": 0,
            "days": days,
            "message": "No outcomes in window",
            "coverage": {
                "total_outcomes_in_window": 0,
                "linked_outcomes": 0,
                "linkage_rate": 0.0,
                "linked_prediction_modalities": {},
            },
            "tabular": {"n": 0, "auroc": None, "brier": None, "calibration_buckets": []},
            "fusion": {"n": 0, "auroc": None, "brier": None, "calibration_buckets": []},
        }

    linked_modalities = {}
    y_tab, p_tab = [], []
    y_fusion, p_fusion = [], []

    for o in outcomes_linked:
        rec = db.query(PredictionRecord).filter(PredictionRecord.id == o.linked_prediction_id).first()
        if not rec:
            continue

        linked_modalities[rec.modality] = int(linked_modalities.get(rec.modality, 0)) + 1
        label = _binary_label(o.outcome_label)

        # Tabular metric input:
        # - if linked record is tabular, use it directly
        # - if linked record is fusion, use embedded tabular probability when present
        if rec.modality == "tabular":
            pt = _extract_tabular_prob(rec)
            if pt is not None:
                y_tab.append(label)
                p_tab.append(pt)
        elif rec.modality == "fusion":
            out = _safe_json(rec.output_json) or {}
            pt = ((out.get("tabular") or {}).get("probabilities") or {}).get("t2d")
            try:
                if pt is not None:
                    y_tab.append(label)
                    p_tab.append(float(pt))
            except Exception:
                pass

        # Fusion metric input:
        # - if linked record is fusion, use final_proba
        # - if linked record is tabular, try to find nearest fusion record for same patient
        if rec.modality == "fusion":
            pf = _extract_fusion_prob(rec)
            if pf is not None:
                y_fusion.append(label)
                p_fusion.append(pf)
        elif rec.modality == "tabular":
            q = db.query(PredictionRecord).filter(
                PredictionRecord.org_id == o.org_id,
                PredictionRecord.modality == "fusion",
                PredictionRecord.input_json.contains(o.patient_key),
                PredictionRecord.created_at <= o.recorded_at,
            ).order_by(PredictionRecord.created_at.desc()).first()
            if q:
                pf = _extract_fusion_prob(q)
                if pf is not None:
                    y_fusion.append(label)
                    p_fusion.append(pf)

    tab = _metric_pack(y_tab, p_tab)
    fusion = _metric_pack(y_fusion, p_fusion)

    # Backward-compatible top-level keys map to tabular metrics.
    return {
        "n": int(tab["n"]),
        "days": days,
        "auroc": tab["auroc"],
        "brier": tab["brier"],
        "calibration_buckets": tab["calibration_buckets"],
        "coverage": {
            "total_outcomes_in_window": int(n_total),
            "linked_outcomes": int(n_linked),
            "linkage_rate": float(n_linked / n_total) if n_total else 0.0,
            "linked_prediction_modalities": linked_modalities,
        },
        "tabular": tab,
        "fusion": fusion,
    }
