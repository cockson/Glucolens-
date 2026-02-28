import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


def render_genomics_report_pdf(prediction: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 2 * cm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "GlucoLens - Genomics Screening Report")
    y -= 0.8 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, "Screening support only. Confirm with labs/clinical evaluation.")
    y -= 1.0 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Prediction")
    y -= 0.6 * cm

    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, y, f"Label: {prediction.get('predicted_label')}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"P(positive): {float(prediction.get('probability', 0.0)):.3f}")
    y -= 0.8 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Top Coefficients")
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)

    top = (prediction.get("explainability") or {}).get("top_coefficients") or []
    if not top:
        c.drawString(2 * cm, y, "No coefficient summary available.")
    else:
        for t in top[:12]:
            if y < 3 * cm:
                c.showPage()
                y = h - 2 * cm
                c.setFont("Helvetica", 10)
            c.drawString(
                2 * cm,
                y,
                f"- {t.get('feature')}: coef={float(t.get('coefficient', 0.0)):.4f} ({t.get('direction')})",
            )
            y -= 0.45 * cm

    c.showPage()
    c.save()
    return buf.getvalue()
