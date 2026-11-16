# Multi-Bank Nepali KYC Intelligent Document Processing

A final-year Computer Vision project. Nepali bank staff often retype paper KYC forms by hand.
This system takes a photo or scan of a filled form and does the first pass for them: it works
out which bank's form it is, straightens the photo, finds the fields, reads the text, and
puts the result next to the page image so a person can check it before anything is saved.

It is a review tool, not an auto-approver. Nothing is marked verified until a person does it.
Identity verification, face or signature matching and fraud checks are out of scope.

## What it does

1. **Upload** one or more page images or a PDF. Blur, skew and glare are measured and
   reported before processing.
2. **Clean up the page** with OpenCV: orientation, page-edge detection, perspective
   correction, deskew, denoising and CLAHE contrast.
3. **Identify the form.** SIFT/ORB keypoints are matched against every enrolled template
   page and filtered with RANSAC. The best match gives the bank and the page number.
4. **Align and locate fields.** A homography maps the template's field boxes onto the photo,
   then each box is snapped to the real printed box found by contour and line detection.
5. **Read.** Checkbox ink ratios are measured, and English and Nepali text is read with
   EasyOCR. Values are normalised and validated.
6. **Review.** Every field is shown with its crop, raw OCR text, cleaned value and
   confidence. Fields can be edited and verified, searched in English or Devanagari, and
   exported as JSON or CSV.

Each pipeline stage saves its image, parameters and timing. The **Vision Lab** page shows
them, with before/after sliders and live re-runs when you change a parameter.

## Current state

- Fields are found by **template alignment plus OpenCV box snapping**. A YOLO field detector
  is planned behind the same interface but is **not trained yet**, and the app never labels
  anything as a YOLO result.
- Supported forms: Laxmi Sunrise, Machhapuchchhre and NIC Asia. A Nabil template is not
  finished. Adding a bank means adding a template folder, not changing pipeline code.
- All demo forms are synthetic, with fictional people. No real personal data is used.

See [Limitations](#limitations) for measured results.

## Tech stack

| Layer | Used |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic, SQLite, JWT auth |
| Computer vision | OpenCV, scikit-image, NumPy, PyMuPDF |
| OCR | EasyOCR (English and Nepali) |
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query, Recharts |
| Tests | pytest |

## Project layout

```
backend/
  app/            API, config, models, services (preprocessing, quality, template,
                  detection, ocr, checkbox, extraction, storage), background jobs
  alembic/        database migrations
  scripts/        create_user, rasterize_sources, propose_templates, build_template,
                  generate_demo_forms, identify_selftest, check_env
  tests/
config/           fields.yaml (field vocabulary), app.yaml (pipeline parameters), ...
templates/<bank>/ template.json and source info for each enrolled bank form
assets/           open handwriting-style fonts and fictional name pools for demo data
frontend/         React app
scripts/dev.py    starts backend and frontend together
reports/          measured results (environment, form inspection, template identification)
docs/SPEC.md     full project specification
```

Form layout lives only in `config/fields.yaml` and `templates/<bank>/template.json`, never
in code.

## Setup (Windows, PowerShell)

Developed and tested with Python 3.13 and Node.js 24.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install easyocr nepali-datetime
cd frontend; npm install; cd ..
copy .env.example .env
```

The blank bank-form PDFs are not in the repository. Put them in `data\source_forms\` and
rasterize them to get the template page images:

```powershell
.venv\Scripts\python.exe backend\scripts\rasterize_sources.py
```

Create the first admin user. The password is typed at the prompt and never stored in code:

```powershell
.venv\Scripts\python.exe backend\scripts\create_user.py admin --role admin
```

## Run

```powershell
.venv\Scripts\python.exe scripts\dev.py
```

Open http://localhost:5173 and sign in. API docs are at http://localhost:8000/api/v1/docs.
On first start the EasyOCR models load in the background; the status chip shows "OCR ready"
when they are done. Stop with Ctrl+C.

## Demo forms

Synthetic filled forms (Nepali and English values, handwriting-style fonts, ink colours,
phone-photo distortion) can be generated for testing:

```powershell
.venv\Scripts\python.exe backend\scripts\generate_demo_forms.py
```

They are written to `data\demo_forms\`. The matching ground truth is stored separately in
`data\demo_forms\ground_truth\` and is never read by the pipeline.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## Limitations

- No trained YOLO model yet, so only enrolled bank forms are supported.
- EasyOCR does well on phone numbers, wards, house numbers and most Nepali place names in
  the synthetic forms. It reads dates, PAN-style boxed numbers and letter-cell fields
  poorly, and some confident readings are wrong. That is why nothing is auto-verified.
- The NIC Asia template comes from automatic box proposals and has not been reviewed by
  hand. The other two were reviewed.
- Synthetic handwriting is cleaner than real handwriting. There is no real handwritten
  test set yet, so the accuracy on real forms is unknown.
- Processing runs on CPU (about 15-25 s per page, mostly OCR). The installed NVIDIA driver
  is too old for current PyTorch CUDA builds.
- Security is development grade: JWT kept in the browser and a SQLite database. A real
  deployment would need much stronger controls.

## Further reading

- `docs/SPEC.md` for the full specification
- `PROGRESS.md` for what is done, what was skipped and what is next
- `reports/` for the measurements behind the numbers above
