from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT_DIR / "reports"
MODEL_PATH = ROOT_DIR / "backend" / "models" / "best.pt"
DATASET_DIR = ROOT_DIR / "data" / "aadhaar"
DATA_YAML_PATH = DATASET_DIR / "data.yaml"
DEFAULT_CLASS_NAMES = {
    0: "AADHAR_NUMBER",
    1: "DATE_OF_BIRTH",
    2: "GENDER",
    3: "NAME",
    4: "ADDRESS",
}


def ensure_dataset_yaml() -> Path:
    if DATA_YAML_PATH.exists():
        return DATA_YAML_PATH

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    yaml_lines = [
        f"path: {DATASET_DIR}",
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "names:",
    ]
    for class_id, class_name in DEFAULT_CLASS_NAMES.items():
        yaml_lines.append(f"  {class_id}: {class_name}")
    DATA_YAML_PATH.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    return DATA_YAML_PATH


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = REPORTS_DIR / "yolo_metrics.json"

    try:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Missing YOLO model at {MODEL_PATH}")

        data_yaml_path = ensure_dataset_yaml()
        model = YOLO(str(MODEL_PATH))
        results = model.val(
            data=str(data_yaml_path),
            split="test",
            imgsz=512,
            device="cpu",
            workers=0,
            plots=False,
            verbose=False,
        )

        class_names = {
            int(class_id): str(class_name)
            for class_id, class_name in (model.names or DEFAULT_CLASS_NAMES).items()
        }
        per_class_map5095 = {
            class_names[index]: round(float(score), 4)
            for index, score in enumerate(getattr(results.box, "maps", []))
            if index in class_names
        }
        worst_class = None
        if per_class_map5095:
            worst_class = min(per_class_map5095, key=per_class_map5095.get)

        payload = {
            "status": "ok",
            "model_path": str(MODEL_PATH.relative_to(ROOT_DIR)),
            "dataset_yaml": str(data_yaml_path.relative_to(ROOT_DIR)),
            "split": "test",
            "mAP50": to_float(round(results.box.map50, 4)),
            "mAP50_95": to_float(round(results.box.map, 4)),
            "precision": to_float(round(results.box.mp, 4)),
            "recall": to_float(round(results.box.mr, 4)),
            "per_class_mAP50_95": per_class_map5095,
            "worst_class": worst_class,
            "notes": [],
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "model_path": str(MODEL_PATH.relative_to(ROOT_DIR)),
            "dataset_yaml": str(DATA_YAML_PATH.relative_to(ROOT_DIR)),
            "split": "test",
            "mAP50": None,
            "mAP50_95": None,
            "precision": None,
            "recall": None,
            "per_class_mAP50_95": {},
            "worst_class": None,
            "notes": [f"YOLO evaluation failed: {exc}"],
        }

    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
