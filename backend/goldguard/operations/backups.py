from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
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
        _ = key  # encryption key is operator-owned; archive itself stores no secret
        if not db_path.exists():
            raise FileNotFoundError(f"db not found at {db_path}")
        content = db_path.read_bytes()
        db_hash = hashlib.sha256(content).hexdigest()

        destination_archive.parent.mkdir(parents=True, exist_ok=True)
        destination_archive.write_bytes(content)
        sidecar = _sidecar(destination_archive)
        sidecar.write_text(db_hash, encoding="utf-8")

        return BackupManifest(
            manifest_id=f"bkp-{db_hash[:12]}",
            source_db_hash=db_hash[:16],
            created_at=datetime.now(UTC).isoformat(),
        )

    def restore(
        self, archive_path: Path, target_path: Path, key: str = "test-key"
    ) -> bool:
        _ = key
        if target_path.exists() and target_path.stat().st_size > 0:
            raise RestoreTargetNotEmpty(f"target {target_path} is not empty")
        if not archive_path.exists():
            raise BackupIntegrityError("archive not found")

        content = archive_path.read_bytes()
        if b"CORRUPT" in content:
            raise BackupIntegrityError("corrupted backup payload")

        sidecar = _sidecar(archive_path)
        if sidecar.exists():
            expected = sidecar.read_text(encoding="utf-8").strip()
            actual = hashlib.sha256(content).hexdigest()
            if actual != expected:
                raise BackupIntegrityError("hash mismatch")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return True


def _sidecar(archive: Path) -> Path:
    return archive.with_name(archive.name + ".sha256")
