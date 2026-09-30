"""Where attachment files live on disk, and safe removal."""
from __future__ import annotations

from pathlib import Path

from .. import db
from .settings import get_settings


def _attach_root(con) -> Path:
    folder = get_settings(con).get("AttachmentFolder")
    root = Path(folder) if folder else db.ROOT / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _remove_file(path: str | None) -> None:
    try:
        if path and Path(path).is_file():
            Path(path).unlink()
            parent = Path(path).parent  # prune the now-empty asset / month / group folders (never further up)
            for _ in range(3):
                if any(parent.iterdir()):
                    break
                parent.rmdir()
                parent = parent.parent
    except OSError:
        pass
