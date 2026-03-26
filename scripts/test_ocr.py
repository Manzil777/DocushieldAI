import cv2
from backend.app.services.ai.ocr import extract_fields

# Load image
image = cv2.imread("data/aadhaar/train/images/0c0584201ff552c4bdcbe160315aa432_jpg.rf.2b6b3019429fe97ca467ac2f5509fb48.jpg")

# Debug check (IMPORTANT)
print("Image loaded:", image is not None)

# Fake bounding boxes (for testing)
detections = [
    {"class": "name", "bbox": [200, 200, 600, 350]},
    {"class": "aadhaar_number", "bbox": [200, 500, 600, 580]},
]
# Run OCR pipeline
result = extract_fields(image, detections)

# Print output
print("\n=== OCR OUTPUT ===")
print(result)
