import os, json, csv, datetime as dt
import numpy as np
from joblib import dump
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.datasets import ImageFolder

from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss
from app.ml.retina.model import TemperatureScaler  # reuse
from app.ml.skin.model import build_skin_model

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "skin")
os.makedirs(ART_DIR, exist_ok=True)


class CsvSkinDataset(Dataset):
    """Dataset for flat image folders with labels in a CSV file."""
    def __init__(self, images_dir, labels_csv, transform):
        self.images_dir = images_dir
        self.transform = transform
        self.samples = []

        with open(labels_csv, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fname = row.get("filename")
                if not fname:
                    continue

                image_path = os.path.join(images_dir, fname)
                if not os.path.exists(image_path):
                    continue

                # Positive class is Acanthosis Nigricans.
                y = None
                if "Acanthosis Nigricans" in row and "Healthy" in row:
                    try:
                        y = int(float(row["Acanthosis Nigricans"]) > float(row["Healthy"]))
                    except (TypeError, ValueError):
                        y = None
                elif "Acanthosis Nigricans" in row:
                    try:
                        y = int(float(row["Acanthosis Nigricans"]) >= 0.5)
                    except (TypeError, ValueError):
                        y = None

                if y is None:
                    continue

                self.samples.append((image_path, y))

        if not self.samples:
            raise ValueError(f"No labeled samples loaded from {labels_csv}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        image_path, y = self.samples[idx]
        with Image.open(image_path) as img:
            x = self.transform(img.convert("RGB"))
        return x, y


def _pick_first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _has_class_subdirs(path):
    if not os.path.isdir(path):
        return False
    return any(entry.is_dir() for entry in os.scandir(path))

def softmax_np(logits):
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return e / (e.sum(axis=1, keepdims=True) + 1e-9)

@torch.no_grad()
def eval_logits(model, loader, device):
    model.eval()
    ys, logits_all = [], []
    for x, y in loader:
        x = x.to(device)
        logits = model(x).detach().cpu().numpy()
        logits_all.append(logits)
        ys.append(y.numpy())
    return np.concatenate(ys), np.concatenate(logits_all)

def fit_temperature_scaler(logits, y_true):
    device = torch.device("cpu")
    logits_t = torch.tensor(logits, dtype=torch.float32, device=device)
    y_t = torch.tensor(y_true, dtype=torch.long, device=device)

    scaler = TemperatureScaler().to(device)
    opt = torch.optim.LBFGS([scaler.temperature], lr=0.1, max_iter=50)
    ce = nn.CrossEntropyLoss()

    def closure():
        opt.zero_grad()
        loss = ce(scaler(logits_t), y_t)
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(scaler.temperature.detach(), 0.05, 10.0).item())

def train_one_epoch(model, loader, opt, device):
    model.train()
    ce = nn.CrossEntropyLoss()
    total = 0
    correct = 0
    loss_sum = 0.0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        opt.zero_grad()
        logits = model(x)
        loss = ce(logits, y)
        loss.backward()
        opt.step()
        loss_sum += float(loss.item()) * len(y)
        pred = logits.argmax(dim=1)
        correct += int((pred == y).sum().item())
        total += len(y)
    return loss_sum / max(1,total), correct / max(1,total)

def main():
    root = os.path.join(REPO_ROOT, "data", "skin")
    tr_dir = os.path.join(root,"train")
    va_dir = _pick_first_existing([os.path.join(root, "val"), os.path.join(root, "valid")])
    if not os.path.exists(tr_dir) or va_dir is None:
        raise SystemExit(
            f"Missing dataset directories. Expected train={tr_dir} and val/valid under {root}"
        )

    tfm = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]),
    ])

    use_imagefolder = _has_class_subdirs(tr_dir) and _has_class_subdirs(va_dir)
    if use_imagefolder:
        ds_tr = ImageFolder(tr_dir, transform=tfm)
        ds_va = ImageFolder(va_dir, transform=tfm)
        print(f"Using ImageFolder layout: train={tr_dir}, val={va_dir}")
    else:
        labels_dir = os.path.join(root, "labels")
        tr_csv = os.path.join(labels_dir, "train_labels.csv")
        va_name = os.path.basename(va_dir)
        va_csv = os.path.join(labels_dir, f"{va_name}_labels.csv")
        if not os.path.exists(tr_csv) or not os.path.exists(va_csv):
            raise SystemExit(
                f"Flat-folder dataset detected, but label CSVs were not found: {tr_csv}, {va_csv}"
            )
        ds_tr = CsvSkinDataset(tr_dir, tr_csv, tfm)
        ds_va = CsvSkinDataset(va_dir, va_csv, tfm)
        print(f"Using CSV layout: train={tr_dir} ({tr_csv}), val={va_dir} ({va_csv})")

    dl_tr = DataLoader(ds_tr, batch_size=16, shuffle=True, num_workers=0)
    dl_va = DataLoader(ds_va, batch_size=16, shuffle=False, num_workers=0)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_skin_model(num_classes=2).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-4)

    best_acc, best_state = 0.0, None
    for epoch in range(8):
        tr_loss, tr_acc = train_one_epoch(model, dl_tr, opt, device)
        y_va, logits_va = eval_logits(model, dl_va, device)
        va_acc = float(accuracy_score(y_va, logits_va.argmax(axis=1)))
        if va_acc > best_acc:
            best_acc = va_acc
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        print(f"epoch {epoch+1}: train_loss={tr_loss:.4f} train_acc={tr_acc:.3f} val_acc={va_acc:.3f}")

    model.load_state_dict(best_state)
    y_va, logits_va = eval_logits(model, dl_va, device)

    temp = fit_temperature_scaler(logits_va, y_va)
    logits_cal = logits_va / temp
    proba = softmax_np(logits_cal)[:,1]

    auc = float(roc_auc_score(y_va, proba)) if len(np.unique(y_va)) == 2 else None
    brier = float(brier_score_loss(y_va, proba))
    acc = float(accuracy_score(y_va, (proba>=0.5).astype(int)))

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = "skin_resnet18_tempcal"

    bundle = {
        "model_name": model_name,
        "model_version": version,
        "arch": "resnet18",
        "state_dict": best_state,
        "temperature": temp,
        "classes": ["negative","positive"],
        "image_size": 224,
        "normalize": {"mean":[0.485,0.456,0.406], "std":[0.229,0.224,0.225]},
        "val_metrics": {"auroc": auc, "brier": brier, "accuracy": acc},
    }

    model_path = os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
    dump(bundle, model_path)

    with open(os.path.join(ART_DIR,"modelcard.json"),"w",encoding="utf-8") as f:
        json.dump({
            "model_name": model_name,
            "model_version": version,
            "classes": bundle["classes"],
            "intended_use": "Skin screening support (acanthosis nigrican risk proxy). Not a definitive diabetes diagnosis.",
            "calibration": {"method":"temperature_scaling","temperature":temp},
            "metrics_val": bundle["val_metrics"],
            "created_at_utc": dt.datetime.utcnow().isoformat()+"Z",
        }, f, indent=2)

    model_ref = os.path.relpath(model_path, REPO_ROOT).replace(os.sep, "/")
    with open(os.path.join(ART_DIR,"registry.json"),"w",encoding="utf-8") as f:
        json.dump({"current":{"model_name":model_name,"model_version":version,"model_path":model_ref}}, f, indent=2)

    print("Saved:", model_path, "Val:", bundle["val_metrics"], "Temp:", temp)

if __name__ == "__main__":
    main()
