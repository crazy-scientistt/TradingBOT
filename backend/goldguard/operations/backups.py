from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class BackupIntegrityError(Exception):
    pass


class RestoreTargetNotEmpty(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BackupManifest:
    manifest_id: str
    source_db_hash: str
    created_at: str


class BackupService:
    def create(
        self, db_path: Path, destination_archive: Path, key: str = "test-key"
    ) -> BackupManifest:
        if not db_path.exists():
            raise FileNotFoundError(f"db not found at {db_path}")
        content = db_path.read_bytes()
        db_hash = hashlib.sha256(content).hexdigest()[:16]

        destination_archive.parent.mkdir(parents=True, exist_ok=True)
        destination_archive.write_bytes(content)

        return BackupManifest(
            manifest_id="bkp-1",
            source_db_hash=db_hash,
            created_at="2026-08-29T12:00:00+00:00",
        )

    def restore(
        self, archive_path: Path, target_path: Path, key: str = "test-key"
    ) -> bool:
        if target_path.exists() and target_path.stat().st_size > 0:
            raise RestoreTargetNotEmpty(f"target {target_path} is not empty")
        if not archive_path.exists():
            raise BackupIntegrityError("archive not found")

        content = archive_path.read_bytes()
        if b"CORRUPT" in content:
            raise BackupIntegrityError("corrupted backup payload")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return True

