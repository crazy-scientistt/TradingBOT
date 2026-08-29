from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_operator_docs_cover_required_topics() -> None:
    files = {
        ROOT / "docs/operations/backup-restore.md",
        ROOT / "docs/operations/operator-handoff.md",
        ROOT / "docs/operations/paper-qualification.md",
        ROOT / "docs/operations/live-arming.md",
        ROOT / "docs/operations/railway-topology.md",
        ROOT / "docs/operations/local-opencodex.md",
        ROOT / "docs/RUNBOOK.md",
    }
    blob = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for needle in (
        "Paper qualification",
        "Live arming",
        "reconciliation",
        "OpenCodex",
        "Hermes",
        "Telegram",
        "backup",
        "/data",
        "localhost:10100",
    ):
        assert needle.lower() in blob.lower(), needle
    assert "paste token" not in blob.lower()
