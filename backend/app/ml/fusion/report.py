import base64
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _fmt_prob(v):
    try:
        if v is None:
            return "N/A"
        return f"{float(v):.3f}"
    except Exception:
        return "N/A"


def _fmt_value(v):
    if v is None:
        return "N/A"
    s = str(v).strip()
    return s if s else "N/A"


def _fmt_sex(v):
    s = str(v or "").strip().upper()
    if s == "M":
        return "Male"
    if s == "F":
        return "Female"
    return _fmt_value(v)


def _fmt_yes_no(v):
    s = str(v or "").strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return "Yes"
    if s in {"0", "false", "no", "n"}:
        return "No"
    return _fmt_value(v)


def _line(c, text, x, y, font="Helvetica", size=10):
    c.setFont(font, size)
    c.drawString(x, y, text)
    return y - 0.45 * cm


def _new_page(c, h):
    c.showPage()
    return h - 2.2 * cm


def _ensure_space(c, y, needed, h):
    if y < needed:
        return _new_page(c, h)
    return y


def _draw_brand_header(c, w, h):
    y = h - 2.0 * cm
    cx = 2.6 * cm
    cy = y - 0.2 * cm

    # Minimal logo mark (lens style) to avoid external asset dependency.
    c.setStrokeColorRGB(0.1, 0.45, 0.75)
    c.setLineWidth(1.8)
    c.circle(cx, cy, 0.48 * cm, stroke=1, fill=0)
    c.line(cx + 0.35 * cm, cy - 0.35 * cm, cx + 0.85 * cm, cy - 0.85 * cm)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(3.6 * cm, y, "GlucoLens")
    c.setFont("Helvetica", 9)
    c.drawString(3.6 * cm, y - 0.45 * cm, "AI Screening Support Platform")

    c.setLineWidth(0.7)
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.line(2 * cm, y - 0.8 * cm, w - 2 * cm, y - 0.8 * cm)
    return y - 1.35 * cm


