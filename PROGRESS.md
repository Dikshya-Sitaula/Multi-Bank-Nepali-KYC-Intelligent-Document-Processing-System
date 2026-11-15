# PROGRESS.md

Last updated: 2026-11-15 (session 2)

## Resume instructions

```
Resume. Read CLAUDE.md and PROGRESS.md and continue.
```

Current branch convention: `phase-N-<slug>` merged into `main` when the phase passes.

## Phase status

| Phase | Name | Status |
|---|---|---|
| 1 | Inspect and plan | DONE (merged to main) |
| 2 | Backend foundation | DONE (merged to main) |
| 3 | Preprocessing + quality + template identification | DONE (merged to main) |
| 4 | Template enrollment (CHECKPOINT A) | IN PROGRESS |
| 5 | Synthetic data engine | not started |
| 6 | Frontend foundation | not started |
| 7 | YOLO training (CHECKPOINT B) | not started |
| 8 | OCR / HTR | not started |
| 9 | End-to-end pipeline | not started |
| 10 | Review workspace, search, detail, export | not started |
| 11 | Pipeline Lab, Datasets, Models pages | not started |
| 12 | Evaluation (CHECKPOINT C) | not started |
| 13 | Testing pass | not started |
| 14 | Docs and demo script | not started |
| 15 | Final audit | not started |

## Phase 1 log

- [x] Project folder inspected: it was empty. `data/source_forms/` did not exist.
- [x] git initialised, remote `origin` set, `main` pushed, branch `phase-1-inspect-and-plan` created.
- [x] Folder structure created per SPEC §7.
- [x] `docs/SPEC.md`, `CLAUDE.md`, `PROGRESS.md` written.
- [x] Source PDFs supplied by the user (found in Downloads) copied read-only into
      `data/source_forms/` under the expected names. Originals untouched.
- [x] Manual visual inspection of every page: `reports/form_inspection.md`.
- [x] `backend/scripts/check_env.py` -> `reports/environment.md`.
- [x] `backend/scripts/rasterize_sources.py` -> `templates/<id>/pages/page_N.png`,
      `templates/<id>/source_info.json`, `reports/source_quality.md`.
- [x] Quality metrics module + 4 passing unit tests.
- [x] `backend/requirements.txt`, `.env.example`, `config/source_forms.yaml`.

## Phase 2 log

- [x] Settings from env (`app/core/config.py`), production refuses the dev secret.
- [x] 16 relational tables (`app/models/entities.py`), UTC-aware timestamps on SQLite.
- [x] Alembic initial migration; startup runs `upgrade head`; a test fails on drift.
- [x] JWT auth (PyJWT + bcrypt), admin/employee roles, login rate limit, audit log.
- [x] Storage service: magic-byte validation, random names, traversal guard.
- [x] DB-backed job queue + worker thread, stage timings, cancel, crash recovery, SSE.
- [x] `/api/v1/health` with honest component status and banners (YOLO missing, MOCK).
- [x] `backend/scripts/create_user.py`, `scripts/dev.py` one-command launcher.
- [x] 41 pytest tests pass. Live smoke test: server start, admin login, audit entry.

## Phase 3 log

- [x] `app/services/preprocessing/`: orientation, page boundary, perspective, deskew,
      resize to 2480 px, median denoise, CLAHE on lightness, optional threshold. Every step
      configurable in `config/app.yaml`; per-step timings; debug images on request; the
      full original-to-processed transform is tracked as one 3x3 matrix.
- [x] `app/services/quality/page_check.py`: resolution, blur, skew, glare (heuristic),
      contrast warnings.
- [x] `app/services/template/`: SIFT features (cached per template page), ratio test,
      one-to-one matching, MAGSAC homography on a shortlist of 4 pages, geometric
      sanity check, documented confidence score, "unknown form" outcome; registration
      with optional ECC refinement and printed-structure overlap score.
- [x] `app/services/datasets/phone_sim.py`: procedural phone-photo simulator that
      returns the exact page-to-photo homography.
- [x] `backend/scripts/identify_selftest.py`, `backend/scripts/debug_pipeline.py`.
- [x] 69 pytest tests pass (28 new CV tests on synthetic forms, no bank PDFs needed).

**Phase 3 measured results** (`reports/template_identification.md`, seed 1234,
2 simulated phone captures per page per level, 20 template pages, 160 captures total):

| Distortion level | Correct template and page | Median registration error | p95 of max error |
|---|---|---|---|
| none | 40/40 | 0.19 px | 1.0 px |
| light | 40/40 | 0.29 px | 1.33 px |
| medium | 40/40 | 0.39 px | 3.02 px |
| strong | 40/40 | 0.48 px | 1.85 px |
| all | 160/160 (100%) | 0.35 px | 1.81 px |

- Non-form pages correctly rejected as "unknown": 10/10.
- Median timings per page on CPU: preprocessing about 1.5 s, identification about 2.1 s.
- Caveat: these are simulated captures, cleaner than many real phone photos. They are an
  upper bound until real photos are tested at Checkpoint C.
- A bug found and fixed by a test: repeated glyphs let many photo keypoints match one
  template keypoint, and RANSAC returned a degenerate homography. One-to-one matching
  fixed it.

## Decisions made

- Python venv at `.venv/` using the Anaconda 3.13 base interpreter (torch and ultralytics
  both ship 3.13 wheels).
- Auth uses PyJWT + bcrypt directly (passlib 1.7 breaks with bcrypt 5).
- No default accounts. First admin via `create_user.py` or BOOTSTRAP_ADMIN_* env.
- One worker thread only (7 GB RAM, 4 GB GPU).
- YOLO base model: `yolo11n` (configurable in `config/app.yaml`).
- SQLite for development, URL from env; PostgreSQL-ready through SQLAlchemy.

- **Triage criteria revised after measuring.** The first run used global Laplacian
  variance and RMS contrast. It wrongly failed Laxmi Sunrise (crisp vector form in light
  orange ink) and passed Nabil (JPEG artefacts inflate the Laplacian). Final criteria:
  native resolution of embedded scans (min 120 DPI; vector always passes) and ink
  contrast (median grey minus 0.1th percentile, min 80).
- **Triage result:** training templates = nicasia (scan, 144 DPI), laxmisunrise (vector),
  machhapuchhre (vector). Held-out evaluation template = nabil (scan, 69 DPI).
- Import PyMuPDF as `pymupdf` (the `fitz` name is deprecated in the installed 1.26+/2.x).

## Known issues / blockers

- Optional Global IME form not supplied; `globalime` is skipped.
- **GPU blocker for local training:** NVIDIA driver 516.40 supports CUDA 11.7 at most. No
  current PyTorch build for Python 3.13 supports CUDA 11.7, so torch is installed as the
  CPU build (2.15.0+cpu) with EasyOCR 1.7.2. Local GPU training needs a driver update
  (CUDA 12.x capable); otherwise train on Colab. To be decided at Checkpoint B.
- Machine RAM is 7.2 GB, which limits dataset generation batch sizes and EasyOCR + YOLO
  running together. Keep worker concurrency at 1.
- Tesseract is not installed; it is optional in the spec and will be treated as absent.

## Next step

Phase 4 on branch `phase-4-template-enrollment`: `config/fields.yaml` vocabulary,
auto-proposal (`propose_templates.py`), human corrections in
`templates/<id>/review_edits.yaml` built into `template.json` by `build_template.py`,
Template Studio (backend endpoints + frontend editor), template self-test.
Then stop at CHECKPOINT A.
