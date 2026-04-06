import os, json, csv, datetime as dt
import numpy as np
from joblib import dump
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms

from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss

from app.ml.retina.model import build_retina_model, TemperatureScaler

# Resolve paths relative to repo root (backend/) regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "retina")
os.makedirs(ART_DIR, exist_ok=True)

class RetinaCSVBinaryDataset(Dataset):
    """
    CSV-backed dataset for Roboflow-style labels:
    filename,No_DR,mild,moderate,proliferate_DR,severe
    Reduced to binary labels for this model:
    0 = No_DR (not_diabetic proxy), 1 = any DR (t2d proxy).
    """
    POSITIVE_CLASSES = ("mild", "moderate", "proliferate_DR", "severe")

    def __init__(self, image_dir: str, labels_csv: str, transform=None):
        self.image_dir = image_dir
        self.labels_csv = labels_csv
        self.transform = transform
        self.samples = []

        if not os.path.exists(image_dir):
            raise FileNotFoundError(f"Image directory not found: {image_dir}")
        if not os.path.exists(labels_csv):
            raise FileNotFoundError(f"Labels CSV not found: {labels_csv}")

        with open(labels_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            expected = {"filename", "No_DR", *self.POSITIVE_CLASSES}
            missing_cols = expected.difference(set(reader.fieldnames or []))
            if missing_cols:
                raise ValueError(f"Missing expected label columns in {labels_csv}: {sorted(missing_cols)}")

            for row in reader:
                filename = row["filename"].strip()
                img_path = os.path.join(image_dir, filename)
                if not os.path.exists(img_path):
                    continue

                is_positive = any(int(row[c]) == 1 for c in self.POSITIVE_CLASSES)
                label = 1 if is_positive else 0
                self.samples.append((img_path, label))

        if not self.samples:
            raise ValueError(f"No valid samples found using {labels_csv} and images in {image_dir}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert("RGB")
        if self.transform is not None:
            img = self.transform(img)
        return img, label

def softmax_np(logits):
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return e / (e.sum(axis=1, keepdims=True) + 1e-9)

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

@torch.no_grad()
def eval_logits(model, loader, device):
    model.eval()
    ys = []
    logits_all = []
    for x, y in loader:
        x = x.to(device)
        logits = model(x).detach().cpu().numpy()
        logits_all.append(logits)
        ys.append(y.numpy())
    return np.concatenate(ys), np.concatenate(logits_all)

def fit_temperature_scaler(logits, y_true):
    """
    Fit temperature scaler on validation logits.
    """
    device = torch.device("cpu")
    logits_t = torch.tensor(logits, dtype=torch.float32, device=device)
    y_t = torch.tensor(y_true, dtype=torch.long, device=device)

    scaler = TemperatureScaler().to(device)
    opt = torch.optim.LBFGS([scaler.temperature], lr=0.1, max_iter=50)

    ce = nn.CrossEntropyLoss()

    def closure():
        opt.zero_grad()
        scaled = scaler(logits_t)
        loss = ce(scaled, y_t)
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(scaler.temperature.detach(), 0.05, 10.0).item())

def main():
    data_root = os.path.join(REPO_ROOT, "data", "retina")
    train_dir = os.path.join(data_root, "train")
    val_dir = os.path.join(data_root, "val")
    labels_dir = os.path.join(data_root, "labels")
    train_csv = os.path.join(labels_dir, "train_labels.csv")
    val_csv = os.path.join(labels_dir, "val_labels.csv")

    if not os.path.exists(train_dir) or not os.path.exists(val_dir) or not os.path.exists(labels_dir):
        raise SystemExit("Expected dataset folders: data/retina/train, data/retina/val, and data/retina/labels")

    tfm = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]),
    ])

    ds_tr = RetinaCSVBinaryDataset(train_dir, train_csv, transform=tfm)
    ds_va = RetinaCSVBinaryDataset(val_dir, val_csv, transform=tfm)

    dl_tr = DataLoader(ds_tr, batch_size=16, shuffle=True, num_workers=0)
    dl_va = DataLoader(ds_va, batch_size=16, shuffle=False, num_workers=0)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_retina_model(num_classes=2).to(device)

    opt = torch.optim.Adam(model.parameters(), lr=1e-4)

    best_acc = 0.0
    best_state = None

    for epoch in range(8):
        tr_loss, tr_acc = train_one_epoch(model, dl_tr, opt, device)
        y_va, logits_va = eval_logits(model, dl_va, device)
        pred_va = logits_va.argmax(axis=1)
        va_acc = float(accuracy_score(y_va, pred_va))

        if va_acc > best_acc:
            best_acc = va_acc
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}

        print(f"epoch {epoch+1}: train_loss={tr_loss:.4f} train_acc={tr_acc:.3f} val_acc={va_acc:.3f}")

    # Restore best
    model.load_state_dict(best_state)
    y_va, logits_va = eval_logits(model, dl_va, device)

    # Fit temperature scaling on validation
    temp = fit_temperature_scaler(logits_va, y_va)

    # Calibrated probabilities on val
    logits_cal = logits_va / temp
    proba = softmax_np(logits_cal)[:, 1]

    # Metrics
    auc = float(roc_auc_score(y_va, proba)) if len(np.unique(y_va)) == 2 else None
    brier = float(brier_score_loss(y_va, proba))
    acc = float(accuracy_score(y_va, (proba >= 0.5).astype(int)))

    version = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_name = "retina_resnet18_tempcal"

    # Save as joblib bundle (your requirement)
    bundle = {
        "model_name": model_name,
        "model_version": version,
        "arch": "resnet18",
        "state_dict": best_state,
        "temperature": temp,
        "classes": ["not_diabetic", "t2d"],
        "image_size": 224,
        "normalize": {"mean":[0.485,0.456,0.406], "std":[0.229,0.224,0.225]},
        "val_metrics": {"auroc": auc, "brier": brier, "accuracy": acc},
    }

    path = os.path.join(ART_DIR, f"{model_name}_{version}.joblib")
    dump(bundle, path)

    # Model card + registry
    modelcard = {
        "model_name": model_name,
        "model_version": version,
        "classes": bundle["classes"],
        "intended_use": "Retina screening support. Not a definitive diabetes diagnosis.",
        "calibration": {"method": "temperature_scaling", "temperature": temp},
        "metrics_val": bundle["val_metrics"],
        "data": {"train_dir": "data/retina/train", "val_dir": "data/retina/val"},
        "created_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "limitations": [
            "Retina model detects retinal patterns correlated with diabetic complications (e.g., DR).",
            "Use within clinical workflow; confirm with lab tests.",
        ],
    }
    with open(os.path.join(ART_DIR, "modelcard.json"), "w", encoding="utf-8") as f:
        json.dump(modelcard, f, indent=2)

    model_ref = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
    reg = {"current": {"model_name": model_name, "model_version": version, "model_path": model_ref}}
    with open(os.path.join(ART_DIR, "registry.json"), "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)

    print("Saved:", path)
    print("Val metrics:", bundle["val_metrics"], "Temp:", temp)

if __name__ == "__main__":
    main()
