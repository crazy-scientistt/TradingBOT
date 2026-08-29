from __future__ import annotations

from pathlib import Path

import pytest
from goldguard.operations.backups import (
    BackupIntegrityError,
    BackupService,
    RestoreTargetNotEmpty,
)


def test_backup_and_restore_drill(tmp_path: Path) -> None:
    db_file = tmp_path / "origin.db"
    db_file.write_bytes(b"VALID_DATABASE_CONTENT")

    archive_file = tmp_path / "backup.bin"
    service = BackupService()
    manifest = service.create(db_file, archive_file, key="secret")
    assert manifest.manifest_id == "bkp-1"

    restore_target = tmp_path / "restored.db"
    success = service.restore(archive_file, restore_target, key="secret")
    assert success is True
    assert restore_target.read_bytes() == b"VALID_DATABASE_CONTENT"


def test_corrupted_backup_never_restores(tmp_path: Path) -> None:
    corrupt_archive = tmp_path / "corrupt.bin"
    corrupt_archive.write_bytes(b"CORRUPT_DATA")

    service = BackupService()
    with pytest.raises(BackupIntegrityError):
        service.restore(corrupt_archive, tmp_path / "dummy.db")


def test_restore_refuses_active_database(tmp_path: Path) -> None:
    archive = tmp_path / "archive.bin"
    archive.write_bytes(b"DATA")

    active_target = tmp_path / "active.db"
    active_target.write_bytes(b"EXISTING_DATA")

    service = BackupService()
    with pytest.raises(RestoreTargetNotEmpty):
        service.restore(archive, active_target)

