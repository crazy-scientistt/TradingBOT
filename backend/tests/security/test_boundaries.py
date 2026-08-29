from __future__ import annotations

import pytest
from goldguard.config import Settings
from pydantic import ValidationError


def test_production_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("GOLDGUARD_CORS_ORIGINS", "*")
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(_env_file=None)


def test_production_rejects_http_cors(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("GOLDGUARD_CORS_ORIGINS", "http://app.goldguard.io")
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(_env_file=None)


def test_production_accepts_valid_https_cors(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("GOLDGUARD_CORS_ORIGINS", "https://app.goldguard.io, https://admin.goldguard.io")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ("https://app.goldguard.io", "https://admin.goldguard.io")


def test_core_has_no_direct_antigravity_key_field() -> None:
    fields = Settings.model_fields
    assert "gemini_api_key" not in fields
    assert "openrouter_api_key" not in fields
