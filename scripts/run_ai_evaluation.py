from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT_DIR / "reports"
YOLO_METRICS_PATH = REPORTS_DIR / "yolo_metrics.json"
OCR_METRICS_PATH = REPORTS_DIR / "ocr_metrics.json"
CONFUSION_PATH = REPORTS_DIR / "confusion_matrix.png"
REPORT_PATH = REPORTS_DIR / "ai_evaluation.md"


def run_script(script_name: str) -> None:
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / script_name)],
        check=True,
        cwd=str(ROOT_DIR),
        env=env,
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def format_metric(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_report(yolo_metrics: dict[str, Any], ocr_metrics: dict[str, Any]) -> str:
    field_metrics = ocr_metrics.get("fields", {})
    ocr_lines = []
    for field_name in ("name", "dob", "aadhaar"):
        metrics = field_metrics.get(field_name, {})
        ocr_lines.append(
            f"- {field_name}: char_acc={format_metric(metrics.get('char_acc'))}, "
            f"word_acc={format_metric(metrics.get('word_acc'))}"
        )

    per_class = yolo_metrics.get("per_class_mAP50_95", {})
    worst_detection_class = yolo_metrics.get("worst_class")
    if not worst_detection_class and per_class:
        worst_detection_class = min(per_class, key=per_class.get)

    worst_ocr_field = None
    if field_metrics:
        worst_ocr_field = min(
            field_metrics,
            key=lambda field_name: field_metrics[field_name].get("char_acc", 0.0),
        )

    observation_lines = []
    if worst_detection_class:
        observation_lines.append(f"- Weakest detection class by mAP@50-95: {worst_detection_class}")
    else:
        observation_lines.append("- Weakest detection class could not be determined from the available metrics")
    if worst_ocr_field:
        observation_lines.append(f"- Weakest OCR field by character accuracy: {worst_ocr_field}")
    else:
        observation_lines.append("- Weakest OCR field could not be determined from the available metrics")
    observation_lines.append(
        "- OCR remains the likely bottleneck when field text quality is poor, while detection quality depends on box localization and class separation."
    )

    limitation_lines = [
        "- The OCR evaluation uses a small synthetic set to provide deterministic field-level ground truth.",
        "- The detection metrics depend on the current local dataset split and model checkpoint.",
        "- Real-world documents can vary more in blur, lighting, skew, language, and occlusion than this evaluation covers.",
    ]

    qr_module = (ocr_metrics.get("optional_modules") or {}).get("qr_validation", {})
    forgery_module = (ocr_metrics.get("optional_modules") or {}).get("forgery_detection", {})

    return "\n".join(
        [
            "# AI Evaluation Report",
            "",
            "## 1. YOLOv8 Detection",
            f"- mAP@50: {format_metric(yolo_metrics.get('mAP50'))}",
            f"- mAP@50-95: {format_metric(yolo_metrics.get('mAP50_95'))}",
            f"- Precision: {format_metric(yolo_metrics.get('precision'))}",
            f"- Recall: {format_metric(yolo_metrics.get('recall'))}",
            "",
            "## 2. OCR Performance (TRA)",
            *ocr_lines,
            "",
            "## 3. Confusion Matrix",
            f"- Image: `{CONFUSION_PATH.relative_to(ROOT_DIR)}`",
            "",
            "## 4. Observations",
            *observation_lines,
            "",
            "## 5. Limitations",
            *limitation_lines,
            "",
            "## 6. Optional Modules",
            f"- Forgery detection: {forgery_module.get('status', 'unavailable')} "
            f"({forgery_module.get('note', 'no note')})",
            f"- QR validation: {qr_module.get('status', 'unavailable')} "
            f"(success_rate={format_metric(qr_module.get('success_rate'))}; {qr_module.get('note', 'no note')})",
            "",
        ]
    )


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_script("evaluate_yolo.py")
    run_script("evaluate_ocr.py")
    run_script("generate_confusion.py")

    yolo_metrics = load_json(YOLO_METRICS_PATH)
    ocr_metrics = load_json(OCR_METRICS_PATH)
    REPORT_PATH.write_text(build_report(yolo_metrics, ocr_metrics), encoding="utf-8")
    print(f"saved {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
