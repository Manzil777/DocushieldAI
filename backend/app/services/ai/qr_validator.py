from __future__ import annotations

import base64
import binascii
import difflib
import re
import zlib
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
except Exception:  # pragma: no cover - fallback for missing native zbar
    pyzbar_decode = None


SAFE_QR_RESULT = {
    "qr_valid": False,
    "fields_match": False,
    "payload": {},
}


def preprocess_image(image: np.ndarray) -> list[np.ndarray]:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy.ndarray")
    if image.size == 0:
        raise ValueError("image array is empty")

    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] in (1, 3):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.shape[2] == 3 else image[:, :, 0]
    else:
        raise ValueError("image must be grayscale or BGR")

    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)

    height, width = gray.shape[:2]
    scale = 2 if min(height, width) < 600 else 1
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    equalized = cv2.equalizeHist(resized)
    thresholded = cv2.adaptiveThreshold(
        equalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    return [resized, equalized, thresholded]


def decode_qr_opencv(images: list[np.ndarray]) -> str | None:
    detector = cv2.QRCodeDetector()

    for candidate in images:
        data, _, _ = detector.detectAndDecode(candidate)
        if data:
            return data.strip()

        ok, decoded_info, _, _ = detector.detectAndDecodeMulti(candidate)
        if ok:
            for value in decoded_info:
                if value:
                    return value.strip()
    return None


def decode_qr_pyzbar(images: list[np.ndarray]) -> str | None:
    if pyzbar_decode is None:
        return None

    for candidate in images:
        decoded_items = pyzbar_decode(candidate)
        for item in decoded_items:
            try:
                return item.data.decode("utf-8").strip()
            except UnicodeDecodeError:
                continue
    return None


def _looks_like_xml(value: str) -> bool:
    stripped = value.lstrip()
    return stripped.startswith("<") and stripped.endswith(">")


def _maybe_base64_decode(value: str) -> bytes | None:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 8:
        return None
    padding = (-len(compact)) % 4
    compact += "=" * padding
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None


def parse_payload(value: str) -> dict[str, str] | None:
    candidates: list[str] = []
    raw = value.strip()
    if raw:
        candidates.append(raw)

    decoded = _maybe_base64_decode(raw)
    if decoded:
        for blob in (decoded,):
            try:
                candidates.append(blob.decode("utf-8"))
            except UnicodeDecodeError:
                pass
            try:
                candidates.append(zlib.decompress(blob).decode("utf-8"))
            except (zlib.error, UnicodeDecodeError):
                pass

    for candidate in candidates:
        if not _looks_like_xml(candidate):
            continue
        try:
            root = ET.fromstring(candidate)
        except ET.ParseError:
            continue

        payload = {
            "uid": _extract_xml_field(root, "uid"),
            "name": _extract_xml_field(root, "name"),
            "dob": _extract_xml_field(root, "dob"),
            "gender": _extract_xml_field(root, "gender"),
        }
        return {key: value for key, value in payload.items() if value}

    return None


def _extract_xml_field(root: ET.Element, field: str) -> str | None:
    field_aliases = {
        "uid": ("uid",),
        "name": ("name",),
        "dob": ("dob", "yob"),
        "gender": ("gender", "sex"),
    }
    aliases = field_aliases.get(field, (field,))

    for alias in aliases:
        if alias in root.attrib and root.attrib[alias]:
            return root.attrib[alias].strip()

    for alias in aliases:
        node = root.find(f".//*[@{alias}]")
        if node is not None and node.attrib.get(alias):
            return node.attrib[alias].strip()

        text_node = root.find(f".//{alias}")
        if text_node is not None and text_node.text:
            return text_node.text.strip()

    return None


def _normalize_uid(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def _normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value or None


def _normalize_gender(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().casefold()
    mapping = {
        "m": "male",
        "male": "male",
        "f": "female",
        "female": "female",
        "other": "other",
    }
    return mapping.get(value, value)


def _normalize_dob(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return value


def _extract_ocr_value(ocr_data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key in ocr_data and isinstance(ocr_data[key], str):
            return ocr_data[key]

    for key in keys:
        field = ocr_data.get(key)
        if isinstance(field, dict):
            normalized = field.get("normalized")
            raw = field.get("raw")
            if normalized:
                return str(normalized)
            if raw:
                return str(raw)
    return None


def compare_fields(qr_payload: dict[str, str], ocr_data: dict[str, Any]) -> bool:
    if not qr_payload or not ocr_data:
        return False

    comparisons: list[bool] = []

    qr_uid = _normalize_uid(qr_payload.get("uid"))
    ocr_uid = _normalize_uid(_extract_ocr_value(ocr_data, "uid", "aadhaar_number"))
    if qr_uid and ocr_uid:
        comparisons.append(qr_uid == ocr_uid)

    qr_dob = _normalize_dob(qr_payload.get("dob"))
    ocr_dob = _normalize_dob(_extract_ocr_value(ocr_data, "dob"))
    if qr_dob and ocr_dob:
        comparisons.append(qr_dob == ocr_dob)

    qr_name = _normalize_name(qr_payload.get("name"))
    ocr_name = _normalize_name(_extract_ocr_value(ocr_data, "name"))
    if qr_name and ocr_name:
        similarity = difflib.SequenceMatcher(None, qr_name, ocr_name).ratio()
        comparisons.append(similarity >= 0.85)

    qr_gender = _normalize_gender(qr_payload.get("gender"))
    ocr_gender = _normalize_gender(_extract_ocr_value(ocr_data, "gender"))
    if qr_gender and ocr_gender:
        comparisons.append(qr_gender == ocr_gender)

    return bool(comparisons) and all(comparisons)


def validate_qr(image: np.ndarray, ocr_data: dict) -> dict:
    try:
        processed_images = preprocess_image(image)
    except Exception:
        return SAFE_QR_RESULT.copy()

    decoded = decode_qr_opencv(processed_images)
    if not decoded:
        decoded = decode_qr_pyzbar(processed_images)
    if not decoded:
        return SAFE_QR_RESULT.copy()

    payload = parse_payload(decoded)
    if not payload:
        return SAFE_QR_RESULT.copy()

    return {
        "qr_valid": True,
        "fields_match": compare_fields(payload, ocr_data),
        "payload": payload,
    }
