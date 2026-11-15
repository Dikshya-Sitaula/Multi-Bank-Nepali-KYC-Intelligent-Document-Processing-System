# PROJECT SPECIFICATION
## Multi-Bank Nepali KYC Intelligent Document Processing System

> This is the complete original brief for the project, preserved verbatim so that any
> future session (human or AI) can re-read the full requirements. `CLAUDE.md` holds the
> condensed working rules; `PROGRESS.md` holds the current state.

---

# ROLE AND MISSION

You are the lead software engineer, computer-vision engineer and ML engineer for a final-year university Computer Vision project. I am a student and must be able to explain every component in a viva, so keep the code clean, modular and commented, and write documentation that explains WHY each part exists.

Build a complete, professional, end-to-end system that reads photographed or scanned **Nepali bank KYC forms from several banks**, extracts structured data, lets a bank employee review and correct it, stores it, and shows honest evaluation results. The system must work on the real uploaded documents and use real trained models. Nothing in it may be faked.

The system's computer-vision core is:

**OpenCV** (preprocessing, template registration, checkbox reading) + **YOLO** (field detection) + **OCR/HTR** (English and Nepali text, including a custom-trained handwriting recognizer) + **structured extraction and validation** + **honest model evaluation**.

# 1. NON-NEGOTIABLE RULES

1. **No fake data anywhere.** No hard-coded OCR results, names, addresses, coordinates, detections, confidences, dashboard numbers, search results, metrics or charts. Everything shown comes from uploaded files, OpenCV, YOLO, OCR, the database, config files or stored experiment results.
2. **No hard-coded form layout in code.** Form structure lives only in data files: `config/fields.yaml` (the field vocabulary) and `templates/<template_id>/template.json` (each bank form). Adding a new bank form must need only a new template folder plus (optionally) retraining, never pipeline code changes.
3. **No pretending.** If model weights are missing, the app still starts and shows a clear banner such as "YOLO model not loaded. Upload and UI work, but real field detection needs trained weights." A `MOCK_CV=true` env var may exist for UI development only, defaults to false, and when on every screen shows a visible MOCK banner. Never present simulated output as model output.
4. **No invented numbers.** Every accuracy, mAP, CER, timing, dataset size or count shown anywhere comes from a stored real run. If it does not exist yet, show "Not available yet". An empty database shows zeros.
5. **Honesty about limits.** If Nepali handwriting recognition is weak, or YOLO is weak on a class, or the real-handwriting test is worse than the synthetic one, show the true numbers and say so in the docs and UI.
6. **Ground truth is never used at inference.** It is used only to generate labels and to evaluate.
7. **Privacy.** Only fictional data. Never download or use real people's photos or documents. Do not log OCR text by default. Uploaded documents are served only through authenticated endpoints, never as public static URLs. Document that a real bank deployment would need much stronger security.
8. **Do not overwrite source files.** The original PDFs in `data/source_forms/` are read-only inputs. All derived files go elsewhere.
9. **Verify, don't assume.** My notes about the forms in section 5 come from a quick look. Open and inspect every PDF yourself and trust what you see over my notes. Verify at runtime that every library, language pack and font you plan to use actually works on this machine.

# 2. WORKING PROTOCOL (important)

**Be autonomous.** Work through the phases in section 18 in order without waiting for me, finishing and testing each one before starting the next. Stop and ask me ONLY at these three human checkpoints:

- **CHECKPOINT A (after Phase 4):** I review the auto-proposed field boxes for each template in Template Studio, fix mistakes, and approve. Wrong labels ruin the model, so this review is essential. Tell me exactly how long it should take and what to look for.
- **CHECKPOINT B (before Phase 7 training):** Report the detected hardware (GPU/CPU), the estimated training time for the chosen configuration, and offer: (1) train locally, (2) a ready-to-run Google Colab notebook plus a packed dataset zip so I can train there and copy the weights back. Wait for my choice.
- **CHECKPOINT C (before final evaluation):** Tell me how to collect the real handwritten test forms (see section 10.9) and wait until I say they are ready or say to skip. If I skip, the final report must clearly say the real-handwriting test was not done.

**Persistence across sessions** (my usage limit may end a session mid-way):
- First thing: write `CLAUDE.md` in the project root containing sections 1, 2, 3 and 7 of this prompt in condensed form, plus run commands. Also save this entire prompt to `docs/SPEC.md`.
- Maintain `PROGRESS.md`: phases done, in progress, next step, decisions made, known issues, exact commands to resume. Update it after every meaningful step.
- Commit to git after every phase with a clear message. Add a proper `.gitignore` (datasets, weights, uploads, node_modules, venv, `.env`).
- On start of any session, read `CLAUDE.md` and `PROGRESS.md` and continue from where you stopped.

