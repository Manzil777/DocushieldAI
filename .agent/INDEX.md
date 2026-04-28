# DocuShieldAI — System Index

## 1. System Overview
- DocuShieldAI protects identity documents by uploading them to a FastAPI backend, extracting sensitive fields, previewing masked output, generating masked PDFs, and creating time-limited share links.
- The current repo also includes an Expo Router mobile client for capture, processing, masking, vault access, and share flows.

## 2. Architecture
- Components:
- Frontend: Expo Router mobile app under `mobile/` for camera capture, masking UI, vault access, and share screens. No Next.js frontend directory is present.
- Backend (FastAPI): `backend/app/main.py` with route modules for auth, documents, vault, and public share access.
- AI services: YOLOv8 model at `backend/models/best.pt`, OCR and preprocessing under `backend/app/services/ai/`, and masking/pipeline orchestration in `backend/app/services/`.
- Supabase (Auth, DB, Storage): not wired in the current repo state. The implemented backend uses local JWT auth, SQLAlchemy-backed persistence, Redis-style token caching, and MinIO/local storage utilities.
- Data Flow:
- Upload → OCR → PII Detection → Masking → Secure Share → View

## 3. Key Architectural Decisions
- YOLOv8 was chosen for field detection because the repo ships a trained checkpoint (`backend/models/best.pt`) and the evaluation results are strong enough for lightweight document-field localization.
- Tesseract OCR was chosen because the pipeline is fully local, open-source, and already integrated in `backend/app/services/ai/ocr.py` with preprocessing and postprocessing support.
- FastAPI was chosen because the backend needs a small Python-native HTTP layer around ML inference, masking, vault, and share workflows.
- JWT auth was chosen because the backend already implements stateless access tokens plus refresh-token validation and expiry checks.
- Redis-backed token/share caching was chosen because refresh tokens and share-token TTL/view tracking need lightweight server-side state.
- MinIO/local object-style storage was chosen because the backend stores uploaded files, masked files, and shareable PDFs through a storage abstraction without coupling the API to a cloud SDK.

## 4. Component Inventory (ACTUAL FILES)
- `backend/app/api/routes/`
- `backend/app/services/ai/`
- `backend/app/services/`
- `backend/app/core/`
- `backend/app/models/`
- `backend/app/schemas/`
- `backend/models/best.pt`
- `backend/models/best.onnx`
- `backend/tests/`
- `backend/tests/integration/`
- `backend/tests/security/`
- `mobile/app/`
- `mobile/screens/`
- `mobile/lib/services/`
- `scripts/`
- `reports/`
- `.agent/`

## 5. AI Metrics (from Issue #33)
- mAP@50: 0.9896
- mAP@50-95: 0.7708
- Precision: 0.9807
- Recall: 0.9658
- OCR:
- name: 1.0 / 1.0
- dob: 0.75 / 0.0
- aadhaar: 0.9833 / 0.8
- Worst class: ADDRESS

## 6. Performance (Issue #32)
- Local in-process benchmark completed via `scripts/benchmark.py --mode local --iterations 5`
- Average latency: 0.664s
- p50: 0.621s
- p95: 0.846s
- p99: 0.846s
- Note: current recorded benchmark excludes live HTTP socket overhead and measures the backend flow in-process.

## 7. Security Summary (Issue #34)
- JWT auth + expiry validated
- Input validation implemented
- Share token expiry + view tracking implemented
- Bandit:
- 0 high
- 2 medium issues
- Known gaps:
- No broad API rate limiting on auth/upload flows
- No upload size restriction
- Temp file + XML issues

## 8. Known Limitations
- OCR is inconsistent on DOB extraction and normalization compared with other evaluated fields.
- QR validation is weak in the current lightweight evaluation and synthetic OCR test setup.
- No broad auth/upload rate limiting or login throttling is implemented on the API.
- Upload validation checks file type and malformed content, but no explicit upload size limit is enforced.
- Live HTTP latency numbers are not yet recorded; the current repo includes an in-process benchmark report in `docs/performance_report.md`.
- The current backend implementation does not use Supabase; the checked-in stack is FastAPI, SQLAlchemy, Redis-style caching, and MinIO/local storage utilities.

## 9. Phase 2 Scope
- Improve OCR robustness, especially for DOB parsing and noisy crops.
- Add rate limiting and auth throttling.
- Optimize end-to-end latency to target sub-8-second processing.
- Improve forgery detection coverage and evaluation quality.
- Improve QR validation accuracy and real-document validation coverage.

## 10. Setup Instructions
```bash
git clone <repository-url>
cd DocushieldAI
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Optional mobile client:
```bash
cd mobile
npm install
npm run start
```
