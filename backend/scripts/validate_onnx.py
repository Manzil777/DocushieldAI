from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ULTRALYTICS_CONFIG_DIR", str(REPO_ROOT / ".ultralytics"))
os.environ.setdefault("XDG_CONFIG_HOME", str(REPO_ROOT / ".config"))

import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox
from ultralytics.utils.nms import TorchNMS
from ultralytics.utils.ops import scale_boxes

PT_MODEL_PATH = REPO_ROOT / "backend/models/best.pt"
ONNX_MODEL_PATH = REPO_ROOT / "backend/models/best.onnx"
IMAGE_ROOT = REPO_ROOT / "data/aadhaar"
DEFAULT_IMAGE_LIMIT = 10
IMG_SIZE = 512
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
MAP_IOU_THRESHOLD = 0.5
OPS_ET = 12


@dataclass
class DetectionResult:
    boxes: np.ndarray
    scores: np.ndarray
    classes: np.ndarray


@dataclass
class BenchmarkResult:
    average_ms: float
    durations_ms: list[float]


@dataclass
class PreparedImage:
    path: Path
    rgb: np.ndarray
    resized: np.ndarray
    tensor: np.ndarray
    original_shape: tuple[int, int]


def export_to_onnx(pt_model_path: Path, onnx_model_path: Path) -> Path:
    if not pt_model_path.exists():
        raise FileNotFoundError(f"Missing PyTorch model: {pt_model_path}")

    model = YOLO(str(pt_model_path))
    exported_path = Path(
        model.export(
            format="onnx",
            opset=OPS_ET,
            dynamic=True,
            imgsz=IMG_SIZE,
            simplify=False,
        )
    )
    if not exported_path.exists():
        raise FileNotFoundError(f"ONNX export did not create a file: {exported_path}")
    if exported_path.resolve() != onnx_model_path.resolve():
        exported_path.replace(onnx_model_path)
    return onnx_model_path


def discover_test_images(image_root: Path, limit: int = DEFAULT_IMAGE_LIMIT) -> list[Path]:
    candidates = sorted(
        path
        for ext in ("*.jpg", "*.jpeg", "*.png")
        for path in image_root.rglob(ext)
    )
    if len(candidates) < limit:
        raise FileNotFoundError(
            f"Expected at least {limit} images under {image_root}, found {len(candidates)}."
        )
    return candidates[:limit]


def load_models(pt_model_path: Path, onnx_model_path: Path) -> tuple[YOLO, ort.InferenceSession]:
    if not pt_model_path.exists():
        raise FileNotFoundError(f"Missing PyTorch model: {pt_model_path}")
    if not onnx_model_path.exists():
        raise FileNotFoundError(f"Missing ONNX model: {onnx_model_path}")

    pytorch_model = YOLO(str(pt_model_path))
    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 4
    session_options.inter_op_num_threads = 1
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    onnx_session = ort.InferenceSession(
        str(onnx_model_path),
        sess_options=session_options,
        providers=["CPUExecutionProvider"],
    )
    return pytorch_model, onnx_session


def prepare_image(image_path: Path) -> PreparedImage:
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise ValueError(f"Failed to read image: {image_path}")

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    original_shape = rgb.shape[:2]
    letterbox = LetterBox(new_shape=(IMG_SIZE, IMG_SIZE), auto=False, stride=32)
    resized = letterbox(image=rgb)

    tensor = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
    tensor = np.expand_dims(np.ascontiguousarray(tensor), axis=0)
    return PreparedImage(
        path=image_path,
        rgb=rgb,
        resized=resized,
        tensor=tensor,
        original_shape=original_shape,
    )


def prepare_images(image_paths: Iterable[Path]) -> list[PreparedImage]:
    return [prepare_image(image_path) for image_path in image_paths]


def run_pytorch_inference(model: YOLO, image_path: Path | PreparedImage) -> DetectionResult:
    source = image_path.rgb if isinstance(image_path, PreparedImage) else str(image_path)
    result = model.predict(
        source=source,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        iou=IOU_THRESHOLD,
        device="cpu",
        verbose=False,
    )[0]

    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else np.empty((0, 4), dtype=np.float32)
    scores = result.boxes.conf.cpu().numpy() if result.boxes is not None else np.empty((0,), dtype=np.float32)
    classes = result.boxes.cls.cpu().numpy().astype(np.int64) if result.boxes is not None else np.empty((0,), dtype=np.int64)
    return DetectionResult(boxes=boxes, scores=scores, classes=classes)