**Context hygiene:** do not print huge files or long logs into the chat. Write logs and reports to files and show short summaries. Keep each phase report to: what was built, files changed, how to run, real results, what remains, limitations.

**Quality gates:** after each phase run its tests and a real smoke test. Do not move on while the phase is broken.

# 3. THE PROBLEM AND THE SOLUTION

**Problem.** During bank customer onboarding in Nepal, customers fill a paper KYC form. An employee then retypes every field into the bank system. This is slow and error-prone, forms differ by bank, handwriting varies, and old paper files are hard to search.

**Solution.** The employee uploads photos or scans of the form pages. The system identifies which bank form it is, straightens and cleans each page, finds every field, reads the text (English and Nepali), reads checkboxes, crops photo, signature and thumbprints, validates everything, and presents it beside the original image with confidence scores. The employee reviews only the uncertain fields, corrects, verifies and saves. Records are then searchable and exportable.

**Out of scope (state this in the UI and docs):** identity verification, face or signature matching, sanctions/AML screening, document authenticity checks.

# 4. END-TO-END PIPELINE (must be reflected in real code)

```
Upload (images / PDF, 1..N pages) -> controlled storage (original kept untouched)
 -> PAGE QUALITY CHECK (blur, resolution, skew, glare) with warnings
 -> OPENCV PREPROCESSING: orientation, document boundary detection, perspective
    correction, deskew, resize, denoise, contrast (CLAHE), optional threshold
    (every step configurable, handwriting must not be destroyed; keep debug images)
 -> TEMPLATE IDENTIFICATION per page: which bank form + which page number
    (feature-matching against enrolled template pages, e.g. ORB/SIFT + RANSAC homography,
     with a confidence; "unknown form" is a valid, handled outcome)
 -> TEMPLATE REGISTRATION: homography aligns the page to the template canvas
 -> YOLO FIELD DETECTION on the aligned page: class, bbox, confidence
 -> RESOLVE each detection against the template (which question/option list/table row/
    applicant number it belongs to)
 -> CROP each detection, route by field type:
      text / boxed_chars -> OCR/HTR -> clean + normalize -> validate
      checkbox_group     -> OpenCV finds the squares, measures ink fill -> selected option(s)
      visual             -> photo / signature / thumbprint / map: crop + store, no OCR
 -> field status: auto_accepted | needs_review | unreadable | empty
 -> merge pages into one document record
 -> human verification in the UI -> database -> search / view / edit / export / reprocess
```

Why a template-identification step: YOLO learns "what a field looks like"; the template tells the system "which bank form and which question this is". This is what makes multi-bank support possible and extensible.

# 5. INPUT FORMS (verify all of this yourself)

Rasterize PDFs with PyMuPDF at 300 DPI (do not require poppler). Do NOT rely on PDF text layers (some use legacy Nepali fonts like Preeti and extract as garbage).

| Template id | Source file | Pages (verify) | Notes from a quick look |
|---|---|---|---|
| `nicasia` | NIC_ASIA_KYC_Update_Individual.pdf | about 5 | KYC update form. Page 1: date, branch, DP ID / Client ID cells, name in block-letter cells, DOB B.S./A.D. in cells, PAN, nationality, gender, citizenship no / issue district / issue date, email, national ID, married yes/no, 16-row family member name table in letter cells, "Recent Photo" box. Page 2: current and permanent address, bank account details, occupation checkboxes, business type, organisation, designation, income-range checkboxes. Page 3: guardian details (minor only), thumbprints, guardian signature, NRN section. Page 4: location map, distance, customer thumb impression (right/left), customer signature, office-use area. Page 5: Nepali self-declaration with many yes/no (छ/छैन) boxes, PEP and beneficial-owner tables. |
| `laxmisunrise` | Laxmisunrisebank-Individuals.pdf | about 4 | Individual KYC. Photo box, name, DOB (B.S. and A.D. cells), nationality, sex, education, PAN, 3-column address table (permanent / present / mailing), identification details (citizenship, others, guardian, minor, passport, NID), family table, source-of-income checkboxes, 3-row occupation table, annual transaction, yes/no questions, other-bank accounts, foreign-national block, landlord, location map, nearest landmark, declaration with signature and right/left thumbprints. |
| `machhapuchhre` | Machapuchre_update_form_personal.pdf | about 3 | KYC update and dormant account form. Photo, boxed date and customer ID and account number cells, minor/major, name, dormant yes/no, DOB, gender, marital status, nationality, education, social-media IDs, address table (permanent / current / local contact), phone/mobile/email, two location maps, identification table (7 ID types), related-parties table, due-diligence checkbox groups, income, turnover, transaction-volume checkbox columns, PEP/FATCA declarations, signature, thumb impression, bank-use-only block. |
| `nabil` | nabil_kyc.pdf | about 8 | Account opening form (individual-joint). **Low image quality**, so do not trust it for training. Joint Applicant 1 and Joint Applicant 2 sections repeat the same fields (applicant number must come from the template, not from YOLO). Letter-cell name boxes, many underline text fields, family table, occupation blocks, location maps, declarations, specimen signature + thumb + photo page, introducer and bank-use page. |
| `globalime` (optional) | any clean Global IME blank I add later | 4 | Individual KYC with customer-ID cells, Nepali and English name rows, marital/gender/purpose checkboxes, permanent and present address blocks, passport/citizenship/PAN, employment checkboxes, bank-use page with signatures. |

