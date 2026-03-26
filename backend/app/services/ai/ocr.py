import cv2
import pytesseract
import numpy as np
import re
from typing import List, Dict
from backend.app.services.ai.postprocessor import postprocess

def preprocess_crop(crop, field_type=None):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Upscale
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    if field_type == "aadhaar_number":
        # LIGHT processing for digits (IMPORTANT)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        return blur
    else:
        # Strong processing for text
        kernel = np.array([[0, -1, 0],
                           [-1, 5,-1],
                           [0, -1, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)

        _, thresh = cv2.threshold(sharpened, 150, 255, cv2.THRESH_BINARY)

        return thresh

def run_ocr(crop, field_type=None):
    if field_type == "aadhaar_number":
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        lang = 'eng'
    else:
        config = r'--oem 3 --psm 6'
        lang = 'hin+eng'

    return pytesseract.image_to_string(crop, lang=lang, config=config).strip()

def extract_aadhaar(text):
    import re

    digits = re.sub(r'\D', '', text)  # remove non-digits

    if len(digits) == 12:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    
    return None

def extract_fields(image, detections: List[Dict]) -> Dict[str, str]:
    results = {}

    for det in detections:
        field = det["class"]
        x1, y1, x2, y2 = map(int, det["bbox"])

        crop = image[y1:y2, x1:x2]
        cv2.imwrite(f"debug_{field}.jpg", crop)
        if crop.size == 0:
            continue

        processed = preprocess_crop(crop, field)
        text = run_ocr(processed, field)

        results[field] = text
    
    processed_results= postprocess(results)

    return {
        "raw": results,
        "processed": processed_results
    }

