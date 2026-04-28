from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT_DIR / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ai import ocr as ocr_service  # noqa: E402
from app.services.ai.postprocessor import postprocess  # noqa: E402


REPORTS_DIR = ROOT_DIR / "reports"
OCR_EVAL_DIR = ROOT_DIR / "data" / "aadhaar" / "ocr_eval"
OCR_IMAGES_DIR = OCR_EVAL_DIR / "images"
SAMPLES_PATH = OCR_EVAL_DIR / "samples.json"
FIELD_TO_PIPELINE_KEY = {
    "name": "name",
    "dob": "dob",
    "aadhaar": "aadhaar_number",
}
SYNTHETIC_SAMPLES = [
    {"name": "Ravi Kumar", "dob": "01/01/2000", "aadhaar": "123456789012"},
    {"name": "Anita Sharma", "dob": "05/07/1998", "aadhaar": "234567890123"},
    {"name": "Suresh Patel", "dob": "12/11/1989", "aadhaar": "345678901234"},
    {"name": "Pooja Singh", "dob": "23/03/1995", "aadhaar": "456789012345"},
    {"name": "Mohit Verma", "dob": "14/08/1992", "aadhaar": "567890123456"},
    {"name": "Neha Gupta", "dob": "30/09/1999", "aadhaar": "678901234567"},
    {"name": "Aman Joshi", "dob": "17/04/1991", "aadhaar": "789012345678"},
    {"name": "Kiran Das", "dob": "28/12/1987", "aadhaar": "890123456789"},
    {"name": "Priya Nair", "dob": "09/06/1996", "aadhaar": "901234567890"},
    {"name": "Deepak Rao", "dob": "19/10/1993", "aadhaar": "112233445566"},
]


def _normalize_for_field(field_name: str, value: str) -> str:
    processed = postprocess({FIELD_TO_PIPELINE_KEY[field_name]: value})
    processed_value = processed.get(FIELD_TO_PIPELINE_KEY[field_name], {})
    normalized = processed_value.get("normalized")
    if normalized is None:
        return value.strip()
    return str(normalized).strip()


