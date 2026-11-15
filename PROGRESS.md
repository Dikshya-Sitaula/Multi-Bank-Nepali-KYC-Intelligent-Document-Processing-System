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
| 1 | Inspect and plan | IN PROGRESS |
| 2 | Backend foundation | not started |
| 3 | Preprocessing + quality + template identification | not started |
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
- [ ] `backend/scripts/check_env.py`
- [ ] `backend/scripts/rasterize_sources.py` + `reports/source_quality.md`
- [ ] `backend/requirements.txt`, `.env.example`, `config/app.yaml`

## Decisions made

- Python venv at `.venv/` using the Anaconda 3.13 base interpreter (torch and ultralytics
  both ship 3.13 wheels).
- YOLO base model: `yolo11n` (configurable in `config/app.yaml`).
- SQLite for development, URL from env; PostgreSQL-ready through SQLAlchemy.

## Known issues / blockers

- **BLOCKER (needs user):** the source PDFs are not in `data/source_forms/`. Expected files:
  `NIC_ASIA_KYC_Update_Individual.pdf`, `Laxmisunrisebank-Individuals.pdf`,
  `Machapuchre_update_form_personal.pdf`, `nabil_kyc.pdf`. Rasterization, quality triage and
  template enrollment (Phases 1, 3, 4) cannot run on real forms until they are added.
  Everything that does not depend on the PDFs continues.
- Tesseract is not installed; it is optional in the spec and will be treated as absent.

## Next step

Finish Phase 1 scripts (`check_env.py`, `rasterize_sources.py`), run them, commit, merge to
main, then start Phase 2 (backend foundation) on branch `phase-2-backend-foundation`.
