from __future__ import annotations

from pathlib import Path

import yaml


def test_compose_has_private_hermes_gateway() -> None:
    compose_path = Path("docker-compose.autonomous.yml")
    assert compose_path.exists()
    content = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    service = content["services"]["hermes"]
    assert service["image"] == "nousresearch/hermes-agent:latest"
    assert service["command"] == ["gateway", "run"]
    assert service["volumes"] == ["hermes-data:/opt/data"]
    assert "ports" not in service
    assert service["environment"]["API_SERVER_HOST"] == "0.0.0.0"

