import numpy as np
import pytest

from backend.app.services.ai import ocr


def test_preprocess_crop_for_aadhaar_returns_upscaled_grayscale(sample_color_image: np.ndarray) -> None:
    processed = ocr.preprocess_crop(sample_color_image, "aadhaar_number")

    assert processed.ndim == 2
    assert processed.shape == (64, 96)
    assert processed.dtype == np.uint8


def test_preprocess_crop_for_text_returns_binary_image(sample_color_image: np.ndarray) -> None:
    processed = ocr.preprocess_crop(sample_color_image, "name")

    assert processed.ndim == 2
    assert processed.shape == (64, 96)
    assert set(np.unique(processed)).issubset({0, 255})


def test_run_ocr_uses_digit_whitelist_for_aadhaar(monkeypatch: pytest.MonkeyPatch) -> None:
    observed = {}

    def fake_image_to_string(image, *, lang, config):
        observed["lang"] = lang
        observed["config"] = config
        return " 1234 5678 9012 \n"

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", fake_image_to_string)

    text = ocr.run_ocr(np.zeros((8, 8), dtype=np.uint8), "aadhaar_number")

    assert text == "1234 5678 9012"
    assert observed["lang"] == "eng"
    assert "tessedit_char_whitelist=0123456789" in observed["config"]
    assert "--psm 7" in observed["config"]


def test_run_ocr_uses_multilingual_config_for_text(monkeypatch: pytest.MonkeyPatch) -> None:
    observed = {}

    def fake_image_to_string(image, *, lang, config):
        observed["lang"] = lang
        observed["config"] = config
        return " Name: John Doe \nDOB: 01/01/2000 "

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", fake_image_to_string)

    text = ocr.run_ocr(np.zeros((8, 8), dtype=np.uint8), "name")

    assert text == "Name: John Doe \nDOB: 01/01/2000"
    assert observed["lang"] == "hin+eng"
    assert observed["config"] == "--oem 3 --psm 6"


def test_extract_aadhaar_normalizes_digits() -> None:
    assert ocr.extract_aadhaar("Aadhaar No: 1234 5678 9012") == "1234 5678 9012"


def test_extract_aadhaar_returns_none_for_invalid_length() -> None:
    assert ocr.extract_aadhaar("1234 5678") is None


def test_extract_fields_returns_raw_and_processed(
    monkeypatch: pytest.MonkeyPatch,
    sample_color_image: np.ndarray,
    sample_detections: list[dict[str, object]],
) -> None:
    observed = {"fields": [], "processed_inputs": None}

    def fake_imwrite(path, crop):
        return True

    def fake_preprocess_crop(crop, field_type=None):
        observed["fields"].append(("preprocess", field_type, crop.shape))
        return crop

    def fake_run_ocr(crop, field_type=None):
        mapping = {
            "name": "Name: John Doe",
            "aadhaar_number": "1234 5678 9012",
        }
        return mapping[field_type]

    def fake_postprocess(fields):
        observed["processed_inputs"] = fields.copy()
        return {"normalized": "ok"}

    monkeypatch.setattr(ocr.cv2, "imwrite", fake_imwrite)
    monkeypatch.setattr(ocr, "preprocess_crop", fake_preprocess_crop)
    monkeypatch.setattr(ocr, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(ocr, "postprocess", fake_postprocess)

    result = ocr.extract_fields(sample_color_image, sample_detections)

    assert result == {
        "raw": {
            "name": "Name: John Doe",
            "aadhaar_number": "1234 5678 9012",
        },
        "processed": {"normalized": "ok"},
    }
    assert observed["processed_inputs"] == result["raw"]
    assert [entry[1] for entry in observed["fields"]] == ["name", "aadhaar_number"]


def test_extract_fields_skips_empty_crops(
    monkeypatch: pytest.MonkeyPatch,
    sample_color_image: np.ndarray,
) -> None:
    detections = [{"class": "name", "bbox": [10, 10, 10, 10]}]
    preprocess_called = {"value": False}

    monkeypatch.setattr(ocr.cv2, "imwrite", lambda path, crop: True)
    monkeypatch.setattr(
        ocr,
        "preprocess_crop",
        lambda crop, field_type=None: preprocess_called.__setitem__("value", True),
    )
    monkeypatch.setattr(ocr, "postprocess", lambda fields: {})

    result = ocr.extract_fields(sample_color_image, detections)

    assert result == {"raw": {}, "processed": {}}
    assert preprocess_called["value"] is False
