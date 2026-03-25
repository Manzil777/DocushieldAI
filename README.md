# DocuShield AI 🛡️

> AI-powered identity document protection and secure sharing for Indian citizens.

**CMRIT — Department of AI & Data Science | Project BAD685 | Phase 1**

---

## What It Does

DocuShield AI lets you upload your Aadhaar card, automatically detect and selectively mask sensitive PII fields using AI, store documents in an encrypted personal vault, and share controlled versions via time-limited links, QR codes, or one-time masked PDFs — without ever exposing raw document data to the recipient.

The core problem: hotels, SIM vendors, printing shops, and KYC counters routinely photocopy or store full Aadhaar cards with zero access control. DocuShield inverts this — **you decide what a recipient sees, and for how long.**

---

## Features (Phase 1)

- **AI Field Detection** — YOLOv8 detects 5 Aadhaar fields (Aadhaar Number, Name, DOB, Gender, Address) with ~92.5% mAP-50
- **Selective Masking UI** — toggle each field on/off before sharing
- **Secure Sharing** — time-limited links (1h / 6h / 24h), QR codes, one-time masked PDFs
- **Document Vault** — AES-256 encrypted storage, accessible only to you
- **Forgery Detection** — CNN + Error Level Analysis flags manipulated documents before vault storage
- **Aadhaar Number Masking** — always defaults to `XXXX XXXX 1234`

---

## Stack

| Layer | Technology |
|-------|-----------|
| Mobile App | React Native (Expo) |
| Backend API | FastAPI + Uvicorn |
| AI Detection | YOLOv8 (Ultralytics) + ONNX |
| OCR | Tesseract 5.x (`lang='hin+eng'`) |
| Augmentation | albumentationsx |
| Image Processing | OpenCV |
| Database | PostgreSQL (Supabase) |
| Storage | Supabase Storage |
| Auth | Supabase Auth + JWT |
| Cache | Redis (share token TTL) |
| PDF Generation | ReportLab |

---

## Repo Structure

```
DocushieldAI/
├── CLAUDE.md                        # AI agent instructions (GSD protocol)
├── DOCUSHIELD_PRD.md                # Full product requirements
├── requirements.txt
├── .agent/
│   ├── INDEX.md                     # Task tracker
│   ├── GETSHITDONE.md               # GSD task contracts
│   ├── ROADMAP.md
│   └── skills/
├── backend/
│   ├── app/
│   │   └── services/
│   │       └── ai/
│   │           └── augmentation.py  # Albumentations pipeline (Issue #6)
│   │           └── preprocessing.py  # Preprocessing pipeline (Issue #7)
│   └── models/
│       ├── best.pt                  # YOLOv8 fine-tuned weights
│       └── baseline_metrics.json
├── data/
│   └── aadhaar/
│       ├── dataset.yaml             # Class labels + split paths
│       ├── hyp.yaml                 # YOLOv8 training hyperparameters
│       ├── train/                   # ⚠️ Not in git — see Dataset section
│       ├── valid/
│       └── test/
├── docs/
│   └── DocuShield_Security_Architecture.docx
└── scripts/
│   └── test_preprocessing.py  # preprocessing pipeline (Issue #7)
```

---

## Dataset

The Aadhaar training dataset (~118MB) is not included in this repo. Download and extract to `data/aadhaar/`:

**[Download Dataset — Google Drive](#)** *(link coming soon)*

After extraction your structure should match:
```
data/aadhaar/
├── train/images/   # Training images
├── train/labels/   # YOLO format labels
├── valid/images/
├── valid/labels/
├── test/images/
├── test/labels/
├── dataset.yaml    ← already in repo
└── hyp.yaml        ← already in repo
```

Class labels:
```yaml
0: AADHAR_NUMBER
1: DATE_OF_BIRTH
2: GENDER
3: NAME
4: ADDRESS
```

---

## Setup

```bash
# Clone
git clone https://github.com/Manzil777/DocushieldAI.git
cd DocushieldAI

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## AI Pipeline Progress

| Task | Status |
|------|--------|
| Dataset YAML + class labels | ✅ Done |
| Data augmentation pipeline | ✅ Done |
| YOLOv8 field detection | 🔄 In progress |
| Tesseract OCR integration | ⏳ Pending |
| Forgery detection (ELA + CNN) | ⏳ Pending |
| Full pipeline orchestrator | ⏳ Pending |

---

## Augmentation Pipeline

`backend/app/services/ai/augmentation.py` implements 4 augmentation types to simulate real-world scanning conditions:

| Augmentation | Simulates |
|---|---|
| `RandomSunFlare` | Glare on laminated card surface |
| `MotionBlur` / `GaussianBlur` | Shaky hands / out-of-focus camera |
| `Perspective` | Card held at an angle |
| `RandomResizedCrop` | Partially cropped scan |

Visual test:
```bash
python backend/app/services/ai/augmentation.py data/aadhaar/train/images/sample.jpg
xdg-open /tmp/aug_preview.jpg
```

---

## Security Architecture

Full security specification in `docs/DocuShield_Security_Architecture.docx`. Key controls:

- Supabase RLS on all tables — cross-user data access impossible at DB level
- File upload validation — magic bytes + MIME type check + UUID filename replacement
- JWT auth on all `/documents/*` endpoints
- Share tokens — scoped, short-lived, stored as hash, Redis TTL expiry
- No plaintext Aadhaar numbers in logs, DB fields, or API responses

---

## GSD Workflow

This project uses the **Get-Shit-Done (GSD)** atomic task protocol. Every implementation task follows:

```
One task = One file = One function
Read before write → Run acceptance test → Commit
```

Full task contracts and current status in `.agent/GETSHITDONE.md`.

---

## Research Foundation

| Paper | Contribution |
|-------|-------------|
| NetraAadhaar (IEEE Access 2025) | YOLOv8 + Tesseract pipeline, mAP-50 = 92.5% |
| Mero Nagarikta (IOE Tribhuvan, 2024) | Preprocessing pipeline, address post-processing |
| Hybrid OCR-Regex PII Tool (IJARIIE 2025) | Masking quality metrics, deepfake integration |
| Fake Aadhaar Detection Review (IJRTI 2025) | CNN + ELA forgery detection, 4000-image dataset |

---

## Milestones

| Milestone | Deliverable | Target |
|-----------|-------------|--------|
| M1 | YOLOv8 fine-tuned on Aadhaar dataset | Week 4 |
| M2 | OCR + masking pipeline | Week 6 |
| M3 | FastAPI backend: auth + vault + share tokens | Week 8 |
| M4 | React Native app: upload + masking UI | Week 10 |
| M5 | Share output: link + QR + PDF | Week 12 |
| M6 | Forgery detection integrated | Week 14 |
| M7 | End-to-end integration + testing | Week 16 |

---

## License

MIT — CMRIT Department of AI & Data Science, 2026
