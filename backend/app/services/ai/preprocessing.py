import cv2
import numpy as np
from pdf2image import convert_from_path
from typing import Union
import os


# ---------------------------
# Utility: Load Image / PDF
# ---------------------------
def _load_input(file_path: str) -> np.ndarray:
    ext = os.path.splitext(file_path)[-1].lower()

    if ext in [".jpg", ".jpeg", ".png"]:
        image = cv2.imread(file_path)
        if image is None:
            raise ValueError("Failed to read image file.")
        return image

    elif ext == ".pdf":
        pages = convert_from_path(file_path, first_page=1, last_page=1)
        if not pages:
            raise ValueError("PDF has no pages.")
        image = np.array(pages[0])
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    else:
        raise ValueError(f"Unsupported file format: {ext}")


# ---------------------------
# Resize
# ---------------------------
def _resize(image: np.ndarray, size=(640, 640)) -> np.ndarray:
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


# ---------------------------
# CLAHE (Contrast Enhancement)
# ---------------------------
def _apply_clahe(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


# ---------------------------
# Adaptive Threshold
# ---------------------------
def _threshold(image: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )


# ---------------------------
# Deskew
# ---------------------------
def _deskew(image: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(image > 0))
    if len(coords) == 0:
        return image

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# ---------------------------
# Blur Detection
# ---------------------------
def _is_blurry(image: np.ndarray, threshold: float = 30.0) -> bool:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance < threshold


# ---------------------------
# Main Pipeline
# ---------------------------
def preprocess_document(file_path: str) -> np.ndarray:
    """
    Preprocess document for OCR + YOLOv8.

    Steps:
    - Load input (image/pdf)
    - Resize
    - Grayscale
    - CLAHE
    - Adaptive threshold
    - Deskew
    - Convert to 3-channel
    """

    image = _load_input(file_path)

    if _is_blurry(image):
        raise ValueError("Input image is too blurry.")

    image = _resize(image)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    clahe = _apply_clahe(gray)

    #thresh = _threshold(clahe)

    deskewed = _deskew(clahe)

    # Convert back to 3-channel for YOLO
    final = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2BGR)

    return final