**Image-quality triage (do this first):** measure resolution, sharpness (Laplacian variance) and contrast for every rasterized page and write `reports/source_quality.md`. Rules:
- Clean forms (expected: nicasia, laxmisunrise, machhapuchhre) are the **training templates**.
- Low-quality forms (expected: nabil) are NOT used to generate training data. Upscale and enhance them carefully, annotate them for **evaluation only**, and use them as the **held-out unseen-template experiment** (section 15). If after enhancement Nabil looks clean enough, say so and let me decide.

If any PDF is missing or unreadable, tell me exactly what is missing and continue with the others.

# 6. TECHNOLOGY STACK

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, SQLite (URL from env; PostgreSQL-ready) |
| CV | OpenCV, NumPy, Pillow, PyMuPDF (PDF), scikit-image if useful |
| Detection | Ultralytics YOLO, lightweight model (yolo11n or yolov8n; configurable, document how to switch to s/m) |
| OCR engines (pluggable) | EasyOCR (English + Nepali), Tesseract (eng+nep, optional if installed), **custom CRNN-CTC handwriting model trained by us** (PyTorch), optional TrOCR for English |
| Jobs | DB-backed job queue + worker thread/process, progress via Server-Sent Events with polling fallback |
| Auth | JWT, roles `admin` and `employee`, audit log |
| Frontend | React + Vite + TypeScript, Tailwind CSS, shadcn/ui, lucide-react, React Router, TanStack Query + TanStack Table, react-hook-form + zod, Recharts, react-zoom-pan-pinch with an SVG overlay for boxes, a command palette |
| Tests | pytest, Vitest + React Testing Library, Playwright (responsive screenshots at 6 widths) |
| Tooling | Windows/macOS/Linux compatible. Provide `scripts/dev.py` (or Makefile + npm scripts) to start backend and frontend with one command. No dependency that cannot be installed with pip/npm alone unless clearly optional. |

# 7. REPOSITORY STRUCTURE (improve if needed, keep these separations)

```
backend/app/{api,core,models,schemas,services,workers,database}
  services/{preprocessing,quality,template,detection,ocr,checkbox,extraction,storage,evaluation,datasets}
backend/scripts/{rasterize_sources,propose_templates,generate_synthetic_data,validate_dataset,
                 train_yolo,train_htr,evaluate,make_real_test_kit,check_env,pack_for_colab}.py
config/{fields.yaml, app.yaml}
templates/<template_id>/{pages/page_N.png, template.json, source_info.json}
assets/{fonts, name_pools, address_pools, photos_procedural, ink_and_paper_textures}
data/{source_forms, synthetic, real_test, htr_lines}
dataset/{images,labels}/{train,val,test} + data.yaml
models/{yolo, htr}   uploads/   outputs/   reports/   docs/   tests/   notebooks/
frontend/src/{components,pages,layouts,hooks,services,types,utils,i18n}
.env.example   README.md   CLAUDE.md   PROGRESS.md
```

# 8. CONFIGURATION-DRIVEN DESIGN

## 8.1 `config/fields.yaml`: the shared field vocabulary

One **shared semantic vocabulary** across all banks, so one YOLO model serves every template. Each entry: `id`, `display_name`, `yolo_class`, `field_type` (`text`, `boxed_chars`, `checkbox_group`, `visual`), `language` (`eng`, `nep`, `digits`, `mixed`), `ocr` (bool), `validation` (named rule), `required`, `section` (UI grouping), `priority` (P1/P2/P3).

Scope control (important, keeps the project achievable):
- **P1 (must work):** name (Nepali, English, boxed block letters), date of birth (B.S., A.D., boxed), gender, marital status, nationality, citizenship number / issue date / issue district, PAN, passport number, national ID number, phone, mobile, email, permanent and current address parts (province, district, municipality, ward, tole/street, house no), occupation, employer/organisation, designation, income range, source of income, family member names, person photo, signature, left and right thumbprints, location map.
- **P2 (should work):** PEP / criminal / beneficial-owner / FATCA yes-no groups and their detail fields, bank-account details, landlord details, nearest landmark and distance, education.
- **P3 (nice to have):** bank-use-only block, introducer details, rare fields.
Train on P1+P2 first. Keep the total class count to roughly 60-90; merge long-tail items rather than inventing hundreds of classes. Do not fabricate a class for a region that does not exist on any enrolled form.