def ensure_ocr_samples() -> list[dict[str, Any]]:
    OCR_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []

    for index, row in enumerate(SYNTHETIC_SAMPLES, start=1):
        image_path = OCR_IMAGES_DIR / f"sample_{index:02d}.png"
        image = np.full((260, 900, 3), 255, dtype=np.uint8)
        cv2.putText(image, row["name"].upper(), (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        cv2.putText(image, row["dob"], (30, 145), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        aadhaar_formatted = f"{row['aadhaar'][0:4]} {row['aadhaar'][4:8]} {row['aadhaar'][8:12]}"
        cv2.putText(
            image,
            aadhaar_formatted,
            (30, 220),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 0),
            2,
        )
        cv2.imwrite(str(image_path), image)

        samples.append(
            {
                "image": str(image_path.relative_to(ROOT_DIR)),
                "ground_truth": {
                    "name": _normalize_for_field("name", row["name"]),
                    "dob": _normalize_for_field("dob", row["dob"]),
                    "aadhaar": _normalize_for_field("aadhaar", row["aadhaar"]),
                },
                "detections": [
                    {"class": "name", "bbox": [20, 25, 860, 90]},
                    {"class": "dob", "bbox": [20, 100, 560, 165]},
                    {"class": "aadhaar_number", "bbox": [20, 175, 860, 240]},
                ],
            }
        )

    SAMPLES_PATH.write_text(json.dumps(samples, indent=2), encoding="utf-8")
    return samples


def safe_extract_fields(image: np.ndarray, detections: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return ocr_service.extract_fields(image, detections)
    except pytesseract.TesseractError:
        raw_results: dict[str, str] = {}
        for detection in detections:
            field_name = detection["class"]
            x1, y1, x2, y2 = [int(value) for value in detection["bbox"]]
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            processed_crop = ocr_service.preprocess_crop(crop, field_name)
            if field_name == "aadhaar_number":
                config = r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"
            else:
                config = r"--oem 3 --psm 6"
            text = pytesseract.image_to_string(processed_crop, lang="eng", config=config).strip()
            raw_results[field_name] = text

        return {
            "raw": raw_results,
            "processed": postprocess(raw_results),
            "forgery": {"note": "not evaluated in OCR fallback"},
            "qr_validation": {"qr_valid": False, "fields_match": False, "payload": {}},
        }


def edit_distance(left: list[str], right: list[str]) -> int:
    rows = len(left) + 1
    cols = len(right) + 1
    dp = [[0] * cols for _ in range(rows)]

    for row in range(rows):
        dp[row][0] = row
    for col in range(cols):
        dp[0][col] = col

    for row in range(1, rows):
        for col in range(1, cols):
            substitution_cost = 0 if left[row - 1] == right[col - 1] else 1
            dp[row][col] = min(
                dp[row - 1][col] + 1,
                dp[row][col - 1] + 1,
                dp[row - 1][col - 1] + substitution_cost,
            )

    return dp[-1][-1]


def char_accuracy(expected: str, predicted: str) -> float:
    if not expected and not predicted:
        return 1.0
    distance = edit_distance(list(expected), list(predicted))
    return max(0.0, 1 - (distance / max(len(expected), 1)))


def word_accuracy(expected: str, predicted: str) -> float:
    expected_words = expected.split()
    predicted_words = predicted.split()
    if not expected_words and not predicted_words:
        return 1.0
    distance = edit_distance(expected_words, predicted_words)
    return max(0.0, 1 - (distance / max(len(expected_words), 1)))


def extract_prediction(result: dict[str, Any], field_name: str) -> str:
    pipeline_key = FIELD_TO_PIPELINE_KEY[field_name]
    processed_entry = (result.get("processed") or {}).get(pipeline_key, {})
    normalized = processed_entry.get("normalized")
    if normalized:
        return str(normalized).strip()

    raw_entry = (result.get("raw") or {}).get(pipeline_key, "")
    return str(raw_entry).strip()


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OCR_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = REPORTS_DIR / "ocr_metrics.json"

    samples = ensure_ocr_samples()
    aggregated: dict[str, dict[str, list[float]]] = {
        "name": {"char": [], "word": []},
        "dob": {"char": [], "word": []},
        "aadhaar": {"char": [], "word": []},
    }
    per_sample: list[dict[str, Any]] = []
    qr_results: list[int] = []

    for sample in samples:
        image_path = ROOT_DIR / sample["image"]
        image = cv2.imread(str(image_path))
        if image is None:
            continue

        result = safe_extract_fields(image, sample["detections"])
        qr_results.append(1 if (result.get("qr_validation") or {}).get("qr_valid") else 0)

        sample_result = {
            "image": sample["image"],
            "predictions": {},
            "ground_truth": sample["ground_truth"],
        }

        for field_name, ground_truth in sample["ground_truth"].items():
            prediction = extract_prediction(result, field_name)
            sample_result["predictions"][field_name] = prediction
            aggregated[field_name]["char"].append(char_accuracy(ground_truth, prediction))
            aggregated[field_name]["word"].append(word_accuracy(ground_truth, prediction))

        per_sample.append(sample_result)

    field_metrics: dict[str, dict[str, float]] = {}
    for field_name, values in aggregated.items():
        char_scores = values["char"]
        word_scores = values["word"]
        field_metrics[field_name] = {
            "char_acc": round(sum(char_scores) / len(char_scores), 4) if char_scores else 0.0,
            "word_acc": round(sum(word_scores) / len(word_scores), 4) if word_scores else 0.0,
        }

    payload = {
        "status": "ok",
        "sample_count": len(per_sample),
        "samples_path": str(SAMPLES_PATH.relative_to(ROOT_DIR)),
        "fields": field_metrics,
        "per_sample": per_sample,
        "optional_modules": {
            "forgery_detection": {
                "status": "not_evaluated",
                "note": "No forgery ground truth is included in this lightweight OCR evaluation.",
            },
            "qr_validation": {
                "status": "ok",
                "success_rate": round(sum(qr_results) / len(qr_results), 4) if qr_results else 0.0,
                "note": "Synthetic OCR samples do not contain QR codes, so this is expected to be low.",
            },
        },
    }

    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
