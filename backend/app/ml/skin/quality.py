import numpy as np
import cv2
from PIL import Image

def pil_to_rgb_uint8(img: Image.Image):
    return np.array(img.convert("RGB")).astype(np.uint8)

def quality_check_rgb_uint8(rgb: np.ndarray):
    h, w = rgb.shape[:2]
    if h < 160 or w < 160:
        return False, "image_too_small", {"h": h, "w": w}

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    bright = float(gray.mean())

    ok_blur = blur >= 30.0
    ok_bright = 30.0 <= bright <= 230.0

    ok = ok_blur and ok_bright
    reason = "ok"
    if not ok_blur: reason = "too_blurry"
    elif not ok_bright: reason = "bad_exposure"

    return ok, reason, {"blur": blur, "brightness": bright, "h": h, "w": w}