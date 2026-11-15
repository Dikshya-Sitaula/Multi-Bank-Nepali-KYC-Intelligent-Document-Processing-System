# KYC Vision: Multi-Bank Nepali KYC Intelligent Document Processing

Final-year Computer Vision project. Upload photos or scans of a Nepali bank KYC form; the
system identifies the bank form and page, straightens the photo, aligns it to the blank
template, snaps every field box to the printed box with OpenCV, reads ticks, crops photo,
signature, thumbprints and map, reads English and Nepali text with EasyOCR, validates the
values and shows everything for human review, search and export.

**Current mode (honest):** template alignment with OpenCV box snapping. The YOLO field
detector is designed in but **not trained yet**, and nothing in the UI is labelled as a
YOLO result. Demo forms are SYNTHETIC (fictional people, procedural photos and signatures).

Full brief: `docs/SPEC.md`. Demo sprint brief: `docs/SPRINT.md`. Status: `PROGRESS.md`.

## Start the app (Windows PowerShell)

One-time setup (already done on the development laptop):

```powershell
cd "C:\Users\nitro\Desktop\KYC app"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install easyocr nepali-datetime
cd frontend; npm install; cd ..
.venv\Scripts\python.exe backend\scripts\rasterize_sources.py      # template page images from the PDFs
```

Create your login (you type the password; nothing is stored in code):

```powershell
.venv\Scripts\python.exe backend\scripts\create_user.py admin --role admin
```

Start backend and frontend with one command:

```powershell
.venv\Scripts\python.exe scripts\dev.py
```

Open http://localhost:5173 and sign in with the user you created. The first start loads the
EasyOCR English + Nepali models in the background (the status chip shows "OCR ready").
API docs: http://localhost:8000/api/v1/docs. Stop with Ctrl+C.

## Demo forms to upload

Generate them (already generated: `data/demo_forms/`):

```powershell
.venv\Scripts\python.exe backend\scripts\generate_demo_forms.py
```

| Upload these files together | Bank form |
|---|---|
| `data\demo_forms\SYNTHETIC_laxmisunrise_1\page_1.jpg` … `page_4.jpg` (or `SYNTHETIC_laxmisunrise_1.pdf`) | Laxmi Sunrise, 4 pages |
| `data\demo_forms\SYNTHETIC_machhapuchhre_1\page_1.jpg` … `page_3.jpg` | Machhapuchchhre, 3 pages |
| `data\demo_forms\SYNTHETIC_nicasia_1\page_1.jpg` … `page_5.jpg` | NIC Asia, 5 pages |
| `data\demo_forms\SYNTHETIC_strong_rotation_shadow\nicasia_page_1.jpg` | NIC Asia p1, rotated 24° with shadow |

Ground truth for each demo form is in `data\demo_forms\ground_truth\` and is never read by
the pipeline. Processing takes about 15-25 s per page on this CPU (most of it OCR).

## Demo flow

Upload (live stepper with real stage timings) → Vision Lab (every OpenCV stage image,
before/after slider, live parameter re-run, histograms, RANSAC inliers per template page,
alignment blend, box snapping) → Review (zoomable page, confidence-coloured boxes, crop,
raw OCR vs value, edit, Verify) → Search (English or Nepali) → Export JSON/CSV.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## Limitations (measured, not hidden)

- No trained YOLO model yet; fields come from template alignment + OpenCV snapping, so only
  enrolled bank forms are supported.
- EasyOCR on synthetic handwriting: phone numbers, wards, house numbers and Nepali place
  names mostly read well; dates and numbers written in letter cells read poorly; some
  confident readings are wrong, which is why nothing is ever auto-verified.
- The NIC Asia template is built from automatic proposals and has not been human reviewed
  yet (Laxmi Sunrise and Machhapuchchhre were reviewed).
- Synthetic handwriting is cleaner than real handwriting; no real handwritten test yet.
- Runs on CPU: the NVIDIA driver (516.40) is too old for current PyTorch CUDA builds.
- Security is development grade (JWT in browser storage, SQLite). A bank deployment needs
  much stronger security.