def render_fusion_report_pdf(out: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    fused = out.get("fusion", {}) or {}
    tab = out.get("tabular", {}) or {}
    tab_inputs = out.get("tabular_inputs", {}) or {}
    genomics = out.get("genomics", {}) or {}
    ret = out.get("retina", {}) or {}
    skin = out.get("skin", {}) or {}

    y = _draw_brand_header(c, w, h)
    # Double line break after logo block.
    y -= 0.9 * cm
    y = _line(c, "Fusion Screening Clinical Report", 2 * cm, y, "Helvetica-Bold", 14)
    y = _line(
        c,
        "Screening support only. Confirm with clinical evaluation and laboratory diagnostics.",
        2 * cm,
        y,
        "Helvetica",
        9,
    )
    y -= 0.15 * cm

    # Fusion Decision Summary
    y = _line(c, "Fusion Decision Summary", 2 * cm, y, "Helvetica-Bold", 12)
    y = _line(c, f"Final label: {fused.get('final_label', 'N/A')}", 2 * cm, y)
    y = _line(c, f"Fusion probability: {_fmt_prob(fused.get('final_proba'))}", 2 * cm, y)
    y = _line(c, f"Decision reason: {fused.get('reason', 'N/A')}", 2 * cm, y)
    y -= 0.6 * cm

    screening_plan = out.get("screening_plan") or {}
    if screening_plan:
        y = _ensure_space(c, y, 5.5 * cm, h)
        y = _line(c, "Screening Program Plan", 2 * cm, y, "Helvetica-Bold", 12)
        y = _line(c, f"Recommended window: {_fmt_value(screening_plan.get('recommended_window_months'))} months", 2 * cm, y)
        y = _line(c, f"Track: {_fmt_value(screening_plan.get('track'))}", 2 * cm, y)
        y = _line(c, f"Summary: {_fmt_value(screening_plan.get('summary'))}", 2 * cm, y)
        for item in screening_plan.get("timelines", [])[:3]:
            y = _line(
                c,
                f"- {item.get('window_months', 'N/A')} months ({_fmt_value(item.get('due_date'))}): {_fmt_value(item.get('status'))}",
                2.4 * cm,
                y,
                "Helvetica",
                9,
            )
        y -= 0.6 * cm

    # 1) Tabular
    y = _ensure_space(c, y, 5.5 * cm, h)
    y = _line(c, "1. Tabular Mode", 2 * cm, y, "Helvetica-Bold", 12)
    y = _line(c, f"Model: {tab.get('model_name', 'N/A')} ({tab.get('model_version', 'N/A')})", 2 * cm, y)
    y = _line(c, f"Predicted label: {tab.get('predicted_label', 'N/A')}", 2 * cm, y)
    probs = tab.get("probabilities", {}) or {}
    y = _line(c, f"P(T2D): {_fmt_prob(probs.get('t2d'))}", 2 * cm, y)
    y = _line(c, f"P(non_diabetic): {_fmt_prob(probs.get('non_diabetic'))}", 2 * cm, y)
    y = _line(c, f"P(prediabetic): {_fmt_prob(probs.get('prediabetic'))}", 2 * cm, y)
    y = _line(c, f"P(diabetic): {_fmt_prob(probs.get('diabetic'))}", 2 * cm, y)

    y = _line(c, "Tabular input features:", 2 * cm, y, "Helvetica-Bold", 10)
    tab_rows = [
        ("Age", _fmt_value(tab_inputs.get("age"))),
        ("Sex", _fmt_sex(tab_inputs.get("sex"))),
        ("BMI", _fmt_value(tab_inputs.get("bmi"))),
        ("BMI category", _fmt_value(tab_inputs.get("bmi_category"))),
        ("Waist Circumference (cm)", _fmt_value(tab_inputs.get("waist_circumference"))),
        ("Family history of diabetes", _fmt_yes_no(tab_inputs.get("family_history_diabetes"))),
        ("Systolic BP (mmHg)", _fmt_value(tab_inputs.get("systolic_bp"))),
        ("Diastolic BP (mmHg)", _fmt_value(tab_inputs.get("diastolic_bp"))),
        ("Fasting glucose (mg/dL)", _fmt_value(tab_inputs.get("fasting_glucose_mgdl"))),
        ("HbA1c (%)", _fmt_value(tab_inputs.get("hba1c_pct"))),
        ("Physical activity", _fmt_value(tab_inputs.get("physical_activity"))),
        ("Smoking status", _fmt_value(tab_inputs.get("smoking_status"))),
    ]
    for label, value in tab_rows:
        y = _ensure_space(c, y, 3.2 * cm, h)
        y = _line(c, f"- {label}: {value}", 2.4 * cm, y, "Helvetica", 9)

    top = (tab.get("explainability") or {}).get("top_features") or []
    if top:
        y = _line(c, "Top contributing factors:", 2 * cm, y)
        for t in top[:8]:
            y = _ensure_space(c, y, 3.2 * cm, h)
            feat = t.get("feature", "N/A")
            sval = _fmt_prob(t.get("shap_value"))
            val = t.get("value", "N/A")
            y = _line(c, f"- {feat}: impact={sval}, value={val}", 2.4 * cm, y, "Helvetica", 9)
    y -= 0.6 * cm

    # 2) Genomics
    y = _ensure_space(c, y, 5.8 * cm, h)
    y = _line(c, "2. Genomics Mode", 2 * cm, y, "Helvetica-Bold", 12)
    if not genomics:
        y = _line(c, "No genomics data provided.", 2 * cm, y)
    elif genomics.get("error"):
        y = _line(c, f"Genomics status: {genomics.get('error')}", 2 * cm, y)
    else:
        y = _line(c, f"Predicted label: {genomics.get('predicted_label', 'N/A')}", 2 * cm, y)
        y = _line(c, f"P(positive): {_fmt_prob(genomics.get('probability'))}", 2 * cm, y)
        topc = (genomics.get("explainability") or {}).get("top_coefficients") or []
        if topc:
            y = _line(c, "Top coefficients:", 2 * cm, y)
            for t in topc[:8]:
                y = _ensure_space(c, y, 3.2 * cm, h)
                y = _line(
                    c,
                    f"- {t.get('feature', 'N/A')}: coef={_fmt_prob(t.get('coefficient'))} ({t.get('direction', 'N/A')})",
                    2.4 * cm,
                    y,
                    "Helvetica",
                    9,
                )
    y -= 0.6 * cm

    # 3) Retina
    y = _ensure_space(c, y, 7.5 * cm, h)
    y = _line(c, "3. Retina Mode", 2 * cm, y, "Helvetica-Bold", 12)
    if not ret:
        y = _line(c, "No retina image provided.", 2 * cm, y)
    else:
        y = _line(c, f"Predicted label: {ret.get('predicted_label', 'N/A')}", 2 * cm, y)
        q = ret.get("quality_gate") or {}
        y = _line(c, f"Quality gate: {'passed' if q.get('passed') else 'failed'} ({q.get('reason', 'N/A')})", 2 * cm, y)
        rprobs = ret.get("probabilities", {}) or {}
        y = _line(c, f"P(retina positive proxy): {_fmt_prob(rprobs.get('t2d'))}", 2 * cm, y)

        overlay_b64 = (ret.get("explainability") or {}).get("overlay_png_base64")
        if overlay_b64:
            y = _ensure_space(c, y, 11.5 * cm, h)
            try:
                img_bytes = base64.b64decode(overlay_b64.encode("utf-8"))
                img = ImageReader(io.BytesIO(img_bytes))
                c.drawImage(img, 2 * cm, y - 8.8 * cm, width=12 * cm, height=8.8 * cm, preserveAspectRatio=True, mask="auto")
                y -= 9.2 * cm
            except Exception:
                y = _line(c, "Retina overlay image could not be rendered.", 2 * cm, y)
    y -= 0.6 * cm

    # 4) Skin
    y = _ensure_space(c, y, 7.5 * cm, h)
    y = _line(c, "4. Skin Mode", 2 * cm, y, "Helvetica-Bold", 12)
    if not skin:
        y = _line(c, "No skin image provided.", 2 * cm, y)
    else:
        y = _line(c, f"Predicted label: {skin.get('predicted_label', 'N/A')}", 2 * cm, y)
        q = skin.get("quality_gate") or {}
        y = _line(c, f"Quality gate: {'passed' if q.get('passed') else 'failed'} ({q.get('reason', 'N/A')})", 2 * cm, y)
        sprobs = skin.get("probabilities", {}) or {}
        y = _line(c, f"P(skin positive proxy): {_fmt_prob(sprobs.get('positive'))}", 2 * cm, y)

        overlay_b64 = (skin.get("explainability") or {}).get("overlay_png_base64")
        if overlay_b64:
            y = _ensure_space(c, y, 11.5 * cm, h)
            try:
                img_bytes = base64.b64decode(overlay_b64.encode("utf-8"))
                img = ImageReader(io.BytesIO(img_bytes))
                c.drawImage(img, 2 * cm, y - 8.8 * cm, width=12 * cm, height=8.8 * cm, preserveAspectRatio=True, mask="auto")
                y -= 9.2 * cm
            except Exception:
                y = _line(c, "Skin overlay image could not be rendered.", 2 * cm, y)

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(2 * cm, 1.8 * cm, "Generated by GlucoLens. Keep prediction records and audit logs for governance.")
    c.save()
    return buf.getvalue()
