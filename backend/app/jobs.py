import json
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import ValidationRun, SiteDataset
from app.ml.tabular.serve import get_model
from app.ml.tabular.serve import load_model_card
from app.services.validation_metrics import compute_external_metrics
from app.services.validation_report import render_external_validation_pdf
import pandas as pd
import os

def run_validation_job(run_id: str, dataset_id: str):
    db: Session = SessionLocal()
    try:
        ds = db.query(SiteDataset).filter(SiteDataset.id == dataset_id).first()
        if not ds:
            return
        df = pd.read_csv(ds.file_path)
        card = load_model_card()
        features = card.get("features") or []
        df = df.dropna(subset=["label"])
        X = df[features].copy()
        y = df["label"].astype(int).values

        model, meta = get_model()
        p = model.predict_proba(X)[:, 1]
        metrics = compute_external_metrics(y, p)

        pdf = render_external_validation_pdf(
            title="GlucoLens — External Validation Report (Tabular)",
            dataset_meta={"site_name": ds.site_name, "country_code": ds.country_code, "n_rows": ds.n_rows, "sha256": ds.sha256},
            model_meta={"model_name": meta["model_name"], "model_version": meta["model_version"]},
            metrics=metrics
        )

        report_path = os.path.join("backend", "artifacts", "tabular", f"external_validation_{run_id}.pdf")
        with open(report_path, "wb") as f:
            f.write(pdf)

        run = db.query(ValidationRun).filter(ValidationRun.id == run_id).first()
        if run:
            run.status = "completed"
            run.metrics_json = json.dumps(metrics, sort_keys=True)
            run.report_pdf_path = report_path
            db.commit()
    finally:
        db.close()