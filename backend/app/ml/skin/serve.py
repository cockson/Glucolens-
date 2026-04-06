import os, json, base64
import numpy as np
from io import BytesIO
from PIL import Image
from joblib import load
import torch
from torchvision import transforms

from app.ml.artifacts import resolve_artifact_path
from app.ml.skin.model import build_skin_model
from app.ml.skin.gradcam import GradCAM, overlay_cam_on_image
from app.ml.skin.quality import pil_to_rgb_uint8, quality_check_rgb_uint8

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
ART_CANDIDATES = [
    os.path.join(REPO_ROOT, "artifacts", "skin"),
    os.path.join(PROJECT_ROOT, "backend", "artifacts", "skin"),
]
_cached = {"bundle":None,"model":None,"cam":None,"tfm":None}

def _find_art_dir() -> str:
    for d in ART_CANDIDATES:
        if os.path.isfile(os.path.join(d, "registry.json")):
            return d
    # Return default location for a clearer downstream error if missing.
    return ART_CANDIDATES[0]

def _resolve_model_path(path: str) -> str:
    return resolve_artifact_path(
        path,
        repo_root=REPO_ROOT,
        project_root=PROJECT_ROOT,
        artifact_dir=_find_art_dir(),
    )

def _load_registry():
    art = _find_art_dir()
    with open(os.path.join(art, "registry.json"),"r",encoding="utf-8") as f:
        return json.load(f)["current"]

def get_bundle():
    if _cached["bundle"] is None:
        reg = _load_registry()
        _cached["bundle"] = load(_resolve_model_path(reg["model_path"]))
    return _cached["bundle"]

def get_model():
    if _cached["model"] is None:
        b = get_bundle()
        m = build_skin_model(num_classes=2)
        m.load_state_dict(b["state_dict"])
        m.eval()
        _cached["model"] = m
        _cached["cam"] = GradCAM(m, m.layer4[-1])
        mean, std = b["normalize"]["mean"], b["normalize"]["std"]
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

def predict_skin(image_bytes: bytes):
    model, cam, tfm, bundle = get_model()
    img = Image.open(BytesIO(image_bytes)).convert("RGB")

    rgb_full = pil_to_rgb_uint8(img)
    ok, reason, qm = quality_check_rgb_uint8(rgb_full)
    if not ok:
        return {
            "model_name": bundle["model_name"],
            "model_version": bundle["model_version"],
            "predicted_label": "retake_image",
            "probabilities": {"negative": None, "positive": None},
            "explainability": {"method":"gradcam","overlay_png_base64":None},
            "quality_gate": {"passed":False,"reason":reason,"metrics":qm},
        }

    x = tfm(img).unsqueeze(0)
    with torch.no_grad():
        logits = model(x).cpu().numpy()[0]

    temp = float(bundle.get("temperature", 1.0))
    probs = _softmax(logits / max(0.05,temp))
    p_pos = float(probs[1])
    label = "positive" if p_pos >= 0.5 else "negative"

    class_idx = int(np.argmax(probs))
    cam_map = cam.generate(x, class_idx=class_idx)

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
        "probabilities": {"negative": float(probs[0]), "positive": float(probs[1])},
        "explainability": {"method":"gradcam","overlay_png_base64":overlay_b64},
        "quality_gate": {"passed":True,"reason":"ok","metrics":qm},
    }

def load_model_card():
    art = _find_art_dir()
    with open(os.path.join(art,"modelcard.json"),"r",encoding="utf-8") as f:
        return json.load(f)

def load_performance():
    art = _find_art_dir()
    perf_path = os.path.join(art, "performance.json")
    if os.path.isfile(perf_path):
        with open(perf_path, "r", encoding="utf-8") as f:
            return {"performance": json.load(f)}
    # Backward-compatible fallback to model card metrics.
    card = load_model_card()
    return {"performance": card.get("metrics_val")}
