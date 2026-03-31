import cv2
import pytesseract
import re
import os

tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.name == 'nt' and os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def mask_aadhaar_in_image(image_path):
    img = cv2.imread(image_path)

    if img is None:
        return image_path

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    n = len(data['text'])

    for i in range(n):
        text = data['text'][i]

        # Strict match for speed + accuracy
        if re.fullmatch(r"\d{4}", text):
            x = data['left'][i]
            y = data['top'][i]
            w = data['width'][i]
            h = data['height'][i]

            # Expand area
            x1 = max(0, x - 20)
            y1 = max(0, y - 10)
            x2 = x + w + 80
            y2 = y + h + 10

            roi = img[y1:y2, x1:x2]

            blurred = cv2.GaussianBlur(roi, (51, 51), 30)

            img[y1:y2, x1:x2] = blurred

    filename = os.path.basename(image_path)
    output_path = os.path.join(os.path.dirname(image_path), "masked_" + filename)

    cv2.imwrite(output_path, img)

    return output_path