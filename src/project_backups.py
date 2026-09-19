"""Atomic backup creation and retention, independent of project operations."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from .backup_policy import next_sequence_backup_path, rotate_sequence_backups, should_backup


def copy_file_atomically(source: Path, destination: Path) -> None:
    """Copy a file without exposing a partially written destination."""
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(str(source), str(temp_path))
        os.replace(str(temp_path), str(destination))
        # Retention is based on backup creation time, not source mtime.
        os.utime(destination, None)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def create_backup(
    source: Path,
    backups_dir: Path,
    *,
    count: int,
    max_bytes: int,
    force: bool = False,
    next_project: dict | None = None,
) -> None:
    """Back up the previous content before replacing or removing a project."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    if not force and next_project is not None:
        try:
            with source.open(encoding="utf-8") as stream:
                current = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError):
            current = {}
        if not should_backup(current, next_project):
            return
    elif not force:
        return

    destination = next_sequence_backup_path(source, backups_dir)
    copy_file_atomically(source, destination)
    rotate_sequence_backups(source, backups_dir, count, max_bytes)
