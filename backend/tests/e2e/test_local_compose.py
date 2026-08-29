from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_local_compose_exposes_opencodex_hermes_and_goldguard() -> None:
    compose_path = ROOT / "docker-compose.local.yml"
    content = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = content["services"]

    assert "opencodex" in services
    assert "hermes" in services
    assert "goldguard" in services

    assert "10100:10100" in services["opencodex"]["ports"]
    assert "8642:8642" in services["hermes"]["ports"]
    assert "8000:8000" in services["goldguard"]["ports"]

    goldguard_env = services["goldguard"]["environment"]
    assert goldguard_env["GOLDGUARD_MODE"] == "paper"
    assert goldguard_env["GOLDGUARD_LIVE_CAPABILITY_ENABLED"] == "false"
    assert goldguard_env["OPENCODEX_BASE_URL"] == "http://opencodex:10100"
    assert goldguard_env["GOLDGUARD_HERMES_BASE_URL"] == "http://hermes:8642"

    hermes_env = services["hermes"]["environment"]
    assert hermes_env["API_SERVER_HOST"] == "0.0.0.0"
    assert hermes_env["OPENAI_BASE_URL"] == "http://opencodex:10100/v1"


def test_autonomous_hermes_routes_through_openai_compatible_opencodex() -> None:
    compose_path = ROOT / "docker-compose.autonomous.yml"
    content = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    hermes_env = content["services"]["hermes"]["environment"]
    assert hermes_env["OPENAI_BASE_URL"] == "http://opencodex:10100/v1"
    assert "ports" not in content["services"]["hermes"]


def test_local_runbook_exists() -> None:
    path = ROOT / "docs/operations/local-opencodex.md"
    text = path.read_text(encoding="utf-8")
    assert "http://localhost:10100" in text
    assert "docker compose -f docker-compose.local.yml" in text
    assert "verify_local_stack.py" in text
