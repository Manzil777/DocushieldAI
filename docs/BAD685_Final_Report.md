# 1. Introduction

DocuShield AI addresses unsafe sharing of identity documents such as Aadhaar cards. Instead of distributing full scans or photocopies, the system uploads the document, detects sensitive fields, generates a masked derivative, and shares only the protected output.

The implemented repository focuses on evaluator-ready execution of the full upload, extract, mask, and share flow. The current submission includes a FastAPI backend, an Expo/React Native mobile client, and a local AI pipeline built around YOLOv8 field detection and Tesseract OCR.

# 2. System Architecture

The checked-in system is composed of:

- Frontend: Expo/React Native mobile client for authentication, upload, masking selection, vault access, and share operations
- Backend: FastAPI application exposing auth, document, vault, share, and health routes
- AI services: preprocessing, YOLOv8-based field detection, Tesseract OCR, QR validation, forgery analysis, and masking
- Persistence and storage: SQLAlchemy-backed persistence, Redis-style token/share caching with in-memory fallback, and MinIO/local object storage fallback

Supabase is not used by the current repository state. The implemented submission stack runs through FastAPI, SQLAlchemy, Redis-compatible caching, and storage fallbacks that are suitable for local validation.

Step-by-step data flow:

1. The authenticated client uploads an Aadhaar image or PDF to `POST /documents/upload`.
2. The backend stores the original file and converts the first page to an image when needed.
3. The preprocessing stage performs resizing, CLAHE, and deskewing.
4. The YOLOv8 ONNX detector localizes supported fields such as Aadhaar number, DOB, gender, name, and address.
5. Tesseract OCR runs on cropped detections and the post-processor normalizes raw text into structured field values.
6. Forgery and QR-validation services generate auxiliary integrity signals.
7. The client selects fields to hide and calls `POST /documents/{id}/mask`.
8. The masking service blacks out the selected bounding boxes and stores masked image/PDF artefacts.
9. `GET /documents/{masked_id}/masked-pdf` creates or reuses a shareable masked PDF and returns a share token.
10. `GET /share/{token}` serves the masked preview and controlled PDF access to the recipient.

# 3. AI Methodology

The OCR engine used in the implemented backend is Tesseract via `pytesseract`, with region-specific OCR behavior for Aadhaar-number fields and textual fields.

PII detection is based on YOLOv8 field localization. The current pipeline loads `backend/models/best.onnx` and maps detector classes to logical fields such as `aadhaar_number`, `dob`, `gender`, `name`, and `address`.

Masking is region-based. After detection and OCR, the backend stores bounding boxes and later converts requested mask fields such as `uid` and `dob` into the corresponding coordinates. The selected boxes are then painted black in the masked derivative.

Additional AI-related modules include:

- `qr_validator.py` for Aadhaar-style QR decoding and field comparison
- `forgery.py` for ELA-based forgery signal generation
- `augmentation.py` for training-time augmentation using glare, blur, perspective skew, and crop simulation

# 4. Results And Evaluation

## Detection Metrics

- mAP@50: `0.9896`
- mAP@50-95: `0.7708`
- Precision: `0.9807`
- Recall: `0.9658`
- Worst class: `ADDRESS`

## OCR Metrics

- name: char accuracy `1.0`, word accuracy `1.0`
- dob: char accuracy `0.75`, word accuracy `0.0`
- aadhaar: char accuracy `0.9833`, word accuracy `0.8`

## Performance

- Benchmark mode: in-process benchmarking, not live HTTP
- Average latency: `0.664s`
- p50: `0.621s`
- p95: `0.846s`
- p99: `0.846s`
- Network latency is not included in these measurements

Observations:

- Detection performance is strong at mAP@50, but the gap between mAP@50 and mAP@50-95 indicates weaker localization quality at stricter IoU thresholds.
- OCR performance is strongest on name and Aadhaar-number extraction.
- DOB extraction remains the weakest OCR output and is the main structured-text normalization gap in the current submission.
- The implemented backend supports the full upload -> mask -> share -> public-view path in the checked-in repository.

# 5. Security Summary

Authentication is handled through JWT-based access and refresh tokens with expiry validation on protected FastAPI routes.

Security checks and controls in the current repository include:

- JWT authentication with expiry enforcement
- Input validation on request payloads and file handling
- Token-based share access with expiry and view tracking
- Bandit scan result: `0` high findings and `2` medium findings

Known gaps:

- No general API rate limiting on auth or upload flows
- No explicit upload size restriction
- OCR and document-processing dependencies still require standard hardening attention for temporary file and XML-related concerns

# 6. Conclusion

The repository demonstrates the BAD685 submission goal with an implemented Aadhaar-protection workflow that uploads identity documents, localizes sensitive information, masks selected fields, and shares only the protected derivative.

The final measured results show strong detector performance, sub-second local in-process latency, and a working secure-share flow. The main remaining weaknesses are DOB OCR robustness, stricter-box localization consistency, and missing production hardening such as broad API rate limiting and upload-size enforcement.
