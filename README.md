# DocuShield AI

DocuShield AI is an identity-document protection system for Aadhaar-style documents. The repository contains a FastAPI backend, an Expo/React Native mobile client, and an AI-assisted pipeline that detects sensitive fields, extracts text, applies masking, and generates controlled share artefacts.

For BAD685 submission review, the core implemented flow is:

`Upload -> OCR + field detection -> Mask selected PII -> Generate share token/PDF -> Open masked share link`

## Project Overview

The system is designed to reduce unsafe sharing of raw identity documents. Instead of handing over an unprotected Aadhaar image or PDF, the owner uploads the document, runs AI-assisted extraction and field localization, masks selected regions, and distributes a controlled share link that exposes only the masked version.

Primary goals:

- detect sensitive fields on an identity document
- extract text for downstream validation and display
- mask selected regions before sharing
- generate expiring, view-tracked share access
- keep original and masked assets separated

## End-to-End Pipeline

1. The mobile app authenticates the user and uploads an image or PDF to `POST /documents/upload`.
2. The backend stores the original file through the storage service.
3. The upload route converts the first page into an image if needed, then runs the AI pipeline.
4. `pipeline_service.py` preprocesses the document, loads the YOLO ONNX detector, localizes supported fields, and calls OCR/post-processing.
5. OCR results, field bounding boxes, forgery output, and QR-validation output are stored against the document record.
6. The client chooses fields to hide and calls `POST /documents/{id}/mask`.
7. `masking_service.py` converts requested logical fields such as `uid` and `dob` into bounding boxes, blacks out those regions, and writes masked image/PDF assets.
8. The client calls `GET /documents/{masked_id}/masked-pdf` to prepare a shareable PDF and receive a deterministic share token.
9. Recipients open `GET /share/{token}` to view the masked preview and fetch the masked PDF until expiry or view limits are reached.

## Architecture

```text
┌──────────────────────┐
│  Mobile Frontend     │
│  Expo / React Native │
└──────────┬───────────┘
           │ auth, upload, mask, share
           v
┌──────────────────────────────────────────────┐
│              FastAPI Backend                 │
│ /auth  /documents  /vault  /share  /health   │
└──────────┬───────────────────────┬───────────┘
           │                       │
           │                       │
           v                       v
┌──────────────────────┐   ┌──────────────────────┐
│     AI Services      │   │  Persistence Layer   │
│ preprocessing        │   │ SQLAlchemy models    │
│ YOLO ONNX detector   │   │ share tokens         │
│ Tesseract OCR        │   │ Redis view/TTL state │
│ post-processing      │   │ object storage       │
│ QR validation        │   │ MinIO or local store │
│ forgery analysis     │   └──────────────────────┘
└──────────────────────┘
```

Notes:

- The submission architecture targets Supabase-style managed auth/database/storage for deployment.
- The checked-in backend currently exposes equivalent concerns through FastAPI, SQLAlchemy, Redis, and an object-storage abstraction with local fallback for evaluator-friendly local runs.

## AI Components

- `backend/app/services/pipeline_service.py`: orchestrates preprocessing, detection, OCR, and packaging of pipeline output.
- `backend/app/services/ai/preprocessing.py`: resize, CLAHE, deskew, and blur checks.
- `backend/app/services/ai/ocr.py`: Tesseract OCR over detected crops, followed by post-processing.
- `backend/app/services/ai/postprocessor.py`: normalizes OCR text into structured fields such as UID and DOB.
- `backend/app/services/ai/qr_validator.py`: attempts Aadhaar-style QR decoding and field matching.
- `backend/app/services/ai/forgery.py`: ELA-based forgery signal generation.
- `backend/app/services/masking_service.py`: converts requested fields into bounding boxes and paints masked regions.
- `backend/app/services/ai/augmentation.py`: Albumentations pipeline used to simulate glare, blur, skew, and crop variation during dataset preparation.

Current detector artefacts:

- `backend/models/best.onnx`
- `backend/models/best.pt`
- `backend/models/baseline_metrics.json`

## Repository Layout

```text
DocushieldAI/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── models/
│   ├── tests/
│   └── requirements.txt
├── mobile/
│   ├── app/
│   ├── lib/services/
│   └── package.json
├── docs/
├── requirements.txt
└── README.md
```

## Setup

### Backend

System packages required for the OCR/PDF path:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-hin poppler-utils
```

Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Optional environment variables:

```bash
export DATABASE_URL="sqlite:///./docushield.db"
export REDIS_URL="redis://localhost:6379/0"
export MINIO_ENDPOINT="localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"
export MINIO_BUCKET="docushield"
export APP_BASE_URL="http://localhost:8000"
export JWT_SECRET="change-me"
export TESSERACT_PATH="/usr/bin/tesseract"
```

Run the API from the backend directory:

```bash
cd backend
uvicorn app.main:app --reload
```

Useful routes:

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /documents/upload`
- `POST /documents/{id}/mask`
- `GET /documents/{id}/masked-pdf`
- `GET /share/{token}`

### Frontend

The mobile client is under `mobile/` and expects the API/share base URLs through Expo public env vars.

```bash
cd mobile
npm install
```

Create a local env file for Expo:

```bash
EXPO_PUBLIC_API_URL=http://localhost:8000
EXPO_PUBLIC_SHARE_BASE_URL=http://localhost:8000
```

Start the app:

```bash
npx expo start
```

If testing on a physical device, replace `localhost` with the machine's LAN IP.

## Demo Flow

1. Upload Aadhaar using an authenticated client via `POST /documents/upload`.
2. AI processing runs inside the upload request: preprocessing, YOLO field detection, OCR, post-processing, forgery analysis, and QR validation.
3. Mask sensitive fields by calling `POST /documents/{id}/mask` with fields such as `uid`, `dob`, `name`, `gender`, or `address`.
4. Generate a secure share artefact by calling `GET /documents/{masked_id}/masked-pdf`, then distribute the resulting `/share/{token}` link.
5. Access the masked document through `GET /share/{token}` to retrieve the masked preview and the masked PDF URL until the token expires.

Important API note:

- The current FastAPI implementation performs upload processing synchronously.
- There is no separate `/documents/{id}/status` endpoint in the shipped backend.

## Validation Notes

Submission-readiness checks applied to this repo:

- The documented upload -> mask -> share -> view route chain exists in the backend.
- Runtime dependency lists were updated to include packages used by the backend and tests, including `pytesseract`, `pdf2image`, `httpx`, and `pytest-asyncio`.
- Detector artefacts are referenced from `backend/models/`, not from user-specific absolute paths.
- OCR debug image writes were removed from the request path to avoid polluting the working directory during normal execution.
- `TESSERACT_PATH` is now env-driven instead of defaulting to a hardcoded local absolute path.
- Storage falls back to `.storage/` if MinIO is unavailable, which helps local evaluation.

## Results Snapshot

- YOLO baseline metric file reports `mAP50 = 0.963`, `precision = 0.973`, and `recall = 0.962`.
- Upload, masking, share-token, and share-view behavior are covered by backend tests in `backend/tests/`.
- Public share responses enforce expiry, rate limiting, and optional view limits in `share_service.py`.

## Submission Deliverables

- `README.md`: evaluator-oriented overview, setup, architecture, demo flow, and validation notes
- `docs/BAD685_Final_Report.md`: concise technical final report

## License

MIT
