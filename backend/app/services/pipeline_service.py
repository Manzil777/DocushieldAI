from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from app.services.ai.ocr import extract_fields
from app.services.ai.preprocessing import _apply_clahe, _deskew, _is_blurry, _resize


MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "best.onnx"
MODEL_CLASS_MAP = {
    "AADHAR_NUMBER": "aadhaar_number",
    "DATE_OF_BIRTH": "dob",
    "GENDER": "gender",
    "NAME": "name",
    "ADDRESS": "address",
}


def _preprocess_image(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("Input image is empty")

    resized = _resize(image, size=(640, 640))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    clahe = _apply_clahe(gray)
    deskewed = _deskew(clahe)
    return cv2.cvtColor(deskewed, cv2.COLOR_GRAY2BGR)


@lru_cache(maxsize=1)
def _load_detector() -> YOLO:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Missing ONNX detector model at {MODEL_PATH}")
    return YOLO(str(MODEL_PATH))


def _detect_fields(image: np.ndarray) -> list[dict]:
    model = _load_detector()
    result = model.predict(source=image, imgsz=512, conf=0.25, iou=0.45, device="cpu", verbose=False)[0]
    detections: list[dict] = []
    if result.boxes is None:
        return detections

    boxes = result.boxes.xyxy.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)
    for box, class_id in zip(boxes, classes, strict=False):
        raw_name = model.names.get(int(class_id), str(class_id))
        mapped_name = MODEL_CLASS_MAP.get(str(raw_name).upper())
        if not mapped_name:
            continue
        detections.append(
            {
                "class": mapped_name,
                "bbox": [float(coord) for coord in box.tolist()],
            }
        )
    return detections


def run_pipeline(image: np.ndarray) -> dict:
    processed_image = _preprocess_image(image)
    detections = _detect_fields(processed_image)
    ocr_output = extract_fields(processed_image, detections)
    bounding_boxes: dict[str, list[list[int]]] = {}

    for detection in detections:
        field_name = detection["class"]
        box = [int(round(coord)) for coord in detection["bbox"]]
        bounding_boxes.setdefault(field_name, []).append(box)

    return {
        "fields": ocr_output.get("processed", {}),
        "bounding_boxes": bounding_boxes,
        "forgery": ocr_output.get("forgery", {}),
        "qr": ocr_output.get("qr_validation", {}),
    }
