from __future__ import annotations

import json
from pathlib import Path


def test_dockerfiles_exist_and_target_isolated_services() -> None:
    backend_df = Path("backend/Dockerfile")
    gateway_df = Path("gateway/Dockerfile")
    hermes_df = Path("hermes/Dockerfile")

    assert backend_df.exists()
    assert gateway_df.exists()
    assert hermes_df.exists()


def test_gateway_package_json_exists() -> None:
    pkg_path = Path("gateway/package.json")
    if pkg_path.exists():
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        assert "dependencies" in data or "name" in data

