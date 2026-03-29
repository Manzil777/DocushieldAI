from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.app.services.ai import preprocessing


def test_load_input_reads_png(sample_png_path: Path, sample_color_image: np.ndarray) -> None:
    loaded = preprocessing._load_input(str(sample_png_path))

    assert loaded.shape == sample_color_image.shape
    assert loaded.dtype == np.uint8


def test_load_input_rejects_unsupported_extension(tmp_path: Path) -> None:
    bad_file = tmp_path / "sample.txt"
    bad_file.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        preprocessing._load_input(str(bad_file))


def test_load_input_raises_for_unreadable_image(tmp_path: Path) -> None:
    bad_image = tmp_path / "bad.png"
    bad_image.write_bytes(b"not-a-real-image")

    with pytest.raises(ValueError, match="Failed to read image file"):
        preprocessing._load_input(str(bad_image))


def test_load_input_reads_pdf_first_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_page = np.full((10, 12, 3), 180, dtype=np.uint8)

    monkeypatch.setattr(preprocessing, "convert_from_path", lambda *args, **kwargs: [fake_page])

    loaded = preprocessing._load_input(str(pdf_path))

    assert loaded.shape == (10, 12, 3)
    assert loaded.dtype == np.uint8


def test_load_input_raises_for_empty_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(preprocessing, "convert_from_path", lambda *args, **kwargs: [])

    with pytest.raises(ValueError, match="PDF has no pages"):
        preprocessing._load_input(str(pdf_path))


def test_resize_outputs_requested_shape(sample_color_image: np.ndarray) -> None:
    resized = preprocessing._resize(sample_color_image)

    assert resized.shape == (640, 640, 3)


def test_apply_clahe_preserves_grayscale_shape(sample_gray_image: np.ndarray) -> None:
    clahe = preprocessing._apply_clahe(sample_gray_image)

    assert clahe.shape == sample_gray_image.shape
    assert clahe.ndim == 2
    assert clahe.dtype == np.uint8


def test_threshold_returns_binary_values(sample_gray_image: np.ndarray) -> None:
    thresholded = preprocessing._threshold(sample_gray_image)

    assert thresholded.shape == sample_gray_image.shape
    assert set(np.unique(thresholded)).issubset({0, 255})


def test_deskew_returns_same_shape_for_text_like_input(sample_gray_image: np.ndarray) -> None:
    deskewed = preprocessing._deskew(sample_gray_image)

    assert deskewed.shape == sample_gray_image.shape
    assert deskewed.dtype == sample_gray_image.dtype


def test_deskew_handles_blank_image_without_crashing() -> None:
    blank = np.zeros((40, 50), dtype=np.uint8)

    deskewed = preprocessing._deskew(blank)

    assert np.array_equal(deskewed, blank)


def test_is_blurry_detects_uniform_image(blurry_color_image: np.ndarray) -> None:
    assert bool(preprocessing._is_blurry(blurry_color_image)) is True


def test_is_blurry_rejects_sharp_pattern(sample_color_image: np.ndarray) -> None:
    assert bool(preprocessing._is_blurry(sample_color_image)) is False


def test_preprocess_document_returns_three_channel_image(sample_png_path: Path) -> None:
    processed = preprocessing.preprocess_document(str(sample_png_path))

    assert processed.shape == (640, 640, 3)
    assert processed.dtype == np.uint8
    assert np.array_equal(processed[:, :, 0], processed[:, :, 1])
    assert np.array_equal(processed[:, :, 1], processed[:, :, 2])


def test_preprocess_document_raises_for_blurry_input(
    monkeypatch: pytest.MonkeyPatch,
    sample_png_path: Path,
) -> None:
    monkeypatch.setattr(preprocessing, "_is_blurry", lambda image: True)

    with pytest.raises(ValueError, match="too blurry"):
        preprocessing.preprocess_document(str(sample_png_path))
