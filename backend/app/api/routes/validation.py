import os, uuid, json, hashlib
import redis
import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Role, SiteDataset, ValidationRun
from app.api.deps import get_current_user, require_role
from app.api.deps_billing import require_active_subscription
from app.jobs import run_validation_job
from app.core.config import settings

from app.ml.tabular.serve import get_model, load_model_card

router = APIRouter()

UPLOAD_DIR = os.path.join("backend", "data", "site_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _uuid():
    return str(uuid.uuid4())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_deidentified(df: pd.DataFrame):
    # Hard block obvious PHI columns (extend as needed)
    banned = {"name", "fullname", "phone", "email", "address", "dob", "national_id", "nin"}
    lower = {c.lower() for c in df.columns}
    hit = banned.intersection(lower)
    if hit:
        raise HTTPException(status_code=400, detail=f"Dataset contains potentially identifying columns: {sorted(list(hit))}")


@router.get("/template/tabular.csv")
def download_tabular_template(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "public":
        require_active_subscription(user=user, db=db)
    card = load_model_card()
    features = card.get("features") or []
    # Expected label column for external validation
    cols = features + ["label"]
    csv = ",".join(cols) + "\n"
    return StreamingResponse(
        iter([csv.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tabular_external_validation_template.csv"'},
    )


@router.post("/datasets/upload")
def upload_site_dataset(
    site_name: str = Form(...),
    description: str = Form(""),
    country_code: str = Form(""),
    facility_id: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.super_admin, Role.org_admin)),
):
    # super_admin only (regulated pattern)
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV supported")

    dataset_id = _uuid()
    path = os.path.join(UPLOAD_DIR, f"{dataset_id}.csv")

    # Save
    with open(path, "wb") as f:
        f.write(file.file.read())

    digest = sha256_file(path)

    # Read + schema validation
    df = pd.read_csv(path)
    ensure_deidentified(df)

    card = load_model_card()
    features = card.get("features") or []
    missing = [c for c in features if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required feature columns: {missing}")
    if "label" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing required target column: label (0/1)")

    # Sanity
    df = df.dropna(subset=["label"])
    n_rows = int(len(df))
    if n_rows < 50:
        raise HTTPException(status_code=400, detail="Dataset too small for external validation (need >=50 rows)")
    if len(set(df["label"].astype(int).unique())) < 2:
        raise HTTPException(status_code=400, detail="Need both classes in label for AUROC (0 and 1)")

    schema_json = json.dumps({"columns": list(df.columns)}, sort_keys=True)

    row = SiteDataset(
        id=dataset_id,
        org_id=user.org_id,
        facility_id=facility_id or None,
        country_code=country_code or None,
        site_name=site_name,
        description=description or None,
        file_path=path,
        sha256=digest,
        n_rows=n_rows,
        schema_json=schema_json,
    )
    db.add(row)
    db.commit()

    return {"ok": True, "dataset_id": dataset_id, "sha256": digest, "n_rows": n_rows}


@router.get("/datasets")
def list_site_datasets(db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    rows = db.query(SiteDataset).filter(SiteDataset.org_id == user.org_id).order_by(SiteDataset.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "site_name": r.site_name,
            "country_code": r.country_code,
            "n_rows": r.n_rows,
            "sha256": r.sha256,
        }
        for r in rows
    ]


@router.post("/run/{dataset_id}")
def run_external_validation(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    if user.role != "public":
        require_active_subscription(user=user, db=db)

    ds = db.query(SiteDataset).filter(SiteDataset.id == dataset_id, SiteDataset.org_id == user.org_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _, meta = get_model()

    run_id = _uuid()
    run = ValidationRun(
        id=run_id,
        org_id=user.org_id,
        dataset_id=dataset_id,
        modality="tabular",
        model_name=meta["model_name"],
        model_version=meta["model_version"],
        status="queued",
        metrics_json=json.dumps({}, sort_keys=True),
        report_pdf_path=None,
    )
    db.add(run)
    db.commit()

    try:
        from rq import Queue
    except Exception:
        raise HTTPException(status_code=503, detail="Background queue dependency 'rq' is not installed")

    conn = redis.from_url(settings.REDIS_URL)
    q = Queue("default", connection=conn)
    q.enqueue(run_validation_job, run_id, dataset_id)

    return {"ok": True, "run_id": run_id, "status": "queued"}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    rows = db.query(ValidationRun).filter(ValidationRun.org_id == user.org_id).order_by(ValidationRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "dataset_id": r.dataset_id,
            "status": r.status,
            "model_name": r.model_name,
            "model_version": r.model_version,
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    r = db.query(ValidationRun).filter(ValidationRun.id == run_id, ValidationRun.org_id == user.org_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "dataset_id": r.dataset_id,
        "status": r.status,
        "model_name": r.model_name,
        "model_version": r.model_version,
        "metrics": json.loads(r.metrics_json),
    }


@router.get("/runs/{run_id}/report.pdf")
def download_run_report(run_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.super_admin, Role.org_admin))):
    r = db.query(ValidationRun).filter(ValidationRun.id == run_id, ValidationRun.org_id == user.org_id).first()
    if not r or not r.report_pdf_path:
        raise HTTPException(status_code=404, detail="Report not found")
    with open(r.report_pdf_path, "rb") as f:
        content = f.read()
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="external_validation_{run_id}.pdf"'},
    )