def run_onnx_inference(session: ort.InferenceSession, image_path: Path | PreparedImage) -> DetectionResult:
    prepared = image_path if isinstance(image_path, PreparedImage) else prepare_image(image_path)
    input_name = session.get_inputs()[0].name
    raw_output = session.run(None, {input_name: prepared.tensor})[0]

    predictions = torch.from_numpy(raw_output)
    if predictions.ndim == 3:
        predictions = predictions.permute(0, 2, 1)
    predictions = predictions[0]

    boxes_xywh = predictions[:, :4]
    class_scores = predictions[:, 4:]
    confidences, classes = class_scores.max(dim=1)
    mask = confidences > CONF_THRESHOLD

    boxes_xywh = boxes_xywh[mask]
    confidences = confidences[mask]
    classes = classes[mask]

    if boxes_xywh.numel() == 0:
        return DetectionResult(
            boxes=np.empty((0, 4), dtype=np.float32),
            scores=np.empty((0,), dtype=np.float32),
            classes=np.empty((0,), dtype=np.int64),
        )

    boxes_xyxy = torch.empty_like(boxes_xywh)
    boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
    boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
    boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
    boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

    kept_indices: list[torch.Tensor] = []
    for class_id in classes.unique():
        class_mask = torch.where(classes == class_id)[0]
        keep = TorchNMS.nms(boxes_xyxy[class_mask], confidences[class_mask], IOU_THRESHOLD)
        kept_indices.append(class_mask[keep])

    keep = torch.cat(kept_indices)
    keep = keep[confidences[keep].argsort(descending=True)]

    boxes_xyxy = boxes_xyxy[keep]
    confidences = confidences[keep]
    classes = classes[keep]
    boxes_xyxy = scale_boxes(prepared.resized.shape[:2], boxes_xyxy, prepared.original_shape)

    return DetectionResult(
        boxes=boxes_xyxy.cpu().numpy(),
        scores=confidences.cpu().numpy(),
        classes=classes.cpu().numpy().astype(np.int64),
    )


def load_ground_truth(image_path: Path | PreparedImage) -> DetectionResult:
    path = image_path.path if isinstance(image_path, PreparedImage) else image_path
    label_path = path.parent.parent / "labels" / f"{path.stem}.txt"
    if isinstance(image_path, PreparedImage):
        height, width = image_path.original_shape
    else:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Failed to read image for labels: {path}")
        height, width = image.shape[:2]

    boxes: list[list[float]] = []
    scores: list[float] = []
    classes: list[int] = []
    if label_path.exists():
        for line in label_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            class_id, x_center, y_center, box_width, box_height = map(float, line.split())
            x1 = (x_center - box_width / 2) * width
            y1 = (y_center - box_height / 2) * height
            x2 = (x_center + box_width / 2) * width
            y2 = (y_center + box_height / 2) * height
            boxes.append([x1, y1, x2, y2])
            scores.append(1.0)
            classes.append(int(class_id))

    return DetectionResult(
        boxes=np.asarray(boxes, dtype=np.float32).reshape(-1, 4) if boxes else np.empty((0, 4), dtype=np.float32),
        scores=np.asarray(scores, dtype=np.float32),
        classes=np.asarray(classes, dtype=np.int64),
    )


