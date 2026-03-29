from __future__ import annotations

from pathlib import Path
import sys

import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.ai.forgery import detect_forgery

IMAGE_ROOT = REPO_ROOT / "data/aadhaar"
IMAGE_LIMIT = 5


def discover_images(limit: int = IMAGE_LIMIT) -> list[Path]:
    images = sorted(
        path
        for ext in ("*.jpg", "*.jpeg", "*.png")
        for path in IMAGE_ROOT.rglob(ext)
    )
    if len(images) < limit:
        raise FileNotFoundError(
            f"Expected at least {limit} images under {IMAGE_ROOT}, found {len(images)}."
        )
    return images[:limit]


def simulate_tampering(image):
    tampered = image.copy()
    height, width = tampered.shape[:2]

    src_y1, src_y2 = height // 6, height // 3
    src_x1, src_x2 = width // 6, width // 2
    patch = tampered[src_y1:src_y2, src_x1:src_x2].copy()

    dst_y = min(height - patch.shape[0] - 1, height // 2)
    dst_x = min(width - patch.shape[1] - 1, width // 3)
    tampered[dst_y:dst_y + patch.shape[0], dst_x:dst_x + patch.shape[1]] = patch

    overlay_x1 = width // 2
    overlay_y1 = height // 5
    overlay_x2 = min(width - 1, overlay_x1 + width // 5)
    overlay_y2 = min(height - 1, overlay_y1 + height // 12)
    cv2.rectangle(tampered, (overlay_x1, overlay_y1), (overlay_x2, overlay_y2), (255, 255, 255), -1)
    cv2.putText(
        tampered,
        "XXX",
        (overlay_x1 + 10, min(height - 5, overlay_y1 + height // 16)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )

    return tampered


def main() -> int:
    images = discover_images()

    genuine_flags = []
    tampered_flags = []

    print("Forgery Detection Report")
    print("=======================")
    for image_path in images:
        original = cv2.imread(str(image_path))
        if original is None:
            raise ValueError(f"Failed to read image: {image_path}")

        forged = simulate_tampering(original)

        genuine_result = detect_forgery(original)
        tampered_result = detect_forgery(forged)

        genuine_flags.append(genuine_result["is_forged"])
        tampered_flags.append(tampered_result["is_forged"])

        print(
            f"{image_path.name} | original | forged={genuine_result['is_forged']} "
            f"| confidence={genuine_result['confidence']:.4f}"
        )
        print(
            f"{image_path.name} | tampered | forged={tampered_result['is_forged']} "
            f"| confidence={tampered_result['confidence']:.4f}"
        )

    false_positive_rate = sum(genuine_flags) / len(genuine_flags)
    true_positive_rate = sum(tampered_flags) / len(tampered_flags)

    print("-----------------------")
    print(f"Genuine false positive rate: {false_positive_rate:.2%}")
    print(f"Tampered detection rate: {true_positive_rate:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
