"""Upload validation and safe storage."""
import pytest

from app.core.config import get_settings
from app.services.storage import files

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.mark.parametrize("data,media", [(PNG, "image/png"), (PDF, "application/pdf"), (JPG, "image/jpeg")])
def test_magic_bytes_detected(data, media):
    assert files.sniff_media_type(data[:16])[0] == media


def test_extension_is_ignored_magic_bytes_decide(app_env):
    # An executable renamed to .png is rejected; a PNG named .txt is accepted as PNG.
    with pytest.raises(files.UploadRejected):
        files.validate_upload(b"MZ\x90\x00" + b"0" * 32, "photo.png")
    assert files.validate_upload(PNG, "notes.txt") == ("image/png", ".png")


def test_empty_and_oversized_rejected(app_env, monkeypatch):
    with pytest.raises(files.UploadRejected, match="empty"):
        files.validate_upload(b"", "a.png")
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    with pytest.raises(files.UploadRejected, match="larger"):
        files.validate_upload(PNG + b"0" * (1024 * 1024), "a.png")


def test_save_upload_uses_random_name_inside_root(app_env):
    stored = files.save_upload("doc-123", PNG, "../../etc/passwd.png")
    root = get_settings().upload_dir.resolve()
    assert root in stored.path.parents
    assert stored.path.read_bytes() == PNG
    assert "passwd" not in stored.relative_path
    assert stored.original_filename == "passwd.png"
    assert files.open_stored(stored.relative_path) == stored.path


def test_path_traversal_blocked(app_env):
    with pytest.raises(PermissionError):
        files.open_stored("../outside.png")
    with pytest.raises(PermissionError):
        files.resolve_inside(get_settings().upload_dir, "a/../../b")
    with pytest.raises(ValueError):
        files.derived_path("doc", "../x", "a.png")


@pytest.mark.parametrize("name,expected", [
    ("C:\\Users\\x\\scan 1.jpg", "scan 1.jpg"),
    ("../../a<b>.pdf", "a_b_.pdf"),
    ("", "upload"),
    ("...", "upload"),
])
def test_safe_display_name(name, expected):
    assert files.safe_display_name(name) == expected
