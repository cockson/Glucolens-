import os, json, datetime as dt
import numpy as np
import pandas as pd
from PIL import Image
from io import BytesIO

import torch
from torch.utils.data import DataLoader, Dataset
from torchvision.datasets import ImageFolder
from torchvision import transforms

from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, accuracy_score, f1_score, log_loss
from sklearn.linear_model import LogisticRegression

from app.ml.retina.serve import get_model
from app.services.validation_metrics import delong_auc_ci, decision_curve_net_benefit

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "retina")
os.makedirs(ART_DIR, exist_ok=True)

def expected_calibration_error(y, p, n_bins=10):
    y = np.asarray(y); p = np.asarray(p)
    bins = np.linspace(0, 1, n_bins+1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i+1]
        mask = (p >= lo) & (p < hi) if i < n_bins-1 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        acc = y[mask].mean()
        conf = p[mask].mean()
        ece += (mask.sum()/len(y)) * abs(acc - conf)
    return float(ece)

def calibration_slope_intercept(y, p):
    eps = 1e-6
    p = np.clip(p, eps, 1-eps)
    logit = np.log(p/(1-p)).reshape(-1,1)
    lr = LogisticRegression(solver="lbfgs")
    lr.fit(logit, y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


class CsvRetinaDataset(Dataset):
    def __init__(self, image_dir: str, labels_csv: str, transform=None):
        self.image_dir = image_dir
        self.transform = transform

        df = pd.read_csv(labels_csv)
        label_cols = [c for c in df.columns if c != "filename"]
        if "No_DR" not in label_cols:
            raise ValueError("Expected 'No_DR' column in labels CSV")

        records = []
        for _, row in df.iterrows():
            fname = str(row["filename"])
            path = os.path.join(image_dir, fname)
            if not os.path.exists(path):
                continue
            # Binary target: No_DR -> 0, any DR stage -> 1.
            y = 0 if int(row.get("No_DR", 0)) == 1 else 1
            records.append((path, y))
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        path, y = self.records[idx]
        img = Image.open(path).convert("RGB")
        if self.transform is not None:
            img = self.transform(img)
        return img, int(y)

@torch.no_grad()
def infer_probs(loader, model, tfm, bundle):
    ys = []
    ps = []
    model.eval()
    temp = float(bundle.get("temperature", 1.0))

    for x, y in loader:
        logits = model(x).cpu().numpy()
        logits = logits / max(0.05, temp)
        # softmax
        ex = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = ex / (ex.sum(axis=1, keepdims=True) + 1e-9)
        p1 = probs[:, 1]
        ys.append(y.numpy())
        ps.append(p1)
    return np.concatenate(ys), np.concatenate(ps)

def main():
    data_root = os.path.join(REPO_ROOT, "data", "retina")
    val_dir = os.path.join(data_root,"val")
    if not os.path.exists(val_dir):
        raise SystemExit("Missing data/retina/val")

    model, cam, tfm, bundle = get_model()

    # Support both ImageFolder layout and flat-images + labels CSV layout.
    class_dirs = [n for n in os.listdir(val_dir) if os.path.isdir(os.path.join(val_dir, n))]
    if class_dirs:
        ds = ImageFolder(val_dir, transform=tfm)
    else:
        labels_csv = os.path.join(data_root, "labels", "val_labels.csv")
        if not os.path.exists(labels_csv):
            raise SystemExit("Missing data/retina/labels/val_labels.csv for flat val dataset")
        ds = CsvRetinaDataset(val_dir, labels_csv, transform=tfm)
    dl = DataLoader(ds, batch_size=16, shuffle=False, num_workers=0)

    y, p = infer_probs(dl, model, tfm, bundle)

    # Metrics
    auroc = float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None
    auprc = float(average_precision_score(y, p)) if len(np.unique(y)) == 2 else None
    brier = float(brier_score_loss(y, p))
    ece = expected_calibration_error(y, p)
    slope, intercept = calibration_slope_intercept(y, p)
    acc = float(accuracy_score(y, (p >= 0.5).astype(int)))
    f1 = float(f1_score(y, (p >= 0.5).astype(int)))
    ll = float(log_loss(y, np.vstack([1-p, p]).T, labels=[0,1]))

    ci = None
    if len(np.unique(y)) == 2:
        a, lo, hi = delong_auc_ci(y, p, alpha=0.95)
        ci = {"auroc": a, "ci_low": lo, "ci_high": hi}

    dca = decision_curve_net_benefit(y, p)

    perf = {
        "current": {"model_name": bundle["model_name"], "model_version": bundle["model_version"]},
        "val": {
            "n": int(len(y)),
            "positive_rate": float(y.mean()),
            "auroc": auroc,
            "auroc_delong_95ci": ci,
            "auprc": auprc,
            "brier": brier,
            "ece": ece,
            "cal_slope": slope,
            "cal_intercept": intercept,
            "accuracy": acc,
            "f1": f1,
            "log_loss": ll,
        },
        "decision_curve": dca,
        "created_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "notes": [
            "Validation computed on backend/data/retina/val using current registry model.",
            "Retina explains via Grad-CAM; use quality gate for clinical intake."
        ]
    }

    with open(os.path.join(ART_DIR, "performance.json"), "w", encoding="utf-8") as f:
        json.dump(perf, f, indent=2)

    # comparison.csv: minimal comparison table (future: multiple architectures)
    comp = pd.DataFrame([{
        "model": bundle["model_name"],
        "version": bundle["model_version"],
        "auroc": auroc,
        "auroc_ci_low": ci["ci_low"] if ci else None,
        "auroc_ci_high": ci["ci_high"] if ci else None,
        "brier": brier,
        "ece": ece,
        "cal_slope": slope,
        "cal_intercept": intercept,
        "accuracy": acc,
        "f1": f1,
        "log_loss": ll,
    }])
    comp.to_csv(os.path.join(ART_DIR, "comparison.csv"), index=False)

    print("Saved performance.json + comparison.csv in", ART_DIR)

if __name__ == "__main__":
    main()
