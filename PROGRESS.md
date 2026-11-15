# PROGRESS.md

Last updated: 2026-11-15 (session 1)

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
| 3 | Preprocessing + quality + template identification | IN PROGRESS |
| 4 | Template enrollment (CHECKPOINT A) | not started |
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
- PyTorch, Ultralytics and EasyOCR are not installed yet. The GPU (RTX 3050, 4 GB) is
  visible to the driver; the CUDA build of torch will be installed before Phase 7/8.
- Machine RAM is 7.2 GB, which limits dataset generation batch sizes and EasyOCR + YOLO
  running together. Keep worker concurrency at 1.
- Tesseract is not installed; it is optional in the spec and will be treated as absent.

## Next step

Phase 3 on branch `phase-3-preprocessing-identification`: OpenCV preprocessing steps
(each configurable, with debug images), page quality warnings, template identification
(ORB/SIFT + RANSAC homography against enrolled pages, with "unknown form"), registration
to the template canvas, tests including simulated phone-photo distortion.
