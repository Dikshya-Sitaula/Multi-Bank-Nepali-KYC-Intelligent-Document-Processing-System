# Environment report

Generated: 2026-11-16T16:12:45

## System

- OS: Linux-7.0.0-42-generic-x86_64-with-glibc2.43
- Python: 3.14.4 (/home/reesuuu/Projects/Multi-Bank-Nepali-KYC-Intelligent-Document-Processing-System/.venv/bin/python)
- CPU: unknown
- CPU cores (logical): 16
- RAM: 14.4 GB
- Compute backend: cuda
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU (5.6 GB, via torch)
- Tesseract binary: NOT FOUND (optional engine disabled)

## Python packages

| Module | Purpose | Status |
|---|---|---|
| `fitz` | PyMuPDF (PDF rasterization) | OK 2.1 |
| `cv2` | OpenCV | OK 5.0.0 |
| `numpy` | NumPy | OK 2.5.5 |
| `PIL` | Pillow | OK 13.0.0 |
| `skimage` | scikit-image | OK 0.26.0 |
| `yaml` | PyYAML | OK 6.0.3 |
| `fastapi` | FastAPI | OK 0.163.1 |
| `sqlalchemy` | SQLAlchemy | OK 2.1.8 |
| `alembic` | Alembic | OK 1.20.1 |
| `torch` | PyTorch | OK 2.15.0+cu132 |
| `ultralytics` | Ultralytics YOLO | MISSING (ModuleNotFoundError) |
| `easyocr` | EasyOCR | OK 1.7.2 |

## Recommendations

- YOLO: yolo11n or yolo11s, imgsz 1024-1280, batch 8.
- CRNN HTR: GPU training is feasible locally.
