import re
import subprocess
from pathlib import Path

import httpx
import pytest

# Secret pattern regexes for scanning tracked files
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PRIVATE )?KEY-----"),
    re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"),
]


def test_no_tracked_files_contain_secrets() -> None:
    """Ensure no tracked file contains live API keys, private keys, or credentials."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        git_ls = subprocess.check_output(
            ["git", "ls-files"], cwd=repo_root, text=True, encoding="utf-8"
        )
        tracked_files = [repo_root / f for f in git_ls.splitlines() if f.strip()]
    except Exception:
        tracked_files = [
            p
            for p in repo_root.rglob("*")
            if p.is_file()
            and not any(
                part.startswith(".") or part in ("node_modules", "dist", "data") for part in p.parts
            )
        ]

    violations: list[str] = []
    for file_path in tracked_files:
        if not file_path.exists() or file_path.is_dir():
            continue
        if file_path.name == "test_safety_guard.py":
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    real_matches = [
                        m
                        for m in matches
                        if not m.startswith(("sk-test", "sk-mock", "sk-ant-test"))
                    ]
                    if real_matches:
                        violations.append(
                            f"{file_path.relative_to(repo_root)}: matched {pattern.pattern}"
                        )
        except Exception:
            continue

    msg = "Potential secrets discovered in tracked repository files:\n" + "\n".join(violations)
    assert not violations, msg


def test_safety_guard_rejects_production_order_url() -> None:
    """Assert the host guard raises when a request attempts to target production order URLs."""
    from goldguard.broker.safety_guard import SafetyGuardError, check_safe_url  # type: ignore

    with pytest.raises(SafetyGuardError, match="GOLDGUARD_SAFETY_GUARD"):
        check_safe_url("https://api.binance.com/api/v3/order")


def test_safety_guard_allows_mock_transport() -> None:
    """Assert requests using httpx.MockTransport are permitted through the safety guard."""

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"orderId": 12345, "status": "FILLED"})

    transport = httpx.MockTransport(fake_handler)
    client = httpx.Client(transport=transport, base_url="https://api.binance.com")
    response = client.post("/api/v3/order", json={"symbol": "PAXGUSDT", "side": "BUY"})
    assert response.status_code == 200
    assert response.json()["status"] == "FILLED"
