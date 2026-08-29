from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_dockerfiles_exist_and_target_isolated_services() -> None:
    backend_df = ROOT / "backend/Dockerfile"
    gateway_df = ROOT / "gateway/Dockerfile"
    hermes_df = ROOT / "hermes/Dockerfile"

    assert backend_df.exists()
    assert gateway_df.exists()
    assert hermes_df.exists()


def test_backend_image_is_nonroot_and_port_driven() -> None:
    text = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert "USER " in text
    assert "$PORT" in text or "${PORT" in text
    assert "/data" in text
    assert "/api/health/live" in text


def test_gateway_dependency_is_exact() -> None:
    pkg_path = ROOT / "gateway/package.json"
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    version = data["dependencies"]["@bitkyc08/opencodex"]
    assert version == "2.33.0"


def test_gateway_package_json_exists() -> None:
    pkg_path = ROOT / "gateway/package.json"
    assert pkg_path.exists()
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert "dependencies" in data or "name" in data
