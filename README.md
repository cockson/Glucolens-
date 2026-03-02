# GlucoLens

Clinical multimodal diabetes risk-screening platform with:
1. Tabular risk modeling.
2. Retina image screening.
3. Skin image screening.
4. Genomics risk modeling.
5. Fusion inference across modalities.
6. Outcome linkage, monitoring, drift checks, and governance endpoints.

This repository contains both backend and frontend applications.

## Safety and Scope
1. This system is for screening support, not diagnosis.
2. Predictions must be confirmed with clinical workflow and laboratory tests.
3. Development datasets and performance values here are not equivalent to prospective clinical validation.

## Repository Layout
1. `backend/`
2. `frontend/`
3. `.gitattributes` for Git LFS tracking of model binaries.

## End-to-End System Flow
1. User authenticates in frontend and receives JWT.
2. Frontend calls backend endpoints by modality.
3. Backend validates role and subscription for protected routes.
4. Backend runs model inference and explainability.
5. Backend stores `PredictionRecord` with non-PHI payload strategy.
6. Frontend displays prediction, explanations, and downloadable report.
7. Clinician records outcomes by `patient_key`.
8. Outcome is linked to prior prediction.
9. Monitoring uses linked outcomes for AUROC, Brier, calibration buckets, and coverage.
10. Fusion training data can be exported from linked outcomes.

## Backend Architecture
1. Framework: FastAPI.
2. ORM: SQLAlchemy.
3. DB: PostgreSQL via `psycopg2`.
4. Caching/rate-limit infra: Redis and FastAPI limiter integration.
5. Security middleware: custom security headers middleware.
6. Optional slowapi middleware when limiter configuration is available.
7. PDF reporting: ReportLab.
8. ML stack: scikit-learn, imbalanced-learn, SHAP, torch/torchvision for image models.

### Main backend entrypoint
1. `backend/app/main.py` starts API app and mounts all routers.
2. Health endpoint: `GET /health`.
3. Routers currently mounted:
4. `/api/auth`
5. `/api/tenancy`
6. `/api/billing`
7. `/api/referrals`
8. `/api/outcomes`
9. `/api/admin`
10. `/api/audit`
11. `/api/predict`
12. `/api/monitor`
13. `/api/validation`
14. `/api/retina`
15. `/api/fusion`
16. `/api/thresholds`
17. `/api/skin`
18. `/api/genomics`

## Frontend Architecture
1. Framework: React + Vite.
2. Router: `react-router-dom`.
3. HTTP client: Axios.
4. Main protected app shell route config: `frontend/src/pages/App.jsx`.
5. Sidebar is primary navigation for screening, model cards, monitoring, governance.
6. Model insights pages now render clean label/value cards instead of raw JSON dumps.

## Environment Configuration
Backend uses `.env` and `.env.example`.

Core keys in `backend/.env.example`:
1. `ENV`
2. `APP_NAME`
3. `API_BASE_URL`
4. `FRONTEND_BASE_URL`
5. `DATABASE_URL`
6. `REDIS_URL`
7. `SETUP_TOKEN`
8. `JWT_SECRET`
9. `JWT_ACCESS_TTL_MIN`
10. `JWT_REFRESH_TTL_DAYS`
11. `CORS_ALLOW_ORIGINS`
12. Paystack keys and plan amounts.

## Datasets
All datasets currently live under `backend/data/`.

### 1) Anthropometric tabular source files
Directory: `backend/data/anthropometric_data/`

Files and row counts:
1. `ncd_high_ncd_burden.csv`: 10,000 rows.
2. `ncd_moderate_ncd_burden.csv`: 10,000 rows.
3. `ncd_low_ncd_burden.csv`: 10,000 rows.
4. `train_tabular.csv`: 20,000 rows after canonical mapping and filtering.
5. `train_tabular.summary.json`: generated preparation summary.

Current merged tabular summary:
1. Rows: 20,000
2. Features: 30
3. 3-class labels:
4. `non_diabetic`: 6,857
5. `prediabetic`: 6,700
6. `diabetic`: 6,443
7. Binary helper label:
8. `0`: 13,557
9. `1`: 6,443
10. Deduplicated rows removed: 0
11. Missingness currently significant mainly in `alcohol_use` at 44.19%.

Target columns:
1. Canonical multiclass target for tabular model: `diabetes_status`
2. Alias support for typo/variant forms exists in preparation scripts.

Important feature note:
1. `hip_circumference` is intentionally removed from current tabular/fusion input expectations.
2. Current tabular feature set includes core vitals plus added fields such as `family_history_diabetes`, `fasting_glucose_mgdl`, `hba1c_pct`, `physical_activity`, `smoking_status`, `bmi_category`.