def compute_iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
    x1 = max(float(box_a[0]), float(box_b[0]))
    y1 = max(float(box_a[1]), float(box_b[1]))
    x2 = min(float(box_a[2]), float(box_b[2]))
    y2 = min(float(box_a[3]), float(box_b[3]))
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    intersection = inter_w * inter_h
    area_a = max(0.0, float(box_a[2] - box_a[0])) * max(0.0, float(box_a[3] - box_a[1]))
    area_b = max(0.0, float(box_b[2] - box_b[0])) * max(0.0, float(box_b[3] - box_b[1]))
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def compare_outputs(
    pytorch_results: dict[Path, DetectionResult],
    onnx_results: dict[Path, DetectionResult],
) -> dict[str, float]:
    bbox_diffs: list[float] = []
    score_diffs: list[float] = []
    class_matches = 0
    match_count = 0
    unmatched = 0

    for image_path, pt_result in pytorch_results.items():
        onnx_result = onnx_results[image_path]
        used_onnx: set[int] = set()
        for pt_index, pt_box in enumerate(pt_result.boxes):
            best_idx = None
            best_iou = -1.0
            for onnx_index, onnx_box in enumerate(onnx_result.boxes):
                if onnx_index in used_onnx:
                    continue
                iou = compute_iou(pt_box, onnx_box)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = onnx_index
            if best_idx is None:
                unmatched += 1
                continue
            used_onnx.add(best_idx)
            match_count += 1
            bbox_diffs.append(1.0 - max(best_iou, 0.0))
            score_diffs.append(abs(float(pt_result.scores[pt_index]) - float(onnx_result.scores[best_idx])))
            if int(pt_result.classes[pt_index]) == int(onnx_result.classes[best_idx]):
                class_matches += 1

        unmatched += max(0, len(onnx_result.boxes) - len(used_onnx))

    return {
        "mean_bbox_difference": float(np.mean(bbox_diffs)) if bbox_diffs else 0.0,
        "mean_confidence_difference": float(np.mean(score_diffs)) if score_diffs else 0.0,
        "class_match_rate": class_matches / match_count if match_count else 1.0,
        "matched_predictions": float(match_count),
        "unmatched_predictions": float(unmatched),
    }


def compute_average_precision(recall: np.ndarray, precision: np.ndarray) -> float:
    mrec = np.concatenate(([0.0], recall, [1.0]))
    mpre = np.concatenate(([0.0], precision, [0.0]))
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    indices = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[indices + 1] - mrec[indices]) * mpre[indices + 1]))


def evaluate_map(
    predictions: dict[Path, DetectionResult],
    ground_truth: dict[Path, DetectionResult],
    iou_threshold: float = MAP_IOU_THRESHOLD,
) -> float:
    class_ids = sorted(
        {
            int(class_id)
            for result in ground_truth.values()
            for class_id in result.classes.tolist()
        }
    )
    if not class_ids:
        return 0.0

    ap_values: list[float] = []
    for class_id in class_ids:
        entries: list[tuple[float, bool]] = []
        total_gt = 0
        used_matches: dict[Path, set[int]] = {}

        for image_path, gt_result in ground_truth.items():
            gt_mask = gt_result.classes == class_id
            total_gt += int(gt_mask.sum())
            used_matches[image_path] = set()

        if total_gt == 0:
            continue

        flat_predictions: list[tuple[Path, float, np.ndarray]] = []
        for image_path, pred_result in predictions.items():
            pred_mask = pred_result.classes == class_id
            for score, box in zip(pred_result.scores[pred_mask], pred_result.boxes[pred_mask], strict=False):
                flat_predictions.append((image_path, float(score), box))
        flat_predictions.sort(key=lambda item: item[1], reverse=True)

        for image_path, score, pred_box in flat_predictions:
            gt_result = ground_truth[image_path]
            gt_mask = gt_result.classes == class_id
            gt_boxes = gt_result.boxes[gt_mask]

            best_iou = 0.0
            best_index = None
            for gt_index, gt_box in enumerate(gt_boxes):
                if gt_index in used_matches[image_path]:
                    continue
                iou = compute_iou(pred_box, gt_box)
                if iou > best_iou:
                    best_iou = iou
                    best_index = gt_index

            is_true_positive = best_index is not None and best_iou >= iou_threshold
            if is_true_positive:
                used_matches[image_path].add(best_index)
            entries.append((score, is_true_positive))

        if not entries:
            ap_values.append(0.0)
            continue

        tp = np.cumsum([1 if is_tp else 0 for _, is_tp in entries], dtype=np.float32)
        fp = np.cumsum([0 if is_tp else 1 for _, is_tp in entries], dtype=np.float32)
        recall = tp / max(total_gt, 1)
        precision = tp / np.maximum(tp + fp, 1e-9)
        ap_values.append(compute_average_precision(recall, precision))

    return float(np.mean(ap_values)) if ap_values else 0.0


