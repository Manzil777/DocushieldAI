from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.tests.fixtures.sample_data import OCR_TEXT_SAMPLES


@pytest.fixture
def sample_color_image() -> np.ndarray:
    image = np.zeros((32, 48, 3), dtype=np.uint8)
    image[:, :16] = (25, 50, 200)
    image[:, 16:32] = (220, 220, 220)
    image[:, 32:] = (0, 180, 0)
    cv2.line(image, (0, 0), (47, 31), (255, 255, 255), 2)
    cv2.rectangle(image, (8, 8), (20, 20), (0, 0, 0), -1)
    return image


@pytest.fixture
def blurry_color_image() -> np.ndarray:
    return np.full((32, 48, 3), 127, dtype=np.uint8)


@pytest.fixture
def sample_gray_image(sample_color_image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(sample_color_image, cv2.COLOR_BGR2GRAY)


@pytest.fixture
def sample_png_path(tmp_path: Path, sample_color_image: np.ndarray) -> Path:
    path = tmp_path / "sample.png"
    ok = cv2.imwrite(str(path), sample_color_image)
    if not ok:
        raise RuntimeError("Failed to write sample PNG fixture.")
    return path


@pytest.fixture
def ocr_text_samples() -> dict[str, str]:
    return OCR_TEXT_SAMPLES.copy()


@pytest.fixture
def sample_detections() -> list[dict[str, object]]:
    return [
        {"class": "name", "bbox": [0, 0, 18, 18]},
        {"class": "aadhaar_number", "bbox": [18, 0, 40, 18]},
        {"class": "empty_field", "bbox": [45, 30, 45, 30]},
    ]
