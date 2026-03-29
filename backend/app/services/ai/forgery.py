from __future__ import annotations

import base64
from io import BytesIO

import cv2
import numpy as np
from PIL import Image


def _validate_image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy.ndarray")
    if image.size == 0:
        raise ValueError("image array is empty")
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3:
        raise ValueError("image must have 2 or 3 dimensions")
    if image.shape[2] == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] != 3:
        raise ValueError("image must be BGR with 3 channels")
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return image


def compute_ela(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute raw and amplified ELA outputs.

    Returns:
        raw_diff_rgb: Absolute RGB difference before amplification.
        amplified_rgb: Difference image amplified for visualization.
        amplified_gray: Grayscale intensity map derived from the amplified image.
    """
    validated = _validate_image(image)
    original_rgb = cv2.cvtColor(validated, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(original_rgb)

    buffer = BytesIO()
    pil_image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    recompressed_rgb = np.array(recompressed)

    raw_diff_rgb = np.abs(
        original_rgb.astype(np.int16) - recompressed_rgb.astype(np.int16)
    ).astype(np.uint8)

    max_pixel_difference = int(raw_diff_rgb.max())
    scale_factor = 255.0 / max_pixel_difference if max_pixel_difference > 0 else 1.0
    amplified_rgb = np.clip(
        raw_diff_rgb.astype(np.float32) * scale_factor,
        0,
        255,
    ).astype(np.uint8)
    amplified_gray = cv2.cvtColor(amplified_rgb, cv2.COLOR_RGB2GRAY)

    return raw_diff_rgb, amplified_rgb, amplified_gray


def compute_threshold(ela_gray: np.ndarray) -> tuple[float, float, float]:
    mean = float(np.mean(ela_gray))
    std = float(np.std(ela_gray))
    threshold = mean + (2.5 * std)
    return mean, std, threshold


def encode_base64(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise ValueError("Failed to encode ELA image as JPEG")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def detect_forgery(image: np.ndarray) -> dict:
    """
    Detect image tampering using Error Level Analysis (ELA).

    The adaptive threshold is computed from the amplified grayscale ELA map,
    while the decision intensity uses the raw grayscale max to avoid trivially
    saturating at 255 after visualization amplification.
    """
    raw_diff_rgb, amplified_rgb, amplified_gray = compute_ela(image)
    raw_gray = cv2.cvtColor(raw_diff_rgb, cv2.COLOR_RGB2GRAY)

    _, _, threshold = compute_threshold(amplified_gray)
    max_intensity = float(np.max(raw_gray))

    is_forged = max_intensity > threshold
    confidence = min(max(max_intensity / (threshold + 1e-6), 0.0), 1.0)

    ela_bgr = cv2.cvtColor(amplified_rgb, cv2.COLOR_RGB2BGR)
    ela_image_b64 = encode_base64(ela_bgr)

    return {
        "is_forged": bool(is_forged),
        "confidence": float(confidence),
        "ela_image": ela_image_b64,
    }