def benchmark(fn, model_or_session, inputs: Iterable[PreparedImage]) -> BenchmarkResult:
    durations_ms: list[float] = []
    for prepared in inputs:
        start = time.perf_counter()
        fn(model_or_session, prepared)
        durations_ms.append((time.perf_counter() - start) * 1000.0)
    return BenchmarkResult(
        average_ms=float(np.mean(durations_ms)) if durations_ms else 0.0,
        durations_ms=durations_ms,
    )


def collect_predictions(
    pytorch_model: YOLO,
    onnx_session: ort.InferenceSession,
    prepared_images: list[PreparedImage],
) -> tuple[dict[Path, DetectionResult], dict[Path, DetectionResult], dict[Path, DetectionResult]]:
    pytorch_results: dict[Path, DetectionResult] = {}
    onnx_results: dict[Path, DetectionResult] = {}
    ground_truth: dict[Path, DetectionResult] = {}

    for prepared in prepared_images:
        pytorch_results[prepared.path] = run_pytorch_inference(pytorch_model, prepared)
        onnx_results[prepared.path] = run_onnx_inference(onnx_session, prepared)
        ground_truth[prepared.path] = load_ground_truth(prepared)

    return pytorch_results, onnx_results, ground_truth


def benchmark_pytorch_runtime(model: YOLO, prepared: PreparedImage) -> None:
    model.predict(
        source=prepared.rgb,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        iou=IOU_THRESHOLD,
        device="cpu",
        verbose=False,
    )


def benchmark_onnx_runtime(session: ort.InferenceSession, prepared: PreparedImage) -> None:
    input_name = session.get_inputs()[0].name
    session.run(None, {input_name: prepared.tensor})


def main() -> int:
    try:
        onnx_path = export_to_onnx(PT_MODEL_PATH, ONNX_MODEL_PATH)
        image_paths = discover_test_images(IMAGE_ROOT, DEFAULT_IMAGE_LIMIT)
        prepared_images = prepare_images(image_paths)
        pytorch_model, onnx_session = load_models(PT_MODEL_PATH, onnx_path)

        pytorch_results, onnx_results, ground_truth = collect_predictions(
            pytorch_model,
            onnx_session,
            prepared_images,
        )

        output_diff = compare_outputs(pytorch_results, onnx_results)
        pytorch_map = evaluate_map(pytorch_results, ground_truth)
        onnx_map = evaluate_map(onnx_results, ground_truth)
        map_difference_pct = abs(pytorch_map - onnx_map) * 100.0

        pytorch_benchmark = benchmark(benchmark_pytorch_runtime, pytorch_model, prepared_images)
        onnx_benchmark = benchmark(benchmark_onnx_runtime, onnx_session, prepared_images)

        export_pass = onnx_path.exists()
        accuracy_pass = map_difference_pct < 1.0
        speed_pass = onnx_benchmark.average_ms <= 200.0

        print("ONNX Validation Report")
        print("======================")
        print(f"Test images: {len(image_paths)}")
        print(f"PyTorch model: {PT_MODEL_PATH}")
        print(f"ONNX model: {onnx_path}")
        print(f"Avg inference time (PyTorch): {pytorch_benchmark.average_ms:.2f} ms/image")
        print(f"Avg inference time (ONNX): {onnx_benchmark.average_ms:.2f} ms/image")
        print(f"Approx. mAP@0.5 (PyTorch): {pytorch_map:.4f}")
        print(f"Approx. mAP@0.5 (ONNX): {onnx_map:.4f}")
        print(f"mAP difference: {map_difference_pct:.2f}%")
        print(f"Mean bbox difference: {output_diff['mean_bbox_difference']:.4f}")
        print(f"Mean confidence difference: {output_diff['mean_confidence_difference']:.4f}")
        print(f"Class match rate: {output_diff['class_match_rate']:.4f}")
        print(f"Matched predictions: {int(output_diff['matched_predictions'])}")
        print(f"Unmatched predictions: {int(output_diff['unmatched_predictions'])}")
        print(f"ONNX export: {'PASS' if export_pass else 'FAIL'}")
        print(f"Accuracy threshold (<1% mAP diff): {'PASS' if accuracy_pass else 'FAIL'}")
        print(f"Speed threshold (<=200 ms/image): {'PASS' if speed_pass else 'FAIL'}")

        return 0 if export_pass and accuracy_pass and speed_pass else 1
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
