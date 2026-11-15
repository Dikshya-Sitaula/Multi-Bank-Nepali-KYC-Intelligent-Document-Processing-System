"""Controlled file storage for uploads and derived images.

WHY:
- Uploaded KYC pages are personal data. They are stored outside any static web root under
  UPLOAD_DIR with random names, and are only read back through authenticated endpoints.
- The original upload is written once and never modified; processed images go to a
  separate folder.
- File type is decided from the file's magic bytes, not from its name or the browser's
  content type, which are both client-controlled.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

# Magic-byte signatures of accepted upload types.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"II*\x00", "image/tiff", ".tif"),
    (b"MM\x00*", "image/tiff", ".tif"),
]


class UploadRejected(ValueError):
    """Raised with a user-facing reason when an upload fails validation."""


@dataclass(frozen=True)
class StoredFile:
    path: Path            # absolute path on disk
    relative_path: str    # path relative to UPLOAD_DIR, stored in the database
    media_type: str
    size_bytes: int
    original_filename: str


def sniff_media_type(head: bytes) -> tuple[str, str] | None:
    """Return (media_type, extension) from the first bytes, or None if unsupported."""
    for sig, media, ext in _SIGNATURES:
        if head.startswith(sig):
            return media, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_display_name(name: str | None, max_len: int = 128) -> str:
    """Sanitise a client filename for display only. It is never used as a disk path."""
    base = Path(name or "upload").name  # drop any directory components
    base = _SAFE_CHARS.sub("_", base).strip(" .") or "upload"
    return base[:max_len]


def validate_upload(data: bytes, filename: str | None) -> tuple[str, str]:
    s = get_settings()
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise UploadRejected(f"The file is larger than {s.max_upload_mb} MB.")
    sniffed = sniff_media_type(data[:16])
    if sniffed is None:
        raise UploadRejected("Unsupported file type. Upload a PDF, PNG, JPEG, TIFF or WEBP file.")
    return sniffed


def save_upload(document_public_id: str, data: bytes, filename: str | None) -> StoredFile:
    """Validate and store an original upload under uploads/<document>/original/."""
    media, ext = validate_upload(data, filename)
    root = get_settings().upload_dir
    rel = Path(document_public_id) / "original" / f"{uuid.uuid4().hex}{ext}"
    dest = resolve_inside(root, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as f:  # "x": never overwrite an existing file
        f.write(data)
    return StoredFile(dest, rel.as_posix(), media, len(data), safe_display_name(filename))


def derived_path(document_public_id: str, kind: str, name: str) -> Path:
    """Path for a derived artefact (processed page, crop, debug image)."""
    if not re.fullmatch(r"[a-z_]+", kind):
        raise ValueError("invalid artefact kind")
    p = resolve_inside(get_settings().upload_dir, Path(document_public_id) / kind / safe_display_name(name))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def resolve_inside(root: Path, relative: str | Path) -> Path:
    """Join and verify the result stays inside root (blocks ../ path traversal)."""
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError("path escapes storage root")
    return candidate


def open_stored(relative_path: str) -> Path:
    """Absolute path of a stored file, for authenticated download endpoints."""
    p = resolve_inside(get_settings().upload_dir, relative_path)
    if not p.is_file():
        raise FileNotFoundError(relative_path)
    return p
