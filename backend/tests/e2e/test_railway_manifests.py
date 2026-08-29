from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_app_healthcheck_is_live_probe() -> None:
    app_manifest = (ROOT / "railway.app.toml").read_text(encoding="utf-8")
    assert 'dockerfilePath = "backend/Dockerfile"' in app_manifest
    assert 'healthcheckPath = "/api/health/live"' in app_manifest

    root_manifest = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/api/health/live"' in root_manifest


def test_hermes_has_private_railway_manifest() -> None:
    hermes_manifest = ROOT / "hermes" / "railway.toml"
    assert hermes_manifest.exists()
    text = hermes_manifest.read_text(encoding="utf-8")
    assert 'dockerfilePath = "Dockerfile"' in text
    assert "public domain" in text.lower() or "no public" in text.lower()


def test_topology_doc_names_volumes_and_private_services() -> None:
    topology = ROOT / "docs" / "operations" / "railway-topology.md"
    assert topology.exists()
    text = topology.read_text(encoding="utf-8")
    assert "/data" in text
    assert "/app/.opencodex" in text
    assert "/opt/data" in text
    assert "10100" in text
    assert "8642" in text
    assert "one writer" in text.lower() or "single writer" in text.lower()
    assert "GoldGuard" in text
    assert "OpenCodex" in text
    assert "Hermes" in text