## 8.2 `templates/<id>/template.json`

Contains: template id, bank name, form name, language(s), page count, per-page canvas size and reference image, and a list of **regions**: `field_id` (vocabulary reference), normalized bbox, `applicant_index` (for joint forms), `row_index` (for tables), `group_id`, `checkbox_options` (ordered option ids with their individual square boxes and printed labels), `cell_count` (for boxed-letter fields), `printed_prefill` (true for text printed on the blank form, which must not be treated as handwriting). Also store keypoint/feature data needed for template identification (generated, not hand-written).

Business logic reads only these files. A future developer adds a form by dropping in a PDF, enrolling it, generating data and retraining.

# 9. TEMPLATE ENROLLMENT: AUTO-ASSISTED ANNOTATION

I must not have to draw hundreds of boxes by hand. Do this:

1. **Rasterize** each source PDF to `templates/<id>/pages/page_N.png` (300 DPI) and keep the PDF as the source of truth.
2. **Auto-propose regions** (`propose_templates.py`):
   - If the PDF has vector drawings, extract rectangles/lines with PyMuPDF to find input boxes, cell rows, table cells, checkboxes and signature/thumbprint/photo/map frames.
   - On raster pages, use OpenCV (line detection, contours, morphology) to find rectangles, letter-cell strips, underline fields and small squares (checkboxes).
   - OCR the printed labels near each candidate (English and Nepali) and match them against the vocabulary to suggest a `field_id`.
   - Also **look at the page images yourself** (you can view images), draft or correct the region list, render an **overlay PNG** with numbered, colour-coded boxes and labels, inspect it, and fix errors. Iterate until the overlay looks right on every page.
3. Mark regions that are printed prefill (for example a pre-printed DP ID or a pre-printed branch name) so the generator does not overwrite them and YOLO is not trained to treat them as handwriting.
4. **Template Studio** (frontend page, section 14): a polished editor to review and fix the proposals: draw, move and resize boxes, change field class, define checkbox options and table rows, and view the overlay. It saves `template.json`. Also support importing/exporting YOLO-format labels so CVAT can be used as an alternative.
5. Run a **template self-test**: identification must pick the right template and page for every rasterized page, including after simulated phone-photo distortion.

This is **CHECKPOINT A**: after the proposals look good to you, tell me and I review in Template Studio.

# 10. SYNTHETIC DATA ENGINE (the heart of model quality)

Goal: many realistic filled, photographed-looking forms with **exact automatic labels**, for every training template. No watermarks. No real people.

## 10.1 Scale presets (config + CLI)

`smoke` (about 10 identities per template, for pipeline testing), `dev` (about 80), `full` (about 300+). Default to `dev` for development, and say clearly which preset the final model used. Seeds are configurable and recorded for reproducibility.

## 10.2 Identity generator

For each fictional customer generate consistent data: Nepali-script name and a consistent English transliteration, father/mother/grandfather/spouse/children names, DOB in B.S. and A.D. (use a correct B.S. conversion library; verify it), gender, marital status, citizenship number / issue date / issue district, PAN, passport, national ID, Nepal-format phone and mobile numbers, email, province/district/municipality/ward/tole/house number (use real administrative names from data pools stored in `assets/`, not in code), occupation, employer, designation, income range, source of income, landlord, nearest landmark and distance, yes/no declarations (mostly "No"; keep realistic proportions), and optional bank account details. Save a `ground_truth.json` per identity, **separate from the images**.

Make the data realistic and varied: some fields empty, optional fields skipped, abbreviations, mixed English and Nepali entries, Devanagari digits in some fields and ASCII digits in others, occasional spelling variants.

## 10.3 Handwriting renderer (realistic variety and "shades")