### 2) Genomics dataset
Directory: `backend/data/genomics/`

Files and row counts:
1. `train.csv`: 1,000 rows.

Expected genomics feature examples in current model card:
1. `TCF7L2_rs7903146`
2. `KCNQ1_rs2237892`
3. `MTNR1B_rs10830963`
4. `SLC30A8_rs13266634`
5. `PPARG_rs1801282`
6. `Age`
7. `BMI`
8. `HbA1c`

### 3) Skin image dataset
Directory: `backend/data/skin/`

Splits and image counts:
1. `train`: 560 images.
2. `valid`: 160 images.
3. `test`: 80 images.

Label CSVs:
1. `labels/train_labels.csv`: 560 rows.
2. `labels/valid_labels.csv`: 160 rows.
3. `labels/test_labels.csv`: 80 rows.

### 4) Retina image dataset
Directory: `backend/data/retina/`

Splits and image counts:
1. `train`: 2,412 images.
2. `val`: 229 images.
3. `test`: 115 images.

Label CSVs:
1. `labels/train_labels.csv`: 2,412 rows.
2. `labels/val_labels.csv`: 229 rows.
3. `labels/test_labels.csv`: 115 rows.

## Model Training and Inference Components

### Tabular
Key files:
1. `backend/app/ml/tabular/prepare_training_data.py`
2. `backend/app/ml/tabular/train_tabular_pro.py`
3. `backend/app/ml/tabular/serve.py`
4. `backend/app/api/routes/predict.py`

Training behavior highlights:
1. Multiclass mapping: non-diabetic, prediabetic, diabetic.
2. Feature normalization and alias mapping.
3. Optional feature dropping by missingness threshold.
4. Nested CV style model selection and calibration.
5. SMOTE path when available.
6. Artifact outputs: model, model card, performance JSON, comparison CSV, registry.

Inference outputs:
1. Class probabilities.
2. Predicted label.
3. Explainability top features via SHAP with fallback method.

### Retina
Key files:
1. `backend/app/ml/retina/train_retina.py`
2. `backend/app/ml/retina/evaluate_retina_pro.py`
3. `backend/app/ml/retina/serve.py`
4. `backend/app/api/routes/retina.py`

Behavior:
1. Quality gate before inference.
2. Softmax probability output.
3. Grad-CAM overlay generation.
4. `retake_image` behavior when quality fails.

### Skin
Key files:
1. `backend/app/ml/skin/train_skin.py`
2. `backend/app/ml/skin/serve.py`
3. `backend/app/api/routes/skin.py`

Behavior:
1. Quality gate before inference.
2. Probability output.
3. Visual explanation overlay support.

### Genomics
Key files:
1. `backend/app/ml/genomics/train_genomics_pro.py`
2. `backend/app/ml/genomics/prepare_genomics.py`
3. `backend/app/ml/genomics/serve.py`
4. `backend/app/api/routes/genomics.py`

Behavior:
1. Logistic regression pipeline with scaling.
2. Calibration strategy selected by sample size.
3. Feature vector reindexing at inference.
4. Coefficient-based explainability summary.

### Fusion
Key files:
1. `backend/app/ml/fusion/train_fusion.py`
2. `backend/app/ml/fusion/export_fusion_train.py`
3. `backend/app/ml/fusion/serve.py`
4. `backend/app/api/routes/fusion.py`

Behavior:
1. Uses tabular prediction plus optional retina/skin/genomics.
2. Includes quality flags per modality.
3. Conservative near-threshold referral logic.
4. Returns `final_label` and `final_proba`.
5. Stores fusion prediction record and supports report export.

## Outcome Linkage and Monitoring
Key files:
1. `backend/app/api/routes/outcome.py`
2. `backend/app/services/linkage.py`
3. `backend/app/services/monitoring.py`
4. `backend/app/api/routes/monitor.py`

Current linkage behavior:
1. Outcome is linked by `org_id` and `patient_key` substring in `input_json`.
2. Linkage now prefers fusion records first, then tabular fallback.

Current monitoring behavior:
1. Computes coverage metrics for outcomes in window.
2. Reports linked-outcome ratio and linked modality counts.
3. Reports tabular metrics.
4. Reports fusion metrics where usable `final_proba` exists.
5. Provides drift snapshots on tabular input distributions.

