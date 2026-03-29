from __future__ import annotations

import logging
from io import BytesIO
from uuid import uuid4

import cv2
import numpy as np
from pdf2image import convert_from_bytes
from PIL import Image

from app.services.storage_service import download_file, upload_file


logger = logging.getLogger(__name__)
MASK_FIELD_ALIASES = {
    "uid": "aadhaar_number",
    "aadhaar_number": "aadhaar_number",
    "dob": "dob",
    "address": "address",
    "name": "name",
    "gender": "gender",
}


def load_image_from_storage(path: str) -> np.ndarray:
    file_bytes = download_file(path)
    if path.lower().endswith(".pdf"):
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=1)
        if not pages:
            raise ValueError(f"PDF at storage path {path} contains no pages")
        rgb = np.array(pages[0].convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    image_array = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to decode image from storage path: {path}")
    return image


def apply_mask(image: np.ndarray, boxes: list[list[int]]) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("Cannot mask an empty image")

    masked = image.copy()
    height, width = masked.shape[:2]
    for box in boxes:
        if len(box) != 4:
            logger.debug("Skipping invalid box with %s coordinates: %s", len(box), box)
            continue

        x1, y1, x2, y2 = [int(coord) for coord in box]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(0, min(x2, width))
        y2 = max(0, min(y2, height))
        if x1 >= x2 or y1 >= y2:
            logger.debug("Skipping non-positive box after clamping: %s", box)
            continue

        cv2.rectangle(masked, (x1, y1), (x2, y2), (0, 0, 0), -1)

    return masked


def save_masked_image(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise ValueError("Failed to encode masked image as JPEG")

    storage_path = f"masked/images/{uuid4()}.jpg"
    upload_file(encoded.tobytes(), storage_path, content_type="image/jpeg")
    logger.info("Stored masked image at %s", storage_path)
    return storage_path


def generate_pdf(image: np.ndarray) -> str:
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    buffer = BytesIO()
    pil_image.save(buffer, format="PDF", resolution=100.0)
    pdf_bytes = buffer.getvalue()
    if not pdf_bytes:
        raise ValueError("Failed to generate PDF from masked image")

    storage_path = f"masked/pdfs/{uuid4()}.pdf"
    upload_file(pdf_bytes, storage_path, content_type="application/pdf")
    logger.info("Stored masked PDF at %s", storage_path)
    return storage_path


def collect_mask_boxes(
    bounding_boxes: dict | None,
    requested_fields: list[str],
) -> tuple[list[list[int]], dict[str, list[list[int]]]]:
    if not bounding_boxes:
        raise ValueError("No bounding boxes available for this document")
    if not requested_fields:
        raise ValueError("mask_fields cannot be empty")

    normalized_fields: list[str] = []
    for field in requested_fields:
        normalized = MASK_FIELD_ALIASES.get(field.strip().lower())
        if normalized:
            normalized_fields.append(normalized)

    filtered_boxes: list[list[int]] = []
    boxes_by_field: dict[str, list[list[int]]] = {}
    for field_name in dict.fromkeys(normalized_fields):
        raw_boxes = bounding_boxes.get(field_name, [])
        if not isinstance(raw_boxes, list):
            continue

        valid_boxes = [box for box in raw_boxes if isinstance(box, list) and len(box) == 4]
        if not valid_boxes:
            continue

        boxes_by_field[field_name] = valid_boxes
        filtered_boxes.extend(valid_boxes)

    if not filtered_boxes:
        raise ValueError("No bounding boxes found for requested fields")

    return filtered_boxes, boxes_by_field


def create_masked_assets(source_path: str, boxes: list[list[int]]) -> tuple[str, str]:
    image = load_image_from_storage(source_path)
    masked_image = apply_mask(image, boxes)
    masked_image_path = save_masked_image(masked_image)
    masked_pdf_path = generate_pdf(masked_image)
    return masked_image_path, masked_pdf_path
