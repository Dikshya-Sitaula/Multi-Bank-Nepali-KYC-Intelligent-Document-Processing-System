"""Environment and hardware check.

WHY: the spec forbids assuming that a library, language pack or GPU exists. This script
probes the machine for real and writes reports/environment.md, so every later decision
(train locally vs Colab, which OCR engines are available) is based on measured facts.

Run:  .venv\\Scripts\\python.exe backend\\scripts\\check_env.py
"""
from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "environment.md"

PACKAGES = [
    ("fitz", "PyMuPDF (PDF rasterization)"),
    ("cv2", "OpenCV"),
    ("numpy", "NumPy"),
    ("PIL", "Pillow"),
    ("skimage", "scikit-image"),
    ("yaml", "PyYAML"),
    ("fastapi", "FastAPI"),
    ("sqlalchemy", "SQLAlchemy"),
    ("alembic", "Alembic"),
    ("torch", "PyTorch"),
    ("ultralytics", "Ultralytics YOLO"),
    ("easyocr", "EasyOCR"),
]


def probe_package(module: str) -> tuple[bool, str]:
    """Import a module and return (ok, version-or-error-name)."""
    try:
        mod = importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 - any import failure is reported
        return False, type(exc).__name__
    return True, str(getattr(mod, "__version__", "ok"))


def probe_gpu() -> dict:
    """Return GPU facts from torch if installed, else from nvidia-smi."""
    info: dict = {"backend": "cpu", "name": None, "vram_gb": None, "source": None}
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info.update(backend="cuda", name=props.name,
                        vram_gb=round(props.total_memory / 1024**3, 1), source="torch")
            return info
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            info.update(backend="mps", name="Apple Silicon", source="torch")
            return info
    except Exception:  # noqa: BLE001
        pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip().splitlines()[0]
            name, mem = [s.strip() for s in out.split(",")]
            info.update(backend="cuda-driver-only (torch CUDA not active)", name=name,
                        vram_gb=round(float(mem) / 1024, 1), source="nvidia-smi")
        except Exception:  # noqa: BLE001
            pass
    return info


def recommend(gpu: dict) -> list[str]:
    """Training recommendations. The real training time is measured and stored by
    train_yolo.py; nothing here is presented as a measured number."""
    recs = []
    vram = gpu.get("vram_gb") or 0
    if gpu["backend"] == "cuda":
        if vram <= 4:
            recs.append("YOLO: yolo11n, imgsz 1024, batch 2-4 (4 GB VRAM), amp=True. "
                        "If out of memory, drop to imgsz 896 or batch 2.")
        else:
            recs.append("YOLO: yolo11n or yolo11s, imgsz 1024-1280, batch 8.")
        recs.append("CRNN HTR: GPU training is feasible locally.")
    elif gpu["backend"].startswith("cuda-driver-only"):
        recs.append("An NVIDIA GPU exists but PyTorch CUDA is not active. Install the CUDA "
                    "build of torch before training (see docs/MODEL_TRAINING.md).")
    else:
        recs.append("No GPU: train YOLO on Google Colab (pack_for_colab.py). "
                    "The small CRNN config is CPU-feasible.")
    return recs


def main() -> int:
    lines = ["# Environment report", "",
             f"Generated: {datetime.now().isoformat(timespec='seconds')}", "", "## System", ""]
    lines.append(f"- OS: {platform.platform()}")
    lines.append(f"- Python: {sys.version.split()[0]} ({sys.executable})")
    lines.append(f"- CPU: {platform.processor() or 'unknown'}")
    try:
        import psutil  # type: ignore

        lines.append(f"- CPU cores (logical): {psutil.cpu_count()}")
        lines.append(f"- RAM: {round(psutil.virtual_memory().total / 1024**3, 1)} GB")
    except Exception:  # noqa: BLE001
        pass
    gpu = probe_gpu()
    lines.append(f"- Compute backend: {gpu['backend']}")
    if gpu["name"]:
        lines.append(f"- GPU: {gpu['name']} ({gpu['vram_gb']} GB, via {gpu['source']})")
    tess = shutil.which("tesseract")
    lines.append(f"- Tesseract binary: {tess or 'NOT FOUND (optional engine disabled)'}")
    if tess:
        try:
            langs = subprocess.run([tess, "--list-langs"], capture_output=True, text=True,
                                   timeout=10).stdout.split()
            lines.append(f"  - languages: eng={'eng' in langs}, nep={'nep' in langs}")
        except Exception:  # noqa: BLE001
            pass

    lines += ["", "## Python packages", "", "| Module | Purpose | Status |", "|---|---|---|"]
    for module, purpose in PACKAGES:
        ok, ver = probe_package(module)
        status = f"OK {ver}" if ok else f"MISSING ({ver})"
        lines.append(f"| `{module}` | {purpose} | {status} |")

    lines += ["", "## Recommendations", ""]
    lines.extend(f"- {r}" for r in recommend(gpu))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
