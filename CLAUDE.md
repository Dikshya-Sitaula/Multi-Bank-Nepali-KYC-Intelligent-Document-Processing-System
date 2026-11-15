# CLAUDE.md — working rules for this repository

Multi-Bank Nepali KYC Intelligent Document Processing System. Final-year Computer Vision
project. Full brief: `docs/SPEC.md`. Current state and resume instructions: `PROGRESS.md`.

**On every session start:** read this file, then `PROGRESS.md`, then continue from the
"Next step" there. Do not re-plan work that is already done.

## Non-negotiable rules (condensed from SPEC §1)

1. **No fake data.** No hard-coded OCR text, names, coordinates, detections, confidences,
   metrics or chart values. Everything shown comes from uploads, OpenCV, YOLO, OCR, the DB,
   config files or stored experiment results.
2. **No form layout in code.** Layout lives only in `config/fields.yaml` (vocabulary) and
   `templates/<id>/template.json`. A new bank = new template folder (+ retrain), never a
   pipeline code change.
3. **No pretending.** Missing weights -> app still starts and shows a clear banner.
   `MOCK_CV=true` exists for UI dev only, defaults false, and shows a MOCK banner everywhere.
4. **No invented numbers.** Anything not measured shows "Not available yet". Empty DB = zeros.
5. **Honesty about limits.** Report weak Nepali HTR, weak YOLO classes, synthetic-vs-real gap
   with the true numbers.
6. **Ground truth is never used at inference.** Only for label generation and evaluation.
7. **Privacy.** Fictional data only. Never real people's photos/documents. Do not log OCR text
   by default. Uploaded files are served only through authenticated endpoints.
8. **Never modify `data/source_forms/`.** Derived files go elsewhere.
9. **Verify, don't assume.** Inspect PDFs yourself; verify every library/font/language pack
   actually works on this machine before relying on it.

## Working protocol (SPEC §2)

- Work autonomously through SPEC §18 phases in order. Finish and test each before the next.
- Stop ONLY at the three human checkpoints:
  - **A** after Phase 4: user reviews auto-proposed template boxes in Template Studio.
  - **B** before Phase 7 training: report hardware + time estimate; offer local vs Colab.
  - **C** before final evaluation: real handwritten test kit collected or skipped.
- Git: one branch per phase (`phase-N-<slug>`), commit after every meaningful change with a
  clear message, merge into `main` when the phase passes its tests, push both.
  Remote: `https://github.com/Dikshya-Sitaula/Multi-Bank-Nepali-KYC-Intelligent-Document-Processing-System.git`
- Update `PROGRESS.md` after every meaningful step.
- Context hygiene: write logs/reports to files; show short summaries only.
- Quality gate: run the phase's tests and a real smoke test before moving on.

## Problem and solution (SPEC §3)

Nepali bank employees retype paper KYC forms by hand. This system takes photos/scans of a
form, identifies the bank template and page, straightens and cleans the page (OpenCV), finds
fields (YOLO), reads text (English/Nepali OCR + custom CRNN HTR), reads checkboxes, crops
photo/signature/thumbprints/map, validates, and shows everything beside the image with
confidences for human review, then stores searchable, exportable records.

Out of scope: identity verification, face/signature matching, AML screening, authenticity.

## Repository layout (SPEC §7)

```
backend/app/{api,core,models,schemas,services,workers,database}
  services/{preprocessing,quality,template,detection,ocr,checkbox,extraction,storage,evaluation,datasets}
backend/scripts/{rasterize_sources,propose_templates,generate_synthetic_data,validate_dataset,
                 train_yolo,train_htr,evaluate,make_real_test_kit,check_env,pack_for_colab}.py
backend/tests/
config/{fields.yaml, app.yaml}
templates/<template_id>/{pages/page_N.png, template.json, source_info.json}
assets/{fonts, name_pools, address_pools, photos_procedural, ink_and_paper_textures}
data/{source_forms, synthetic, real_test, htr_lines}
dataset/{images,labels}/{train,val,test} + data.yaml
models/{yolo, htr}   uploads/   outputs/   reports/   docs/   notebooks/
frontend/src/{components,pages,layouts,hooks,services,types,utils,i18n}
.env.example   README.md   CLAUDE.md   PROGRESS.md
```

## Environment on this machine (verified 2026-11-15)

- Windows 11, PowerShell. Base interpreter: Anaconda Python 3.13 (`python`).
  Project venv: `.venv/` (create with `python -m venv .venv`).
- GPU: NVIDIA GeForce RTX 3050 Laptop, 4 GB VRAM. RAM 7.2 GB, 12 logical cores.
  Node 24, npm 11. No Tesseract installed.
- Import PyMuPDF as `pymupdf` (the `fitz` name is deprecated).
- Use `.venv/Scripts/python.exe` (Windows) for every backend command.

## Run commands

```powershell
# one-time
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# environment + hardware report
.venv\Scripts\python.exe backend\scripts\check_env.py

# rasterize source PDFs and write reports/source_quality.md
.venv\Scripts\python.exe backend\scripts\rasterize_sources.py

# backend tests
.venv\Scripts\python.exe -m pytest backend\tests -q

# start backend + frontend together
.venv\Scripts\python.exe scripts\dev.py
```

(Commands for later phases are added here as the scripts are created.)