## API Surface Summary
Main prediction and model-card endpoints:
1. `POST /api/predict/tabular`
2. `POST /api/predict/tabular/public`
3. `GET /api/predict/tabular/model-card`
4. `GET /api/predict/tabular/performance`
5. `POST /api/retina/predict`
6. `GET /api/retina/model-card`
7. `GET /api/retina/performance`
8. `POST /api/skin/predict`
9. `GET /api/skin/model-card`
10. `GET /api/skin/performance`
11. `POST /api/genomics/predict`
12. `GET /api/genomics/model-card`
13. `GET /api/genomics/performance`
14. `POST /api/fusion/predict`
15. `GET /api/fusion/model-card`
16. `GET /api/fusion/performance`
17. `GET /api/monitor/outcomes`
18. `POST /api/monitor/drift/snapshot`
19. `GET /api/monitor/drift/latest`

## Artifacts and Model Registry
Primary artifact roots:
1. `backend/artifacts/tabular`
2. `backend/artifacts/retina`
3. `backend/artifacts/skin`
4. `backend/artifacts/genomics`
5. `backend/artifacts/fusion`

Each modality generally stores:
1. Model binary (`.joblib` for sklearn bundles).
2. `registry.json` pointer to active model.
3. `modelcard.json` or `model_card.json`.
4. `performance.json`.
5. Optional `comparison.csv`.

## Git LFS and Large Files
1. `.joblib` files are tracked by Git LFS via `.gitattributes`.
2. Current rule: `*.joblib filter=lfs diff=lfs merge=lfs -text`.
3. This is required to avoid GitHub large blob push failures.
4. A previously problematic ~1.09GB legacy blob was excluded from active history.

## Local Development

### Backend setup
1. Create and activate Python environment.
2. Install dependencies:
```bash
pip install -r backend/requirements.txt
```
3. Configure `backend/.env` from `backend/.env.example`.
4. Start API:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Run from `backend/`.

### Frontend setup
1. Install dependencies:
```bash
npm install
```
2. Run dev server:
```bash
npm run dev
```
3. Production build check:
```bash
npm run build
```

## Render Deployment
This repo now includes a Render Blueprint file at `render.yaml` that deploys:
1. `glucolens-backend` (FastAPI web service).
2. `glucolens-frontend` (static Vite site).
3. `glucolens-db` (managed PostgreSQL).

By default, the Blueprint is configured to be free-tier friendly (no worker/Redis service).

### One-click deploy
1. Push this repository to GitHub.
2. In Render dashboard: New > Blueprint.
3. Select this repo and apply the Blueprint.
4. After provisioning completes, verify:
5. Backend health: `https://<backend-service>/health`
6. Frontend loads and can call backend APIs.

### Important post-deploy checks
1. Update backend `CORS_ALLOW_ORIGINS` if Render assigned a frontend URL different from `https://glucolens-frontend.onrender.com`.
2. Set Paystack keys in backend and `VITE_PAYSTACK_PUBLIC_KEY` in frontend if billing is used.
3. If you later need background jobs and strict Redis-backed rate limiting, add Worker + Redis services manually (paid tiers may require payment method).

## Common Training Commands
Run from `backend/`:
```bash
python -m app.ml.tabular.prepare_training_data
python -m app.ml.tabular.train_tabular_pro data/anthropometric_data/train_tabular.csv
python -m app.ml.genomics.train_genomics_pro
python -m app.ml.fusion.export_fusion_train
python -m app.ml.fusion.train_fusion
```

## Current Artifact Snapshot Metrics
From current artifact JSON files:
1. Tabular OOF AUROC: `0.9991`
2. Tabular OOF Brier: `0.0218`
3. Retina validation AUROC: `0.9767`
4. Retina validation Brier: `0.0126`
5. Genomics AUC: `0.9992`
6. Genomics Brier: `0.0038`
7. Fusion summary AUROC: `1.0000`
8. Fusion summary Brier: `0.0003`

These values are environment-state snapshots, not guarantees of external generalization.

## Troubleshooting
1. Frontend import error about missing default export:
2. Restart Vite dev server and ensure component has explicit `export default`.
3. Model-card performance endpoint fails:
4. Check artifact `registry.json` and `performance.json` existence.
5. Ensure backend was restarted after code/artifact changes.
6. Push fails due large file:
7. Confirm `.joblib` is tracked by LFS and run `git lfs ls-files`.
8. Monitoring shows low `n`:
9. Verify outcomes have `linked_prediction_id` and consistent `patient_key`.

## Security and Privacy Notes
1. Do not commit real API keys or production secrets.
2. Keep patient identifiers pseudonymized (`patient_key`).
3. Treat model outputs as sensitive clinical support data.
4. Enable strong secret management and transport security in production.

## License and Governance
Add your intended license and governance policy in this file once finalized.
