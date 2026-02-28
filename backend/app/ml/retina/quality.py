import numpy as np
import cv2
from PIL import Image

def quality_check_rgb_uint8(rgb: np.ndarray):
    """
    Returns (ok:bool, reason:str, metrics:dict)
    """
    h, w = rgb.shape[:2]
    if h < 200 or w < 200:
        return False, "image_too_small", {"h": h, "w": w}

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Blur score: variance of Laplacian
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Brightness: mean gray
    bright = float(gray.mean())

    ok_blur = blur >= 40.0
    ok_bright = 35.0 <= bright <= 220.0

    ok = ok_blur and ok_bright
    reason = "ok"
    if not ok_blur:
        reason = "too_blurry"
    elif not ok_bright:
        reason = "bad_exposure"

    return ok, reason, {"blur": blur, "brightness": bright, "h": h, "w": w}

def pil_to_rgb_uint8(img: Image.Image):
    img = img.convert("RGB")
    return np.array(img).astype(np.uint8)