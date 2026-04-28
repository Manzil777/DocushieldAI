# 1. Introduction

DocuShield AI addresses the unsafe sharing of identity documents such as Aadhaar cards. In many real-world workflows, citizens hand over full scans or photocopies to hotels, telecom counters, printing shops, and other third parties with little control over downstream misuse.

The motivation for this system is document privacy and misuse prevention. The project focuses on detecting sensitive personal information, masking only the necessary regions, and sharing a controlled derivative instead of the raw document.

# 2. System Architecture

The system is composed of:

- Frontend: Expo/React Native mobile client for authentication, upload, masking selection, and share operations
- Backend: FastAPI application exposing auth, document, vault, and share routes
- AI services: preprocessing, YOLO-based field detection, OCR, QR validation, forgery analysis, and masking
- Supabase/persistence layer: intended managed auth/database/storage target; the checked-in repository currently uses SQLAlchemy, Redis, and a storage abstraction with MinIO/local fallback for local validation

Step-by-step data flow:

1. The authenticated client uploads an Aadhaar image or PDF to `POST /documents/upload`.
2. The backend stores the original file and converts the first page to an image when needed.
3. The preprocessing stage performs resizing, CLAHE, and deskewing.
4. The YOLO ONNX detector localizes supported fields such as Aadhaar number, DOB, gender, name, and address.
5. Tesseract OCR runs on cropped detections and the post-processor normalizes raw text into structured field values.
6. Forgery and QR-validation services generate auxiliary integrity signals.
7. The client selects fields to hide and calls `POST /documents/{id}/mask`.
8. The masking service blacks out the selected bounding boxes and stores masked image/PDF artefacts.
9. `GET /documents/{masked_id}/masked-pdf` creates or reuses a shareable masked PDF and returns a share token.
10. `GET /share/{token}` serves the masked preview and controlled PDF access to the recipient.

# 3. AI Methodology

The OCR engine used in the implemented backend is Tesseract via `pytesseract`, with English-only digit extraction for Aadhaar-number regions and `hin+eng` OCR for textual regions.

PII detection is based on YOLO field localization. The current pipeline loads `backend/models/best.onnx` and maps detector classes to logical fields such as `aadhaar_number`, `dob`, `gender`, `name`, and `address`.

Masking is region-based. After detection and OCR, the backend stores bounding boxes and later converts requested mask fields such as `uid` and `dob` into the corresponding coordinates. The selected boxes are then painted black in the masked derivative.

Additional AI-related modules include:

- `qr_validator.py` for Aadhaar-style QR decoding and field comparison
- `forgery.py` for ELA-based forgery signal generation
- `augmentation.py` for training-time augmentation using glare, blur, perspective skew, and crop simulation

# 4. Results & Evaluation

- mAP@50: `0.963` from `backend/models/baseline_metrics.json`
- TRA: not formally reported in the repository
- End-to-end latency: not formally benchmarked in the repository

Observations:

- The implemented backend supports the full upload -> mask -> share -> public-view path.
- Masked PDF generation is cached/reused when a share PDF already exists for the masked document.
- Share access includes expiry handling, rate limiting, and optional view-count limits.
- The repository contains integration and unit tests for upload, masking, share-token handling, OCR helpers, and vault behavior, although async integration tests require `pytest-asyncio` in the environment.

# 5. Security Measures

Authentication is handled through bearer-token protected FastAPI routes. The project goal references Supabase-backed auth; the current checked-in backend implements JWT-based access and refresh token handling through the auth service.

Sharing is token-based. Public document access is exposed through `/share/{token}`, while the token record stores expiry, masked fields, and view counters. Redis-backed state is used for TTL, rate limiting, and view tracking, with in-memory fallback for local validation.

Expiry handling is enforced on public share access. Expired tokens return denial responses and view limits can be enforced for shared assets.

Storage/security considerations:

- Original and masked assets are stored separately
- Masked public sharing is restricted to derived documents, not the original upload
- Object storage access is abstracted through the storage service
- Local fallback storage avoids user-specific hardcoded paths

# 6. Conclusion

The repository successfully demonstrates the main BAD685 submission objective: an AI-assisted pipeline that uploads identity documents, localizes sensitive information, masks selected fields, and shares only the protected derivative.

Current limitations are the absence of formal OCR accuracy and latency benchmarking in the repository, the reliance on local fallbacks for evaluator runs, and the presence of legacy prototype code outside the active FastAPI/mobile stack.

Future improvements include production-grade Supabase integration, formal benchmark reporting for OCR and latency, broader document-class support, and stronger anti-forgery evaluation on curated datasets.