Render values into the template regions using **many writer styles**. A writer style is a bundle of: font (handwriting-like Devanagari and Latin fonts; survey and download open-licensed fonts such as Kalam and other handwriting fonts, record each font's licence in `assets/fonts/LICENSES.md`, and allow me to drop extra fonts into `assets/fonts/`), size, slant, baseline wobble, per-character jitter in position/size/rotation, letter spacing, stroke width via morphology, pressure variation, ink colour and **shade** (blue ballpoint, dark blue, black, gel black, faded blue, grey pencil, with opacity variation, uneven ink flow, light bleed and slight texture), plus handwriting neatness. Sample a writer style per customer and add field-level variation, so the dataset contains many "different people".

Be honest in the docs that font-based synthetic handwriting is cleaner and less varied than real handwriting, and that Devanagari handwriting fonts are limited; the per-character distortions and the real test set exist to address and measure this.

Field-type handling:
- `boxed_chars`: one character per cell, centred imperfectly, sometimes overflowing slightly.
- Underlined and table fields: text sitting on the line, sometimes crossing it, sometimes slightly overlapping borders.
- Checkboxes: hand-drawn tick marks, crosses and filled marks, sometimes overshooting the square, sometimes ambiguous (light marks), correct one-of-many or multi-select behaviour per question.
- Occasional strike-throughs, overwriting and corrections.
- Signature: procedurally generated cursive-like strokes in varied ink shades. Thumbprint: procedurally generated ridge-pattern ink blobs of varied darkness. Do not fake real people's biometrics.
- Person photo: **procedurally generated passport-style avatar portraits** (shapes, gradients, backgrounds). Do not download photos of real people. If I place my own consenting photos in `assets/photos_user/`, use those too.
- Never write over printed-prefill regions.

## 10.4 Phone-photo simulation (separate step)

Create "captured" versions: perspective warp, rotation, partial shadows, uneven lighting, glare, blur (motion and defocus), sensor noise, JPEG compression, scale changes, background around the page (desk/table textures), page curl or fold lines, slight crop. Realistic, never so strong that handwriting is unreadable. Keep the clean version too.

## 10.5 Labels

The generator knows exactly where it wrote each value, so it emits YOLO-format labels automatically, transformed through every geometric distortion. It also writes per-field crops metadata (for training the HTR model) and keeps `ground_truth.json` mapping.

## 10.6 Splits and leakage prevention (critical)

Split by **customer identity** into train/val/test (for example 70/15/15) BEFORE any augmentation, per template. Different augmented copies of one identity must never be in different splits. Write a `reports/leakage_check.md` produced by code that proves no identity appears in two splits. Also forbid reusing the same writer style across test and train where feasible (hold out some writer styles and fonts for test), so the test measures generalization to new "writers".

## 10.7 Validation script

`validate_dataset.py` checks missing images/labels, malformed YOLO lines, invalid class ids, boxes outside the image, empty annotations, class distribution, split distribution; writes `reports/dataset_summary.md` and saves random sample images with boxes drawn so I can visually confirm labels are correct. Train only if validation passes.

## 10.8 HTR line dataset

From the same generator, export **field-crop text images with their exact text** into `data/htr_lines/` (English, Nepali, digits, mixed; boxed and free-form), split by identity like above. This trains the custom OCR model.

## 10.9 Real handwritten test kit (for CHECKPOINT C)

`make_real_test_kit.py` produces: (1) printable PDFs of the blank forms; (2) a printable sheet of **fictional identity cards**, each listing the exact values to copy by hand; (3) `data/real_test/ground_truth` pre-filled from those identity cards. Friends copy the values by hand into the printed forms and I photograph them with a phone. Because the values are known in advance, I never need to type ground truth. Provide a script to ingest the photos. Real-test forms are **never used for training the detector or the OCR**, and results are always reported separately from synthetic results.

# 11. YOLO TRAINING

- `train_yolo.py`: validate dataset, load a pretrained lightweight model, train with configurable epochs, image size (default about 1024; fields are small on a full page, allow up to 1280), batch, device, patience; save weights, `results.csv`, curves, PR curves, confusion matrix and per-class metrics into `models/yolo/<run_id>/` and register the run in the database.
- `check_env.py`: detect GPU (CUDA/MPS) or CPU, recommend settings, and give an honest time estimate.
- `pack_for_colab.py` + `notebooks/train_colab.ipynb`: zip the dataset and generate a ready-to-run notebook, for the case where the laptop has no GPU.
- Use genuine Ultralytics training augmentations only. Source images are never modified.
- Report real per-class precision, recall, mAP50, mAP50-95, plus a real confusion matrix.

# 12. OCR / HTR

## 12.1 Abstraction

`OCREngine` interface: `process_text_crop(image, language, field_type) -> {text, confidence, language, engine, raw}`. Independent of YOLO. Engines selectable by config and per field type; the UI can run the same crop through several engines for comparison.

## 12.2 Crop preprocessing

Per-field: remove form lines and cell borders for boxed fields (morphological line removal), upscale small crops, adaptive binarize only when it helps, pad, normalize contrast. For `boxed_chars`, optionally segment per cell and read per character. Keep preprocessing configurable per field type.

## 12.3 Custom handwriting recognizer (trained by us)

Train a **CRNN with CTC loss** (PyTorch, CNN + BiLSTM, character set = ASCII letters/digits/punctuation + Devanagari characters and digits, with correct handling of Devanagari conjuncts/matras by treating them as Unicode code points) on `data/htr_lines/`. Provide `train_htr.py` with configurable size, epochs and device, CPU-feasible small configuration, and GPU/Colab option. Compare **three engines** on identical test crops: EasyOCR, Tesseract (if available), and the custom CRNN, per language and field type, on both synthetic-test and real-test data. Choose the default engine per field type from these real results, not from assumption. Report honestly that a model trained on synthetic handwriting may not generalize to real handwriting, and measure that gap.

## 12.4 Nepali

Treat Nepali printed text, Nepali handwriting and English as different cases. If Nepali handwriting accuracy is poor, say so with numbers and keep the interface open for a stronger model. Do not hide errors.

## 12.5 Checkbox reader

`services/checkbox`: find the squares inside a detected group crop (contours, aspect ratio), compute ink fill ratio relative to the empty-box baseline from the template, decide selected / not selected / ambiguous with a confidence, and map to option ids using `template.json`. Evaluate it separately.

## 12.6 Normalization and validation

Raw OCR text is always preserved (`raw_ocr_text`) beside `normalized_value`. Rules: Devanagari to ASCII digit conversion for numeric fields, phone (10 digits, Nepal mobile pattern), email, B.S./A.D. dates (never silently change ambiguous values; flag them), citizenship number (keep separators), PAN (digits), names (whitespace cleanup only), income-range option mapping. Field status: `auto_accepted` (confident and valid), `needs_review`, `unreadable`, `empty`. A low-confidence value is never auto-verified.

# 13. BACKEND

## 13.1 Database (relational, not one JSON blob)

`users`, `form_templates`, `template_pages`, `template_regions`, `documents` (with `template_id`, status, timings), `pages` (original path, processed path, quality metrics, template page number, registration confidence), `processing_jobs` (QUEUED, PREPROCESSING, IDENTIFYING, DETECTING, OCR, STRUCTURING, COMPLETED, FAILED, with per-stage timings), `field_detections` (class, bbox, confidence, page), `extracted_fields` (field_id, applicant_index, row_index, raw_text, normalized_value, detection_confidence, ocr_confidence, engine, status, verified_by, verified_at), `field_edits` (history), `models` (registered YOLO/HTR weights with metadata), `training_runs`, `evaluation_runs`, `evaluation_results`, `dataset_builds`, `audit_log`. Use Alembic migrations.

## 13.2 API (clean REST, typed schemas)

Auth (`/api/auth/*`), documents (upload, list with server-side pagination/sort/filter, detail, pages, fields, process, reprocess, export JSON/CSV/XLSX, delete), fields (patch, verify, bulk verify), search, jobs (status, SSE stream), templates (list, detail, regions CRUD, identify-test), pipeline-lab (run individual preprocessing steps with parameters, run detection with thresholds, run OCR engines on a crop), datasets (build job, summary, sample browser), models (list, activate, status), training (start job, list runs, curves), evaluation (run, results, report export), dashboard stats, audit log. Version the API and document it via OpenAPI.

## 13.3 Jobs

Document processing and long tasks (dataset build, training, evaluation) run as background jobs with persisted progress. The frontend never waits on one long request.

## 13.4 Security

Upload validation (type, size, page count, magic bytes), safe filenames, files stored outside web root and served only through authenticated endpoints, parameterized DB access, secrets only in env vars, `.env.example`, rate limiting on auth, structured logging without OCR text, CORS configured explicitly.

# 14. FRONTEND: design and pages (make it look like a polished final-year product)

## 14.1 Design system

- Restrained, professional, mostly neutral palette (slate/zinc greys) with **one** accent colour. Semantic colours only for meaning (confidence and status: good / warning / error). No decorative gradients, no gimmicks, no fake placeholder data.
- Typography: Inter for Latin, Noto Sans Devanagari for Nepali (both must render correctly everywhere, including field values and the optional Nepali UI labels). 8-pt spacing grid, consistent radii, shadows used sparingly, clear visual hierarchy.
- Light and dark theme with a toggle; respects system preference.
- Reusable component library (buttons, inputs, badges, cards, data tables, dialogs, drawers, tabs, tooltips, toasts, skeleton loaders, empty states with actions, error boundaries, confirmation dialogs for destructive actions).
- Accessibility: WCAG AA contrast, visible focus, full keyboard operation, ARIA labels, no information conveyed by colour alone.
- Responsive and tested at **1920, 1440, 1024, 768, 390 and 360 px**: no horizontal page overflow; the review workspace becomes a stacked layout with a bottom-sheet field inspector on mobile; tables become card lists on small screens; touch targets at least 44 px.
- Every screen has loading, empty and error states. Everything displayed comes from the API.

## 14.2 App shell

Collapsible sidebar (Dashboard, Upload, Documents, Review Queue, Search, Pipeline Lab, Templates, Datasets, Models & Experiments, Evaluation, Audit Log, Settings), top bar with global search and a **command palette** (Ctrl/Cmd+K), user menu, theme toggle, a **system status** chip (model loaded, OCR engine, database, MOCK warning if on), and a **job tray** showing running background jobs with live progress.

## 14.3 Pages

1. **Login.**
2. **Dashboard:** KPI cards (total, processed, pending review, verified, average processing time, average field confidence), throughput over time chart, status breakdown, review-queue preview, recent documents, per-template counts, "most corrected fields" ranking, model status card. All from the database; zeros when empty.
3. **Upload:** multi-file drag-and-drop, file picker, mobile camera capture, PDF support, **drag-to-reorder page thumbnails**, per-page **quality warnings** (blur, low resolution, skew, glare) computed by the backend, detected template and page number preview with confidence (and a clear "unknown form" state), batch upload of several documents, stepper with live status (Uploading, Preprocessing, Identifying form, Detecting fields, Reading text, Structuring, Completed) and an expandable log.
4. **Documents:** server-side paginated, sortable, filterable table (status, template, date range, confidence, verified by), saved filters, bulk actions, status and template badges.
5. **Review workspace (the flagship screen):** three zones: page thumbnail rail; main viewer; field inspector. Viewer: zoom/pan/minimap, **Original / Processed / side-by-side / slider compare**, interactive bounding boxes coloured by confidence, layer toggles (by section, by status, confidence heatmap, crops), a live **confidence threshold slider**. Clicking a box selects the field; selecting a field highlights its box and scrolls the viewer to it. Inspector: fields grouped by section with editable inputs (Nepali and English), YOLO and OCR confidence bars, raw OCR versus normalized value, validation messages, checkbox groups rendering selected option with the option crop, the field crop image, "re-read with another engine" candidates, visual items gallery (photo, signature, thumbprints, location map), per-field edit history, Verify / Edit / Mark unreadable. Bulk "verify all above X%". **Keyboard flow:** J/K jump between uncertain fields, Enter verify, E edit, 1-4 toggle layers, Save & next document. Low-confidence fields clearly highlighted; nothing is auto-verified.
6. **Review Queue:** documents waiting for review, sorted by uncertainty, with estimated fields to check.
7. **Search:** query box with field selector and filters, server-side pagination, sorting, result highlighting, saved searches, export of the selection.
8. **Document detail:** summary, processing timeline with per-stage durations, pages (original/processed), all fields, edit history, audit entries, exports (JSON, CSV, XLSX), reprocess with options (engine, thresholds), delete with confirmation.
9. **Pipeline Lab (for the viva):** pick or upload a page; step through every OpenCV stage (original, grayscale, denoise, CLAHE, threshold, edges, contours/document boundary, perspective-corrected, deskewed) with **parameter sliders and live preview**; run template identification and show matched features; run YOLO with confidence/IoU sliders and class filters; browse the crop gallery; compare **OCR engines side by side** on any crop with confidence and CER if ground truth exists.
10. **Templates:** list with enrollment status, page previews, identification test, and **Template Studio** editor (draw/move/resize boxes, assign field class, define checkbox options, table rows, applicant index, printed-prefill flag, auto-propose button, overlay verification, import/export).
11. **Datasets:** launch a generation job (preset, identities, seed, writer-style settings), progress, sample browser showing images with ground-truth boxes, class distribution charts, split summary and the leakage-check result.
12. **Models & Experiments:** registry of YOLO and HTR models, active model selector, training runs with curves read from real `results.csv`, PR curve and confusion matrix images, per-class AP table, run comparison, start a training job (when hardware allows).
13. **Evaluation:** run on the test split; tabs: Detection, OCR (by language, field type, engine), Checkbox accuracy, End-to-end (field-level, document-level, % needing correction), Efficiency (time per page/document), **Generalization** (leave-one-template-out), **Synthetic versus real handwriting**, Error analysis (worst classes and a gallery of failures). Export the report as Markdown/PDF. Charts only from stored results.
14. **Audit Log** and **Settings** (thresholds, default OCR engines, preprocessing options, user management for admins, optional Nepali UI language toggle).

# 15. EVALUATION AND EXPERIMENTS (all real, all reproducible)

1. **YOLO:** precision, recall, mAP50, mAP50-95, per-class table, confusion matrix, on the held-out synthetic test split.
2. **Template identification:** accuracy over test pages and distortion levels.
3. **OCR:** CER, WER where appropriate, exact-match, per language (English, Nepali, digits) and field type, for each engine (EasyOCR, Tesseract if available, custom CRNN), on synthetic-test and real-test separately.
4. **Checkbox reading accuracy.**
5. **End-to-end:** field-level accuracy, document-level accuracy (all P1 fields correct), % of fields needing manual correction, per template.
6. **Efficiency:** time per page and per document, per stage.
7. **Generalization experiment:** train on the clean templates, test on a **held-out template** (the enhanced Nabil form, with labels used for evaluation only). Report honestly how well the shared-vocabulary YOLO transfers to an unseen bank layout.
8. **Baseline comparison:** a simple template-alignment-only extraction (fixed regions after registration, no YOLO) versus the YOLO pipeline, to justify using YOLO, evaluated under increasing distortion.
9. **Synthetic versus real handwriting gap** (after Checkpoint C).
10. **Face-presence check** on person_photo crops is optional; if included, report that the procedural avatars may not behave like real photos.

Write `reports/final_evaluation.md` from the stored results. Never write a number that was not measured. Include dataset sizes actually used, preset, seeds, hardware and training time.

# 16. TESTING

pytest for backend (upload validation, API, normalizers/validators, database, search, export, job lifecycle, auth), CV (preprocessing, perspective correction, template identification, bbox conversion, YOLO output parsing, checkbox reader, OCR output parsing), generator (labels line up with rendered text, split leakage check). Vitest + React Testing Library for upload flow, review workspace rendering and editing, search, confidence highlighting. Playwright for end-to-end and **screenshots at the six widths with an automated no-horizontal-overflow assertion**.

# 17. DOCUMENTATION

`README.md` (overview, problem, objectives, pipeline, architecture with Mermaid diagrams, stack, install on Windows/macOS/Linux, run backend, run frontend, enroll a new template, generate data, train YOLO, train HTR, run inference, evaluate, limitations, future work, privacy) and `docs/`: PROJECT_OVERVIEW, SYSTEM_ARCHITECTURE, COMPUTER_VISION_PIPELINE, TEMPLATE_SYSTEM, DATASET, ANNOTATION_GUIDE, MODEL_TRAINING, OCR_PIPELINE, EVALUATION, LIMITATIONS, PRIVACY, VIVA_CHEATSHEET (plain-English answers to likely examiner questions: why YOLO and not only template matching, why synthetic data, how leakage is prevented, why OCR is separate from YOLO, what the limitations are). Explain WHY each component exists.

# 18. PHASES (run in order, autonomously, commit after each)

1. **Inspect and plan.** Inspect the folder and PDFs, rasterize, write `reports/source_quality.md`, write `CLAUDE.md`, `PROGRESS.md`, `docs/SPEC.md`, run `check_env.py`, report the plan and risks briefly, then continue.
2. **Backend foundation:** config, DB models and migrations, auth, storage, health, job system skeleton, tests.
3. **OpenCV preprocessing + page quality + template identification and registration**, with debug visualizations and tests.
4. **Template enrollment:** `fields.yaml`, auto-proposal, overlays, Template Studio (backend endpoints and frontend editor), template self-test. **CHECKPOINT A.**
5. **Synthetic data engine:** identities, handwriting renderer, phone simulation, labels, splits, validator, HTR line export, real-test kit generator. Show sample images with boxes and a short report.
6. **Frontend foundation:** design system, shell, auth, dashboard, upload, documents list (connected to the real API as soon as it exists).
7. **YOLO training. CHECKPOINT B**, then train, register the model, record real metrics.
8. **OCR/HTR:** engines, crop preprocessing, custom CRNN training, checkbox reader, normalizers, validators; measure and select defaults from real results.
9. **Processing pipeline end to end** (job system, extraction, structuring, REST API), tested on unseen synthetic forms.
10. **Review workspace, search, document detail, export, Review Queue.**
11. **Pipeline Lab, Datasets, Models & Experiments pages.**
12. **Evaluation module and Evaluation page** (**CHECKPOINT C** for real-handwriting data), generalization and baseline experiments.
13. **Testing pass** (all suites, Playwright screenshots at six widths, fix overflow and accessibility issues).
14. **Docs and demo script:** README, docs/, VIVA_CHEATSHEET, and a step-by-step live demo script (upload an unseen form, original versus processed, form identified, boxes, click a field, crop, OCR text and confidence, correct, verify, save, search, open record, export, show evaluation).
15. **Final audit:** go through section 19 line by line and report pass/fail for each with evidence.

# 19. DEFINITION OF DONE (verify each with evidence)

- App starts cleanly with one command; backend and frontend work; database persists.
- Upload works for images and PDFs; the correct bank template and page are identified.
- Preprocessing works and the Pipeline Lab shows each stage.
- A **trained** YOLO model is loaded and real inference runs; boxes and confidences display.
- OCR works for English and Nepali through the engine abstraction; the custom CRNN is trained and compared with the other engines; limitations are reported honestly.
- Checkboxes, photo, signature, thumbprints and location map are handled.
- Fields are editable and verifiable; nothing is auto-verified; edits are audited.
- Search, export (JSON, CSV, XLSX), reprocess and delete work.
- Evaluation, generalization and baseline numbers are real and stored; the dashboard shows zeros on an empty database.
- No hard-coded customer data, detections, coordinates or metrics anywhere (grep to prove it).
- Error cases (corrupt file, wrong format, unknown form, missing model, OCR failure, no detections, timeout) are handled without crashing.
- Responsive at all six widths with no horizontal overflow; keyboard accessible.
- All tests pass; README and docs are complete; no secrets committed.
