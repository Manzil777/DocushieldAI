import pytesseract
import cv2
import os

tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.name == 'nt' and os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def extract_text(image_path):
    img = cv2.imread(image_path)

    # Convert to grayscale (improves OCR speed + accuracy)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    text = pytesseract.image_to_string(gray)

    return text