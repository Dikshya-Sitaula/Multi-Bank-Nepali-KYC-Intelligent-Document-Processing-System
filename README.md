# 🏦 Multi-Bank Nepali KYC Intelligent Document Processing System

<div align="center">

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Python](https://img.shields.io/badge/Python-3.13-green)
![Node](https://img.shields.io/badge/Node.js-24-brightgreen)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Status](https://img.shields.io/badge/status-Active%20Development-orange)

**A computer vision–powered system that reads filled Nepali bank KYC forms and presents every extracted field for human review — no auto-approval, ever.**

[Features](#-features) · [Tech Stack](#-tech-stack) · [Setup](#-setup) · [Running](#-running) · [Project Structure](#-project-structure) · [API Docs](#-api-docs) · [Screenshots](#-screenshots) · [Limitations](#️-limitations)

</div>

---

## 📌 What Is This?

Nepali bank staff manually retype paper KYC (Know Your Customer) forms by hand — a slow, error-prone process. This system automates the **first pass**:

1. A bank officer uploads a photo or scan of a filled KYC form.
2. The system automatically:
   - Figures out **which bank's form** it is (Laxmi Sunrise, Machhapuchchhre, NIC Asia)
   - Straightens, denoises and enhances the page
   - Finds every field box on the form
   - Reads the text using OCR (English and Nepali/Devanagari)
   - Extracts checkbox selections
3. All results appear side-by-side with the original page for a **human to verify**.

> **This is a review tool, not an auto-approver.** Nothing is ever marked as verified until a person explicitly presses Verify. Identity verification, face/signature matching and fraud detection are out of scope.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📤 **Multi-format Upload** | JPEG, PNG, PDF — single or multi-page |
| 🔍 **Automatic Form Identification** | SIFT/ORB keypoint matching + RANSAC homography identifies the bank and page number |
| 🖼️ **Page Pre-processing** | EXIF orientation fix, perspective correction, deskew, denoising, CLAHE contrast (all configurable) |
| 📊 **Quality Warnings** | Flags blur, skew, glare and low resolution before processing |
| 📦 **Field Extraction** | Template box alignment → OpenCV contour snapping → EasyOCR (English + Nepali) |
| ☑️ **Checkbox Detection** | Ink fill ratio vs. baseline to determine selected/unselected options |
| 👤 **Customer Profile Registry** | Extracted fields are auto-aggregated into a consolidated customer record |
| 🔬 **Vision Lab** | Inspect every CV pipeline stage with before/after images, timings and live re-runs |
| ✅ **Human Review Workflow** | Edit values, verify fields, track confidence — field-by-field |
| 🔎 **Search** | Search documents and customer profiles in English or Devanagari |
| 📁 **Export** | Download any document's extracted data as JSON or CSV |
| 🔐 **JWT Authentication** | Role-based access (admin / employee), login rate limiting, audit log |
| 🌙 **Dark / Light Theme** | Responsive UI that works on desktop and mobile |

---

## 🛠 Tech Stack

### Backend
| Library | Purpose |
|---|---|
| **FastAPI** | REST API framework |
| **SQLAlchemy** | ORM — SQLite for dev, PostgreSQL-ready |
| **Alembic** | Database migrations |
| **PyJWT + bcrypt** | Authentication and password hashing |
| **OpenCV** | Preprocessing, feature matching, box detection |
| **EasyOCR** | English and Nepali text recognition |
| **scikit-image** | Image quality metrics |
| **PyMuPDF** | PDF rasterization |
| **NumPy** | Numerical operations |

### Frontend
| Library | Purpose |
|---|---|
| **React 19** | UI framework |
| **TypeScript** | Type-safe JavaScript |
| **Vite** | Build tool and dev server |
| **Tailwind CSS v4** | Utility-first styling |
| **TanStack Query** | Server state and data fetching |
| **Framer Motion** | Animations |
| **Recharts** | Charts and dashboards |
| **React Zoom Pan Pinch** | Zoomable document viewer |
| **Lucide React** | Icons |

### Infrastructure
| Tool | Purpose |
|---|---|
| **SQLite** | Development database |
| **pytest** | Backend testing (69+ tests) |
| **Alembic** | Auto-applied database migrations on startup |

---

## 📋 Requirements

- **Python** 3.13 (or 3.11+)
- **Node.js** 24 (or 18+)
- **Git**
- 4 GB RAM minimum (8 GB recommended for running OCR + pipeline together)
- CPU is sufficient. GPU is optional (see [Limitations](#️-limitations))

---

## ⚙️ Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Dikshya-Sitaula/Multi-Bank-Nepali-KYC-Intelligent-Document-Processing-System.git
cd Multi-Bank-Nepali-KYC-Intelligent-Document-Processing-System
```

### 2. Create a Python Virtual Environment

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies

```bash
pip install -r backend/requirements.txt
```

Then install PyTorch (CPU build) and EasyOCR:

**Linux / macOS:**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install easyocr nepali-datetime
```

**Windows:**
```powershell
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install easyocr nepali-datetime
```

### 4. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Configure Environment Variables

```bash
# Linux / macOS
cp .env.example .env

# Windows
copy .env.example .env
```

Open `.env` and set at minimum:
```env
APP_SECRET_KEY=change-me-to-a-long-random-string   # ← CHANGE THIS
DATABASE_URL=sqlite:///./kyc_idp.db
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
CORS_ORIGINS=http://localhost:5173
```

> ⚠️ **Never commit your `.env` file.** It is already in `.gitignore`.

### 6. Set Up Bank Form Templates

The blank bank-form PDFs are not stored in the repository (licensing). Place them in `data/source_forms/` and rasterize them to generate template reference images:

```bash
# Linux / macOS
.venv/bin/python backend/scripts/rasterize_sources.py

# Windows
.venv\Scripts\python.exe backend\scripts\rasterize_sources.py
```

### 7. Create the First Admin User

```bash
# Linux / macOS
.venv/bin/python backend/scripts/create_user.py admin --role admin

# Windows
.venv\Scripts\python.exe backend\scripts\create_user.py admin --role admin
```

You will be prompted to type a password. It is **never stored in code**.

Alternatively, set environment variables before first start:
```env
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=your-secure-password
```

---

## 🚀 Running

### One-Command Start (Recommended)

```bash
# Linux / macOS
.venv/bin/python scripts/dev.py

# Windows
.venv\Scripts\python.exe scripts\dev.py
```

This starts both servers simultaneously:
- 🌐 **Frontend** → `http://localhost:5173`
- 🔧 **Backend API** → `http://localhost:8000`

Sign in with the admin credentials you created. On first start, EasyOCR downloads its models in the background — the status chip in the top bar shows **"OCR ready"** when done.

Stop with `Ctrl+C`.

### Run Servers Separately

**Backend only:**
```bash
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend
```

**Frontend only:**
```bash
cd frontend && npm run dev
```

---

## 🧪 Running Tests

```bash
# Run all tests
.venv/bin/python -m pytest -q

# Run a specific test file
.venv/bin/python -m pytest backend/tests/test_storage.py -v

# Run with output
.venv/bin/python -m pytest backend/tests/ -v
```

The test suite includes 69+ tests covering auth, storage, pipeline stages, template identification, job management, and customer profile logic.

---

## 🧪 Generate Demo Forms

Synthetic filled forms (fictional Nepali names, handwriting-style fonts, phone-photo distortion) can be generated for testing without using real personal data:

```bash
# Linux / macOS
.venv/bin/python backend/scripts/generate_demo_forms.py

# Windows
.venv\Scripts\python.exe backend\scripts\generate_demo_forms.py
```

Output goes to `data/demo_forms/`. Ground truth is stored in `data/demo_forms/ground_truth/` and is never read by the pipeline.

---

## 🗂 Project Structure

```
├── backend/
│   ├── alembic/                  # Database migration scripts
│   ├── app/
│   │   ├── api/                  # FastAPI route handlers
│   │   │   ├── auth.py           # Login, JWT, rate limiting
│   │   │   ├── documents.py      # Upload, review, fields, customers
│   │   │   ├── jobs.py           # Background job status (SSE)
│   │   │   ├── system.py         # Health check
│   │   │   └── templates.py      # Template management
│   │   ├── core/                 # Config, logging, security
│   │   ├── database/             # SQLAlchemy engine and session
│   │   ├── models/               # ORM models (Document, Field, CustomerProfile, ...)
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── preprocessing/    # OpenCV: orientation, warp, deskew, denoise, CLAHE
│   │   │   ├── quality/          # Blur, skew, glare, resolution checks
│   │   │   ├── template/         # SIFT/ORB matching, RANSAC, registration
│   │   │   ├── detection/        # Field box detection (OpenCV snapping)
│   │   │   ├── ocr/              # EasyOCR English + Nepali
│   │   │   ├── checkbox/         # Ink fill ratio detection
│   │   │   ├── extraction/       # Field value normalisation + customer sync
│   │   │   └── storage/          # File validation and safe storage
│   │   └── workers/              # Background job queue and worker thread
│   ├── scripts/
│   │   ├── create_user.py        # Admin user creation
│   │   ├── rasterize_sources.py  # PDF → template page images
│   │   ├── generate_demo_forms.py# Synthetic test form generator
│   │   ├── propose_templates.py  # Auto-propose field boxes for a new bank
│   │   ├── build_template.py     # Compile review_edits.yaml into template.json
│   │   ├── identify_selftest.py  # Template identification self-test
│   │   ├── debug_pipeline.py     # Pipeline debug runner
│   │   └── check_env.py          # Environment validation report
│   └── tests/                    # pytest test suite
│
├── config/
│   ├── app.yaml                  # All CV pipeline parameters (no hard-coding)
│   ├── fields.yaml               # Field vocabulary (all supported field IDs)
│   ├── label_keywords.yaml       # OCR label matching keywords
│   └── source_forms.yaml         # Source PDF registry
│
├── templates/
│   ├── laxmisunrise/             # Laxmi Sunrise Bank template
│   ├── machhapuchhre/            # Machhapuchchhre Bank template
│   ├── nicasia/                  # NIC Asia Bank template
│   └── nabil/                    # Nabil Bank (template in progress)
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx     # Stats and job overview
│       │   ├── Upload.tsx        # Document upload
│       │   ├── Documents.tsx     # Document list
│       │   ├── Review.tsx        # Field review and verification
│       │   ├── VisionLab.tsx     # CV pipeline inspector
│       │   └── Search.tsx        # Customer profiles and document search
│       ├── components/ui.tsx     # Shared UI components
│       └── lib/
│           ├── api.ts            # Backend API client + type definitions
│           └── utils.ts          # Shared utilities
│
├── data/
│   ├── source_forms/             # Original blank bank PDFs (not in git)
│   └── demo_forms/               # Generated synthetic test forms
│
├── assets/                       # Fonts and name pools for demo generation
├── reports/                      # Measured results (environment, quality, identification)
├── docs/SPEC.md                  # Full project specification
├── scripts/dev.py                # One-command dev launcher
├── .env.example                  # Environment variable template
└── pytest.ini                    # pytest configuration
```

---

## 🌐 API Docs

The interactive API documentation (Swagger UI) is available at:

```
http://localhost:8000/api/v1/docs
```

### Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Log in and get a JWT token |
| `POST` | `/api/v1/documents` | Upload a document |
| `GET` | `/api/v1/documents` | List all documents |
| `GET` | `/api/v1/documents/{id}` | Get document details and all fields |
| `POST` | `/api/v1/documents/{id}/process` | Re-trigger processing |
| `PATCH` | `/api/v1/fields/{id}` | Edit an extracted field value |
| `POST` | `/api/v1/fields/{id}/verify` | Mark a field as verified |
| `GET` | `/api/v1/customers` | List customer profiles with search and filter |
| `GET` | `/api/v1/documents/{id}/export` | Export as `?format=json` or `?format=csv` |
| `GET` | `/api/v1/health` | System health and component status |

---

## 📸 Screenshots

### Document Review
The review page shows the aligned document image with coloured confidence boxes, and the field inspector panel where extracted values are immediately visible without clicking.

### Customer Profiles Registry
The Search page shows all scanned customers with name, account number, address, email, phone and status — no clicking required to see key details.

### Vision Lab
Inspect every CV pipeline stage (preprocessing, identification, registration, OCR) with before/after images, timing breakdowns and live parameter re-runs.

---

## 📊 Measured Performance

Results from 160 simulated phone captures (seed 1234, 4 distortion levels) on CPU:

| Distortion Level | Correct Identification | Median Registration Error | p95 Max Error |
|---|---|---|---|
| None | 40 / 40 | 0.19 px | 1.0 px |
| Light | 40 / 40 | 0.29 px | 1.33 px |
| Medium | 40 / 40 | 0.39 px | 3.02 px |
| Strong | 40 / 40 | 0.48 px | 1.85 px |
| **All** | **160 / 160 (100%)** | **0.35 px** | **1.81 px** |

Non-form pages correctly rejected: **10 / 10**

**Processing time (CPU):**
- Laxmi Sunrise (4 pages): ~70 s
- Machhapuchchhre (3 pages): ~46 s
- NIC Asia (5 pages): ~90 s
- Average OCR confidence: **74.2%**

> These results are from simulated captures. Real phone photo accuracy at Checkpoint C is TBD.

---

## ⚠️ Limitations

- **No YOLO model trained yet** — only pre-enrolled template forms are supported. Documents that don't match any template are marked "Unidentified".
- **OCR accuracy**: Phone numbers, ward numbers and place names read well. Boxed date fields (e.g. DOB), PAN-style boxed numbers and letter-cell fields are read poorly by EasyOCR.
- **Synthetic test data only** — accuracy on real handwritten forms is unknown until real samples are tested.
- **NIC Asia template** was generated by auto-proposal and has not been reviewed by hand.
- **CPU only** — processing takes 15–25 s per page (mostly OCR). GPU support requires a CUDA 12.x driver update.
- **Development-grade security** — JWT tokens are stored in the browser, SQLite database. Not production-ready without further hardening.
- **Single worker thread** — concurrent document processing is not supported to stay within RAM limits.

---

## 🗺 Roadmap

| Phase | Status |
|---|---|
| ✅ Inspect and plan | Done |
| ✅ Backend foundation (API, auth, jobs, storage) | Done |
| ✅ Preprocessing + quality + template identification | Done |
| ✅ Template enrollment (Laxmi, Machhapuchchhre, NIC Asia) | Done |
| ✅ Customer profiles registry + review UI improvements | Done |
| 🔄 Template Studio UI + Nabil template | In progress |
| ⏳ Synthetic data engine (Phase 5) | Not started |
| ⏳ YOLO field detector training (Phase 7) | Not started |
| ⏳ HTR / handwriting recognition (Phase 8) | Not started |
| ⏳ Evaluation and testing pass | Not started |

---

## 🤝 Contributing

This is a final-year academic project. Contributions, suggestions and issue reports are welcome.

1. Fork the repository
2. Create your branch: `git checkout -b feat/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to your branch: `git push origin feat/your-feature`
5. Open a Pull Request

---

## 👥 Team

| Name | Role |
|---|---|
| **Dikshya Sitaula** | Project Lead |
| **Rishu Prajapati** | Backend & CV Pipeline |

---

## 📄 Further Reading

- [`docs/SPEC.md`](docs/SPEC.md) — full technical specification
- [`PROGRESS.md`](PROGRESS.md) — phase-by-phase progress log
- [`reports/`](reports/) — measured results and environment reports
- [`config/app.yaml`](config/app.yaml) — all CV pipeline parameters explained

---

## 📜 License

This project is for academic and educational purposes.

---

<div align="center">
Made with ❤️ for Nepali banks · Final Year Computer Vision Project
</div>
