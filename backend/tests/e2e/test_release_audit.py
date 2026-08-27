from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_release import (
    AuditStatus,
    audit_api_snapshot,
    audit_compose_file,
    audit_provider,
)


def test_missing_docker_context_is_blocked(tmp_path: Path) -> None:
    """A compose context must contain every source referenced by its Dockerfile."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY frontend/ ./frontend/\n",
        encoding="utf-8",
    )
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  backend:\n"
        "    build:\n"
        "      context: ./backend\n"
        "      dockerfile: Dockerfile\n",
        encoding="utf-8",
    )

    findings = audit_compose_file(compose, root=tmp_path)

    assert any(f.status == AuditStatus.BLOCKED for f in findings)
    assert any("frontend" in f.detail for f in findings)


def test_unconfigured_provider_is_degraded() -> None:
    findings = audit_provider(
        {
            "GOLDGUARD_MODE": "paper",
            "GOLDGUARD_LIVE_CAPABILITY_ENABLED": "false",
        }
    )

    provider = next(f for f in findings if f.name == "provider")
    assert provider.status == AuditStatus.DEGRADED
    assert "configured" in provider.detail.lower()


def test_fabricated_api_data_is_blocked() -> None:
    snapshot = {
        "position": {
            "availability": "unavailable",
            "source": "paper-broker",
            "data": {"hasPosition": True, "position": {"entry": 2_500}},
        },
        "kpi": {
            "availability": "unavailable",
            "source": "paper-ledger",
            "data": {"equity": 101.25},
        },
    }

    findings = audit_api_snapshot(snapshot)

    assert any(f.status == AuditStatus.BLOCKED for f in findings)
    assert any("fabricated" in f.detail.lower() for f in findings)


def test_audit_findings_are_json_serialisable() -> None:
    findings = audit_api_snapshot({"agentEvents": {"availability": "unavailable", "data": []}})
    json.dumps([finding.as_dict() for finding in findings])
