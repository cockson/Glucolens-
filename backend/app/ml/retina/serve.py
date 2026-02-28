import os, json, base64
import numpy as np
from io import BytesIO
from PIL import Image
from joblib import load
from app.ml.retina.quality import quality_check_rgb_uint8, pil_to_rgb_uint8

import torch
from torchvision import transforms

from app.ml.retina.model import build_retina_model
from app.ml.retina.gradcam import GradCAM, overlay_cam_on_image

# Resolve paths relative to backend repo root regardless of cwd.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART_DIR = os.path.join(REPO_ROOT, "artifacts", "retina")
REGISTRY = os.path.join(ART_DIR, "registry.json")

_cached = {"bundle": None, "model": None, "cam": None, "tfm": None}

def _load_registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        return json.load(f)["current"]

def get_bundle():
    if _cached["bundle"] is None:
        reg = _load_registry()
        _cached["bundle"] = load(reg["model_path"])
    return _cached["bundle"]

def get_model():
    if _cached["model"] is None:
        b = get_bundle()
        model = build_retina_model(num_classes=2)
        model.load_state_dict(b["state_dict"])
        model.eval()
        _cached["model"] = model

        # Grad-CAM target layer for resnet18:
        _cached["cam"] = GradCAM(model, model.layer4[-1])

        mean = b["normalize"]["mean"]
        std = b["normalize"]["std"]
        size = b["image_size"]

        _cached["tfm"] = transforms.Compose([
            transforms.Resize((size,size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=mean, std=std),
        ])

    return _cached["model"], _cached["cam"], _cached["tfm"], get_bundle()

def _softmax(logits):
    ex = np.exp(logits - logits.max())
    return ex / (ex.sum() + 1e-9)

def predict_retina(image_bytes: bytes):
    model, cam, tfm, bundle = get_model()

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    rgb_full = pil_to_rgb_uint8(img)
    ok, reason, qm = quality_check_rgb_uint8(rgb_full)

    if not ok:
        return {
            "model_name": bundle["model_name"],
            "model_version": bundle["model_version"],
            "predicted_label": "retake_image",
            "probabilities": {"not_diabetic": None, "t2d": None},
            "explainability": {
                "method": "gradcam",
                "overlay_png_base64": None
            },
            "quality_gate": {"passed": False, "reason": reason, "metrics": qm}
        }

    x = tfm(img).unsqueeze(0)  # [1,3,H,W]

    with torch.no_grad():
        logits = model(x).cpu().numpy()[0]

    temp = float(bundle.get("temperature", 1.0))
    logits_cal = logits / max(0.05, temp)
    probs = _softmax(logits_cal)
    p1 = float(probs[1])
    label = "t2d" if p1 >= 0.5 else "not_diabetic"

    # Grad-CAM for predicted class
    class_idx = int(np.argmax(probs))
    cam_map = cam.generate(x, class_idx=class_idx)

    # Build overlay image (base64 PNG)
    rgb = np.array(img.resize((224,224))).astype(np.uint8)
    overlay = overlay_cam_on_image(rgb, cam_map, alpha=0.45)

    out_img = Image.fromarray(overlay)
    buf = BytesIO()
    out_img.save(buf, format="PNG")
    overlay_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "model_name": bundle["model_name"],
        "model_version": bundle["model_version"],
        "predicted_label": label,
        "probabilities": {"not_diabetic": float(probs[0]), "t2d": float(probs[1])},
        "explainability": {
            "method": "gradcam",
            "overlay_png_base64": overlay_b64
        },
        "quality_gate": {"passed": True, "reason": "ok", "metrics": qm}
    }

def load_model_card():
    with open(os.path.join(ART_DIR, "modelcard.json"), "r", encoding="utf-8") as f:
        return json.load(f)
