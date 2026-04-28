# AI Evaluation Report

## 1. YOLOv8 Detection
- mAP@50: 0.9896
- mAP@50-95: 0.7708
- Precision: 0.9807
- Recall: 0.9658

## 2. OCR Performance (TRA)
- name: char_acc=1.0000, word_acc=1.0000
- dob: char_acc=0.7500, word_acc=0.0000
- aadhaar: char_acc=0.9833, word_acc=0.8000

## 3. Confusion Matrix
- Image: `reports/confusion_matrix.png`

## 4. Observations
- Weakest detection class by mAP@50-95: ADDRESS
- Weakest OCR field by character accuracy: dob
- OCR remains the likely bottleneck when field text quality is poor, while detection quality depends on box localization and class separation.

## 5. Limitations
- The OCR evaluation uses a small synthetic set to provide deterministic field-level ground truth.
- The detection metrics depend on the current local dataset split and model checkpoint.
- Real-world documents can vary more in blur, lighting, skew, language, and occlusion than this evaluation covers.

## 6. Optional Modules
- Forgery detection: not_evaluated (No forgery ground truth is included in this lightweight OCR evaluation.)
- QR validation: ok (success_rate=0.0000; Synthetic OCR samples do not contain QR codes, so this is expected to be low.)
