import datetime as dt
from typing import Any


def _to_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _normalize_sex(value: Any) -> str | None:
    s = str(value or "").strip().upper()
    if s in {"M", "MALE"}:
        return "M"
    if s in {"F", "FEMALE"}:
        return "F"
    return None


def _coalesce_str(value: Any) -> str | None:
    s = str(value or "").strip()
    return s or None


def _derive_bmi_category(bmi: float | None) -> str | None:
    if bmi is None:
        return None
    if bmi < 18.5:
        return "underweight"
    if bmi < 25:
        return "normal"
    if bmi < 30:
        return "overweight"
    return "obese"


def _derive_central_obesity(waist: float | None, sex: str | None) -> str | None:
    if waist is None:
        return None
    if sex == "M":
        return "yes" if waist >= 102 else "no"
    if sex == "F":
        return "yes" if waist >= 88 else "no"
    if waist >= 102:
        return "yes"
    return "no"


def _derive_hypertension_status(sbp: float | None, dbp: float | None) -> str | None:
    if sbp is None and dbp is None:
        return None
    if (sbp is not None and sbp >= 140) or (dbp is not None and dbp >= 90):
        return "yes"
    return "no"


def _derive_cvd_risk_category(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 10:
        return "low"
    if value < 20:
        return "moderate"
    return "high"


def derive_tabular_features(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload or {})

    age = _to_float(enriched.get("age"))
    bmi = _to_float(enriched.get("bmi"))
    waist = _to_float(enriched.get("waist_circumference"))
    sbp = _to_float(enriched.get("systolic_bp"))
    dbp = _to_float(enriched.get("diastolic_bp"))
    sex = _normalize_sex(enriched.get("sex"))
    cvd_risk = _to_float(enriched.get("cvd_risk_10yr_pct"))

    if enriched.get("sex") in (None, "") and sex is not None:
        enriched["sex"] = sex

    if enriched.get("pulse_pressure") in (None, "", "nan") and sbp is not None and dbp is not None:
        enriched["pulse_pressure"] = sbp - dbp

    if not _coalesce_str(enriched.get("bmi_category")):
        bmi_category = _derive_bmi_category(bmi)
        if bmi_category is not None:
            enriched["bmi_category"] = bmi_category

    if not _coalesce_str(enriched.get("central_obesity")):
        central_obesity = _derive_central_obesity(waist, sex)
        if central_obesity is not None:
            enriched["central_obesity"] = central_obesity

    if not _coalesce_str(enriched.get("hypertension_status")):
        hypertension = _derive_hypertension_status(sbp, dbp)
        if hypertension is not None:
            enriched["hypertension_status"] = hypertension

    if not _coalesce_str(enriched.get("cvd_risk_category")):
        cvd_category = _derive_cvd_risk_category(cvd_risk)
        if cvd_category is not None:
            enriched["cvd_risk_category"] = cvd_category

    if age is not None and enriched.get("Age") in (None, ""):
        enriched["Age"] = age
    if bmi is not None and enriched.get("BMI") in (None, ""):
        enriched["BMI"] = bmi
    if enriched.get("HbA1c") in (None, "") and enriched.get("hba1c_pct") not in (None, ""):
        enriched["HbA1c"] = enriched.get("hba1c_pct")

    return enriched


def build_screening_plan(
    *,
    fusion: dict[str, Any] | None,
    tabular: dict[str, Any] | None = None,
    threshold: float = 0.5,
    as_of: dt.date | None = None,
) -> dict[str, Any]:
    today = as_of or dt.date.today()
    fusion = fusion or {}
    tabular = tabular or {}
    final_label = str(fusion.get("final_label") or "")
    reason = str(fusion.get("reason") or "")
    final_proba = _to_float(fusion.get("final_proba"))
    tab_label = str(tabular.get("predicted_label") or "").lower()

    recommended_window = 12
    track = "routine"
    summary = "Routine annual screening is appropriate if there are no new symptoms or interim clinical concerns."

    if final_label in {"retake_image", "insufficient_data"}:
        recommended_window = 3
        track = "repeat_capture"
        summary = (
            "Repeat data capture now before relying on a longitudinal screening interval. "
            "Use the 3-month window as the next checkpoint if repeat capture cannot be completed immediately."
        )
    elif final_label == "screen_positive_refer":
        recommended_window = 3
        track = "intensive"
        summary = (
            "High-risk screening result. Retain the patient in the 3-month follow-up track after referral and confirmatory testing."
        )
    elif (final_proba is not None and abs(final_proba - float(threshold)) <= 0.05) or tab_label == "prediabetic":
        recommended_window = 6
        track = "enhanced"
        summary = (
            "Intermediate-risk screening result. A 6-month rescreening interval is more appropriate than routine annual follow-up."
        )

    timelines = []
    for months in (3, 6, 12):
        due_date = today + dt.timedelta(days=months * 30)
        if final_label in {"retake_image", "insufficient_data"}:
            status = "repeat_now" if months == 3 else "pending_complete_dataset"
        elif months == recommended_window:
            status = "recommended"
        elif months < recommended_window:
            status = "not_primary_window"
        else:
            status = "surveillance"

        if months == 3:
            note = (
                "Referral review / repeat capture window."
                if recommended_window == 3
                else "Reserve for earlier review if symptoms emerge or clinician concern increases."
            )
        elif months == 6:
            note = (
                "Enhanced screening checkpoint."
                if recommended_window == 6
                else "Escalate to this window when lifestyle risk remains elevated."
            )
        else:
            note = "Routine annual screening checkpoint."

        timelines.append(
            {
                "window_months": months,
                "due_date": due_date.isoformat(),
                "status": status,
                "note": note,
            }
        )

    return {
        "program": "diabetes_screening",
        "recommended_window_months": recommended_window,
        "track": track,
        "summary": summary,
        "timelines": timelines,
        "generated_on": today.isoformat(),
    }
