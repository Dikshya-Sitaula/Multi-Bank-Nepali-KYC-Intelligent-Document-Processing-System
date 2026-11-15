# Environment report

Generated: 2026-11-15T14:53:53

## System

- OS: Windows-11-10.0.26200-SP0
- Python: 3.13.9 (C:\Users\nitro\Desktop\KYC app\.venv\Scripts\python.exe)
- CPU: AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD
- CPU cores (logical): 12
- RAM: 7.2 GB
- Compute backend: cuda-driver-only (torch CUDA not active)
- GPU: NVIDIA GeForce RTX 3050 Laptop GPU (4.0 GB, via nvidia-smi)
- Tesseract binary: NOT FOUND (optional engine disabled)

## Python packages

| Module | Purpose | Status |
|---|---|---|
| `fitz` | PyMuPDF (PDF rasterization) | OK 2.1 |
| `cv2` | OpenCV | OK 5.0.0 |
| `numpy` | NumPy | OK 2.5.4 |
| `PIL` | Pillow | OK 13.0.0 |
| `skimage` | scikit-image | OK 0.26.0 |
| `yaml` | PyYAML | OK 6.0.3 |
| `fastapi` | FastAPI | OK 0.163.0 |
| `sqlalchemy` | SQLAlchemy | OK 2.1.8 |
| `alembic` | Alembic | OK 1.20.1 |
| `torch` | PyTorch | MISSING (ModuleNotFoundError) |
| `ultralytics` | Ultralytics YOLO | MISSING (ModuleNotFoundError) |
| `easyocr` | EasyOCR | MISSING (ModuleNotFoundError) |

## Recommendations

- An NVIDIA GPU exists but PyTorch CUDA is not active. Install the CUDA build of torch before training (see docs/MODEL_TRAINING.md).
