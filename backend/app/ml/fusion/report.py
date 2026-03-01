import io, base64
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

def render_fusion_report_pdf(out: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 2*cm

    fused = out.get("fusion", {})
    tab = out.get("tabular", {})
    ret = out.get("retina", {})
    skin = out.get("skin", {})
    genomics = out.get("genomics", {})

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, y, "GlucoLens — Fusion Screening Report (Tabular + Retina + Skin + Genomics)")
    y -= 0.8*cm

    c.setFont("Helvetica", 10)
    c.drawString(2*cm, y, "Disclaimer: This is screening support only. Please confirm with labs/clinical evaluation.")
    y -= 1.0*cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Fusion Decision")
    y -= 0.6*cm
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, y, f"Final label: {fused.get('final_label')}")
    y -= 0.5*cm
    c.drawString(2*cm, y, f"Fusion probability: {fused.get('final_proba')}")
    y -= 0.5*cm
    c.drawString(2*cm, y, f"Reason: {fused.get('reason')}")
    y -= 0.8*cm

    # Tabular summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Tabular")
    y -= 0.6*cm
    probs = tab.get("probabilities", {})
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, y, f"P(T2D): {probs.get('t2d'):.3f}")
    y -= 0.45*cm

    # SHAP top features
    top = (tab.get("explainability") or {}).get("top_features") or []
    c.drawString(2*cm, y, "Top SHAP features:")
    y -= 0.45*cm
    for t in top[:8]:
        if y < 3*cm:
            c.showPage(); y = h - 2*cm; c.setFont("Helvetica", 10)
        c.drawString(2*cm, y, f"- {t.get('feature')}: shap={t.get('shap_value'):.4f} val={t.get('value')}")
        y -= 0.4*cm

    y -= 0.3*cm

    # Retina section
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Retina (if provided)")
    y -= 0.6*cm
    c.setFont("Helvetica", 10)

    if not ret:
        c.drawString(2*cm, y, "No retina image provided.")
        y -= 0.45*cm
    else:
        qp = (ret.get("quality_gate") or {}).get("passed")
        c.drawString(2*cm, y, f"Quality gate passed: {qp}")
        y -= 0.45*cm

        rprobs = ret.get("probabilities", {})
        if rprobs.get("t2d") is not None:
            c.drawString(2*cm, y, f"P(retina proxy positive): {float(rprobs.get('t2d')):.3f}")
            y -= 0.45*cm

        overlay_b64 = (ret.get("explainability") or {}).get("overlay_png_base64")
        if overlay_b64:
            img_bytes = base64.b64decode(overlay_b64.encode("utf-8"))
            img = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(img, 2*cm, y-10*cm, width=14*cm, height=10*cm, preserveAspectRatio=True, mask="auto")
            y -= 10.5*cm

    # Skin section
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Skin (if provided)")
    y -= 0.6*cm
    c.setFont("Helvetica", 10)

    if not skin:
        c.drawString(2*cm, y, "No skin image provided.")
        y -= 0.45*cm
    else:
        qp = (skin.get("quality_gate") or {}).get("passed")
        c.drawString(2*cm, y, f"Quality gate passed: {qp}")
        y -= 0.45*cm

        sprobs = skin.get("probabilities", {})
        if sprobs.get("positive") is not None:
            c.drawString(2*cm, y, f"P(skin proxy positive): {float(sprobs.get('positive')):.3f}")
            y -= 0.45*cm

        overlay_b64 = (skin.get("explainability") or {}).get("overlay_png_base64")
        if overlay_b64:
            img_bytes = base64.b64decode(overlay_b64.encode("utf-8"))
            img = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(img, 2*cm, y-10*cm, width=14*cm, height=10*cm, preserveAspectRatio=True, mask="auto")
            y -= 10.5*cm

    # Genomics section
    if y < 5*cm:
        c.showPage()
        y = h - 2*cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Genomics (if provided)")
    y -= 0.6*cm
    c.setFont("Helvetica", 10)

    if not genomics:
        c.drawString(2*cm, y, "No genomics data provided.")
        y -= 0.45*cm
    else:
        if genomics.get("predicted_label") is not None:
            c.drawString(2*cm, y, f"Predicted label: {genomics.get('predicted_label')}")
            y -= 0.45*cm
        if genomics.get("probability") is not None:
            c.drawString(2*cm, y, f"P(genomics positive): {float(genomics.get('probability')):.3f}")
            y -= 0.45*cm

        topc = (genomics.get("explainability") or {}).get("top_coefficients") or []
        if topc:
            c.drawString(2*cm, y, "Top coefficients:")
            y -= 0.45*cm
            for t in topc[:8]:
                if y < 3*cm:
                    c.showPage(); y = h - 2*cm; c.setFont("Helvetica", 10)
                c.drawString(2*cm, y, f"- {t.get('feature')}: coef={float(t.get('coefficient', 0.0)):.4f} ({t.get('direction')})")
                y -= 0.4*cm

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(2*cm, 2*cm, "Generated by GlucoLens • Fusion uses calibrated probabilities + conservative abstain policy.")
    c.showPage()
    c.save()
    return buf.getvalue()
