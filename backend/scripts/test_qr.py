from __future__ import annotations

import base64
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.ai.qr_validator import validate_qr


IMAGE_ROOT = REPO_ROOT / "data/aadhaar"


def discover_background() -> Path:
    images = sorted(
        path
        for ext in ("*.jpg", "*.jpeg", "*.png")
        for path in IMAGE_ROOT.rglob(ext)
    )
    if not images:
        raise FileNotFoundError(f"No images found under {IMAGE_ROOT}")
    return images[0]


def build_payload_xml() -> str:
    return (
        '<PrintLetterBarcodeData uid="123456789012" '
        'name="John Doe" dob="01/01/2000" gender="M" />'
    )


def encode_payload(payload_xml: str) -> str:
    compressed = zlib.compress(payload_xml.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")


def generate_qr_image(payload: str) -> np.ndarray:
    params = cv2.QRCodeEncoder_Params()
    encoder = cv2.QRCodeEncoder_create(params)
    qr = encoder.encode(payload)
    if qr.ndim == 2:
        qr = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
    qr = cv2.resize(qr, (240, 240), interpolation=cv2.INTER_NEAREST)
    return qr


def compose_qr_on_image(background: np.ndarray, qr_image: np.ndarray) -> np.ndarray:
    composed = background.copy()
    height, width = composed.shape[:2]
    qr_height, qr_width = qr_image.shape[:2]
    y1 = max(10, height - qr_height - 10)
    x1 = max(10, width - qr_width - 10)
    composed[y1:y1 + qr_height, x1:x1 + qr_width] = qr_image
    return composed


def corrupt_qr(qr_image: np.ndarray) -> np.ndarray:
    corrupted = cv2.GaussianBlur(qr_image, (17, 17), 0)
    cv2.line(corrupted, (0, 0), (corrupted.shape[1] - 1, corrupted.shape[0] - 1), (127, 127, 127), 12)
    return corrupted


def main() -> int:
    background_path = discover_background()
    background = cv2.imread(str(background_path))
    if background is None:
        raise ValueError(f"Failed to read background image: {background_path}")

    ocr_data = {
        "aadhaar_number": {"normalized": "123456789012"},
        "name": {"normalized": "John Doe"},
        "dob": {"normalized": "01/01/2000"},
        "gender": {"normalized": "Male"},
    }

    payload_xml = build_payload_xml()
    encoded_payload = encode_payload(payload_xml)
    qr_image = generate_qr_image(encoded_payload)

    test_cases = [
        ("valid_qr", compose_qr_on_image(background, qr_image)),
        ("no_qr", background),
        ("corrupted_qr", compose_qr_on_image(background, corrupt_qr(qr_image))),
    ]

    print("QR Validation Report")
    print("====================")
    for name, image in test_cases:
        result = validate_qr(image, ocr_data)
        payload = result.get("payload", {})
        print(
            f"{name} | qr_valid={result['qr_valid']} | "
            f"fields_match={result['fields_match']} | "
            f"uid={payload.get('uid', '')} | name={payload.get('name', '')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
