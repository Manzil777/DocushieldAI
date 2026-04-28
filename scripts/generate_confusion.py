from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import cv2
import matplotlib.pyplot as plt
import numpy as np
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT_DIR / "reports"
MODEL_PATH = ROOT_DIR / "backend" / "models" / "best.pt"
DATASET_DIR = ROOT_DIR / "data" / "aadhaar"
DATA_YAML_PATH = DATASET_DIR / "data.yaml"
TEST_IMAGES_DIR = DATASET_DIR / "test" / "images"
TEST_LABELS_DIR = DATASET_DIR / "test" / "labels"
BACKGROUND_LABEL = "background"


def ensure_dataset_yaml() -> Path:
    if DATA_YAML_PATH.exists():
        return DATA_YAML_PATH

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    DATA_YAML_PATH.write_text(
        "\n".join(
            [
                f"path: {DATASET_DIR}",
                "train: train/images",
                "val: valid/images",
                "test: test/images",
                "names:",
                "  0: AADHAR_NUMBER",
                "  1: DATE_OF_BIRTH",
                "  2: GENDER",
                "  3: NAME",
                "  4: ADDRESS",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return DATA_YAML_PATH


def convert_yolo_box_to_xyxy(box: list[float], image_width: int, image_height: int) -> list[float]:
    x_center, y_center, width, height = box
    x1 = (x_center - (width / 2)) * image_width
    y1 = (y_center - (height / 2)) * image_height
    x2 = (x_center + (width / 2)) * image_width
    y2 = (y_center + (height / 2)) * image_height
    return [x1, y1, x2, y2]


def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    intersection_width = max(0.0, x2 - x1)
    intersection_height = max(0.0, y2 - y1)
    intersection = intersection_width * intersection_height
    if intersection == 0:
        return 0.0

    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def load_ground_truth(label_path: Path, image_width: int, image_height: int) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    if not label_path.exists():
        return boxes

    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        class_id = int(float(parts[0]))
        coords = [float(value) for value in parts[1:]]
        boxes.append({"class_id": class_id, "bbox": convert_yolo_box_to_xyxy(coords, image_width, image_height)})
    return boxes


def build_confusion_with_fallback(actual_labels: list[str], predicted_labels: list[str], labels: list[str]) -> np.ndarray:
    try:
        from sklearn.metrics import confusion_matrix

        return confusion_matrix(actual_labels, predicted_labels, labels=labels)
    except Exception:
        index_by_label = {label: index for index, label in enumerate(labels)}
        matrix = np.zeros((len(labels), len(labels)), dtype=int)
        for actual, predicted in zip(actual_labels, predicted_labels, strict=False):
            matrix[index_by_label[actual], index_by_label[predicted]] += 1
        return matrix


def save_placeholder_figure(output_path: Path, message: str) -> None:
    fig, axis = plt.subplots(figsize=(6, 4))
    axis.axis("off")
    axis.text(0.5, 0.5, message, ha="center", va="center", wrap=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    confusion_path = REPORTS_DIR / "confusion_matrix.png"

    try:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Missing YOLO model at {MODEL_PATH}")

        ensure_dataset_yaml()
        model = YOLO(str(MODEL_PATH))
        class_names = {int(class_id): str(class_name) for class_id, class_name in model.names.items()}
        labels = [class_names[index] for index in sorted(class_names)] + [BACKGROUND_LABEL]
        actual_labels: list[str] = []
        predicted_labels: list[str] = []

        image_paths = sorted(TEST_IMAGES_DIR.glob("*"))[:100]
        if not image_paths:
            save_placeholder_figure(confusion_path, "No test images were found for confusion matrix generation.")
            print(f"saved {confusion_path}")
            return 0

        for image_path in image_paths:
            image = cv2.imread(str(image_path))
            if image is None:
                continue

            height, width = image.shape[:2]
            label_path = TEST_LABELS_DIR / f"{image_path.stem}.txt"
            ground_truth_boxes = load_ground_truth(label_path, width, height)
            prediction_result = model.predict(source=str(image_path), imgsz=512, conf=0.25, iou=0.45, device="cpu", verbose=False)[0]

            predicted_boxes: list[dict[str, Any]] = []
            if prediction_result.boxes is not None:
                for xyxy, class_id in zip(
                    prediction_result.boxes.xyxy.cpu().numpy(),
                    prediction_result.boxes.cls.cpu().numpy().astype(int),
                    strict=False,
                ):
                    predicted_boxes.append({"class_id": int(class_id), "bbox": [float(value) for value in xyxy.tolist()]})

            used_prediction_indices: set[int] = set()
            for gt_box in ground_truth_boxes:
                best_match_index = None
                best_iou = 0.0
                for prediction_index, predicted_box in enumerate(predicted_boxes):
                    if prediction_index in used_prediction_indices:
                        continue
                    iou = compute_iou(gt_box["bbox"], predicted_box["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_match_index = prediction_index

                actual_labels.append(class_names.get(gt_box["class_id"], str(gt_box["class_id"])))
                if best_match_index is None or best_iou < 0.1:
                    predicted_labels.append(BACKGROUND_LABEL)
                    continue

                used_prediction_indices.add(best_match_index)
                predicted_class_id = predicted_boxes[best_match_index]["class_id"]
                predicted_labels.append(class_names.get(predicted_class_id, str(predicted_class_id)))

            for prediction_index, predicted_box in enumerate(predicted_boxes):
                if prediction_index in used_prediction_indices:
                    continue
                actual_labels.append(BACKGROUND_LABEL)
                predicted_labels.append(class_names.get(predicted_box["class_id"], str(predicted_box["class_id"])))

        if not actual_labels:
            save_placeholder_figure(confusion_path, "No matched predictions were available for confusion matrix generation.")
            print(f"saved {confusion_path}")
            return 0

        matrix = build_confusion_with_fallback(actual_labels, predicted_labels, labels)
        fig, axis = plt.subplots(figsize=(8, 6))
        image = axis.imshow(matrix, cmap="Blues")
        axis.set_xticks(range(len(labels)))
        axis.set_yticks(range(len(labels)))
        axis.set_xticklabels(labels, rotation=45, ha="right")
        axis.set_yticklabels(labels)
        axis.set_xlabel("Predicted")
        axis.set_ylabel("Actual")
        axis.set_title("Confusion Matrix")

        for row in range(matrix.shape[0]):
            for col in range(matrix.shape[1]):
                axis.text(col, row, str(matrix[row, col]), ha="center", va="center", color="black")

        fig.colorbar(image, ax=axis)
        fig.tight_layout()
        fig.savefig(confusion_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        save_placeholder_figure(confusion_path, f"Confusion matrix generation failed: {exc}")

    print(f"saved {confusion_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
