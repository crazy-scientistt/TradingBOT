"""Read-only release audit for the GoldGuard paper-first deployment.

The audit deliberately separates configuration evidence from live observations.  A
configured URL is not evidence that a provider answered, and a missing Docker daemon
is reported as ``blocked`` rather than being mistaken for a successful build.

The module is importable by deterministic tests and can also be run directly from a
checkout::

    python scripts/audit_release.py --root . --json

No credentials are printed.  Values read from ``.env`` are used only as booleans (for
example, whether a token is present) and are never included in the report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class AuditStatus(StrEnum):
    """Statuses used by the release gate, ordered from safest to most severe."""

    PASS = "pass"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AuditFinding:
    """One auditable release condition with safe, human-readable evidence."""

    name: str
    status: AuditStatus
    detail: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "evidence": dict(self.evidence),
        }


def _finding(
    name: str,
    status: AuditStatus,
    detail: str,
    **evidence: Any,
) -> AuditFinding:
    return AuditFinding(name=name, status=status, detail=detail, evidence=evidence)


def _read_dotenv(root: Path) -> dict[str, str]:
    """Read simple ``KEY=value`` entries without expanding or logging secrets."""

    path = root / ".env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _environment(root: Path, supplied: Mapping[str, str] | None) -> dict[str, str]:
    if supplied is not None:
        return {str(key): str(value) for key, value in supplied.items()}
    values = _read_dotenv(root)
    # The process environment wins over a checkout-local .env file, as it does in
    # Compose and in the application process.
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _compose_build_blocks(text: str) -> dict[str, dict[str, str]]:
    """Extract service build context/dockerfile pairs without a YAML dependency."""

    services: dict[str, dict[str, str]] = {}
    service: str | None = None
    in_build = False
    for line in text.splitlines():
        if match := re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line):
            service = match.group(1)
            services.setdefault(service, {})
            in_build = False
            continue
        if service is None:
            continue
        if re.match(r"^    build:\s*$", line):
            in_build = True
            continue
        if in_build and re.match(r"^    \S", line):
            in_build = False
        if not in_build:
            continue
        if match := re.match(r"^      context:\s*(\S+)", line):
            services[service]["context"] = match.group(1).strip('"\'')
        elif match := re.match(r"^      dockerfile:\s*(\S+)", line):
            services[service]["dockerfile"] = match.group(1).strip('"\'')
    return {name: build for name, build in services.items() if "context" in build}


def _dockerfile_sources(dockerfile: Path) -> list[str]:
    """Return COPY source paths (excluding files copied from another stage)."""

    sources: list[str] = []
    for raw_line in dockerfile.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.upper().startswith("COPY "):
            continue
        tokens = line.split()[1:]
        # A source copied from another build stage is not required in the external
        # build context (for example ``COPY --from=frontend-builder ...``).
        if any(token.startswith("--from=") for token in tokens):
            continue
        if len(tokens) >= 2:
            sources.extend(tokens[:-1])
    return sources


def _dockerfile_dependency_finding(dockerfile: Path) -> AuditFinding | None:
    lines = dockerfile.read_text(encoding="utf-8", errors="replace").splitlines()
    install_indexes = [
        index
        for index, line in enumerate(lines)
        if re.search(r"\bpip\s+install\b[^\n]*\.", line)
    ]
    if not install_indexes:
        return None
    install_index = install_indexes[0]
    package_copy_indexes = [
        index
        for index, line in enumerate(lines)
        if re.match(r"\s*COPY\s+(?:backend/goldguard|backend/)\S*", line)
    ]
    if package_copy_indexes and min(package_copy_indexes) < install_index:
        return _finding(
            "dependency_copy_order",
            AuditStatus.PASS,
            "Python package source is copied before pip install.",
            dockerfile=str(dockerfile),
        )
    return _finding(
        "dependency_copy_order",
        AuditStatus.BLOCKED,
        "Dockerfile runs pip install before copying backend package sources.",
        dockerfile=str(dockerfile),
    )


def _dockerfile_context_finding(dockerfile: Path, context: Path) -> AuditFinding:
    """Check a standalone Dockerfile's COPY sources against its build context."""

    missing_sources: list[str] = []
    for source in _dockerfile_sources(dockerfile):
        source_path = (context / source).resolve()
        try:
            source_path.relative_to(context)
        except ValueError:
            missing_sources.append(source)
            continue
        if not source_path.exists():
            missing_sources.append(source)
    if missing_sources:
        return _finding(
            "docker_context",
            AuditStatus.BLOCKED,
            "Standalone Dockerfile references files outside its build context: "
            + ", ".join(missing_sources),
            dockerfile=str(dockerfile),
            context=str(context),
            missing_sources=missing_sources,
        )
    return _finding(
        "docker_context",
        AuditStatus.PASS,
        "Standalone Dockerfile sources are present in its build context.",
        dockerfile=str(dockerfile),
        context=str(context),
    )


def audit_compose_file(compose_path: Path, *, root: Path | None = None) -> tuple[AuditFinding, ...]:
    """Validate Compose build contexts and Dockerfile source/dependency ordering."""

    root = (root or compose_path.parent).resolve()
    if not compose_path.is_file():
        return (
            _finding(
                "docker_context",
                AuditStatus.BLOCKED,
                f"Compose file is missing: {compose_path.name}.",
                path=str(compose_path),
            ),
        )
    text = compose_path.read_text(encoding="utf-8", errors="replace")
    builds = _compose_build_blocks(text)
    findings: list[AuditFinding] = []
    if not builds:
        findings.append(
            _finding(
                "docker_context",
                AuditStatus.BLOCKED,
                "Compose file declares no build contexts.",
                path=str(compose_path),
            )
        )
        return tuple(findings)

    for service, build in builds.items():
        context = (compose_path.parent / build["context"]).resolve()
        dockerfile = context / build.get("dockerfile", "Dockerfile")
        if not context.is_dir():
            findings.append(
                _finding(
                    "docker_context",
                    AuditStatus.BLOCKED,
                    f"Service {service!r} build context does not exist: {context}.",
                    service=service,
                    context=str(context),
                )
            )
            continue
        if not dockerfile.is_file():
            findings.append(
                _finding(
                    "docker_context",
                    AuditStatus.BLOCKED,
                    f"Service {service!r} Dockerfile does not exist: {dockerfile}.",
                    service=service,
                    dockerfile=str(dockerfile),
                )
            )
            continue

        missing_sources: list[str] = []
        for source in _dockerfile_sources(dockerfile):
            # Absolute paths and parent traversal are invalid in a build context.
            source_path = (context / source).resolve()
            try:
                source_path.relative_to(context)
            except ValueError:
                missing_sources.append(source)
                continue
            if not source_path.exists():
                missing_sources.append(source)
        if missing_sources:
            findings.append(
                _finding(
                    "docker_context",
                    AuditStatus.BLOCKED,
                    f"Service {service!r} Dockerfile references files outside its build context: "
                    + ", ".join(missing_sources),
                    service=service,
                    context=str(context),
                    missing_sources=missing_sources,
                )
            )
        else:
            findings.append(
                _finding(
                    "docker_context",
                    AuditStatus.PASS,
                    f"Service {service!r} build context contains Dockerfile sources.",
                    service=service,
                    context=str(context),
                )
            )
        dependency = _dockerfile_dependency_finding(dockerfile)
        if dependency is not None:
            findings.append(dependency)

    return tuple(findings)


def audit_provider(env: Mapping[str, str]) -> tuple[AuditFinding, ...]:
    """Check optional AI provider configuration without treating it as live proof."""

    gateway_url = env.get("GOLDGUARD_GATEWAY_BASE_URL") or env.get("OPENCODEX_BASE_URL")
    gateway_token = env.get("GOLDGUARD_GATEWAY_DATA_TOKEN") or env.get(
        "OPENCODEX_API_AUTH_TOKEN"
    )
    native_key = env.get("GEMINI_API_KEY")
    if not gateway_url and not native_key:
        return (
            _finding(
                "provider",
                AuditStatus.DEGRADED,
                "No provider is configured; deterministic paper gates remain available, "
                "but AI veto/context checks cannot be observed.",
            ),
        )
    if gateway_url and not gateway_token:
        return (
            _finding(
                "provider",
                AuditStatus.DEGRADED,
                "Provider gateway URL is set but its data token is not configured.",
                gateway_url=gateway_url,
            ),
        )
    configured = "gateway" if gateway_url else "native"
    return (
        _finding(
            "provider",
            AuditStatus.PASS,
            f"{configured} provider configuration is present; reachability was not claimed.",
            provider=configured,
        ),
    )


def audit_market_source(env: Mapping[str, str]) -> tuple[AuditFinding, ...]:
    enabled = env.get("GOLDGUARD_MARKET_INGESTION_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    url = env.get("GOLDGUARD_MARKET_BASE_URL", "https://data-api.binance.vision").strip()
    if not enabled:
        return (
            _finding(
                "market_source",
                AuditStatus.DEGRADED,
                "Market ingestion is disabled; no live candles or quote can be verified.",
                source=url,
            ),
        )
    if not re.match(r"^https?://[^\s/]+(?:/[^\s]*)?$", url):
        return (
            _finding(
                "market_source",
                AuditStatus.BLOCKED,
                "Configured market source is not a valid HTTP(S) URL.",
                source=url,
            ),
        )
    return (
        _finding(
            "market_source",
            AuditStatus.DEGRADED,
            "Market source is configured; no external candle/quote request was made by this audit.",
            source=url,
        ),
    )


def audit_safety_gates(env: Mapping[str, str]) -> tuple[AuditFinding, ...]:
    mode = env.get("GOLDGUARD_MODE", "paper").strip().lower()
    live_enabled = _truthy(env.get("GOLDGUARD_LIVE_CAPABILITY_ENABLED", "false"))
    findings: list[AuditFinding] = []
    if mode != "paper":
        findings.append(
            _finding(
                "safety_gates",
                AuditStatus.BLOCKED,
                f"Trading mode is {mode!r}; this release permits paper mode only.",
                mode=mode,
            )
        )
    elif live_enabled:
        findings.append(
            _finding(
                "safety_gates",
                AuditStatus.BLOCKED,
                "Live capability is enabled; production must keep this gate false.",
                mode=mode,
                live_capability_enabled=True,
            )
        )
    else:
        findings.append(
            _finding(
                "safety_gates",
                AuditStatus.PASS,
                "Paper mode is selected and live capability is disabled.",
                mode=mode,
                live_capability_enabled=False,
            )
        )
    return tuple(findings)


def audit_production_compose_safety(compose_path: Path) -> tuple[AuditFinding, ...]:
    """Ensure the checked-in production manifest cannot arm live execution."""

    if not compose_path.is_file():
        return ()
    text = compose_path.read_text(encoding="utf-8", errors="replace")
    mode_match = re.search(r"(?:^|[-\s])GOLDGUARD_MODE\s*=\s*([^\s#]+)", text)
    live_match = re.search(
        r"(?:^|[-\s])GOLDGUARD_LIVE_CAPABILITY_ENABLED\s*=\s*([^\s#]+)",
        text,
    )
    mode = mode_match.group(1).strip("'\"").lower() if mode_match else None
    live = live_match.group(1).strip("'\"").lower() if live_match else None
    if mode != "paper" or live != "false":
        return (
            _finding(
                "production_safety",
                AuditStatus.BLOCKED,
                "Production Compose must set GOLDGUARD_MODE=paper and "
                "GOLDGUARD_LIVE_CAPABILITY_ENABLED=false.",
                mode=mode,
                live_capability_enabled=live,
            ),
        )
    return (
        _finding(
            "production_safety",
            AuditStatus.PASS,
            "Production Compose explicitly selects paper mode and disables live capability.",
            mode=mode,
            live_capability_enabled=False,
        ),
    )


def audit_database(root: Path, env: Mapping[str, str]) -> tuple[AuditFinding, ...]:
    configured_dir = env.get("GOLDGUARD_DATA_DIR", "data")
    data_dir = Path(configured_dir)
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    path = data_dir / "goldguard.db"
    if not path.is_file():
        return (
            _finding(
                "database",
                AuditStatus.DEGRADED,
                "SQLite database is not present; first boot must initialise durable paper state.",
                path=str(path),
            ),
        )
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            table_count = int(
                connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
            )
    except (OSError, sqlite3.Error) as exc:
        return (
            _finding(
                "database",
                AuditStatus.BLOCKED,
                f"SQLite database could not be read: {exc}.",
                path=str(path),
            ),
        )
    if integrity.lower() != "ok" or table_count == 0:
        return (
            _finding(
                "database",
                AuditStatus.BLOCKED,
                f"SQLite integrity check failed ({integrity}); no release claim is safe.",
                path=str(path),
                integrity=integrity,
                tables=table_count,
            ),
        )
    return (
        _finding(
            "database",
            AuditStatus.PASS,
            "SQLite integrity is ok and the schema contains tables.",
            path=str(path),
            integrity=integrity,
            tables=table_count,
        ),
    )


def _is_unavailable_payload(payload: Any) -> bool:
    if payload is None or payload == [] or payload == {}:
        return True
    if isinstance(payload, Mapping):
        return all(
            value is None or value == [] or value == {} or value is False
            for value in payload.values()
        )
    return False


def audit_api_snapshot(snapshot: Mapping[str, Any]) -> tuple[AuditFinding, ...]:
    """Reject values attached to an ``unavailable`` envelope (fabricated data)."""

    findings: list[AuditFinding] = []
    envelope_sections = {
        name: payload
        for name, payload in snapshot.items()
        if name not in {"health", "preflight"} and isinstance(payload, Mapping)
    }
    if not envelope_sections:
        return (
            _finding(
                "api_truthfulness",
                AuditStatus.DEGRADED,
                "No enveloped dashboard sections were supplied for API truthfulness audit.",
            ),
        )
    for name, payload in envelope_sections.items():
        availability = str(payload.get("availability", "")).lower()
        data = payload.get("data")
        # Runtime/configuration sections can legitimately carry static safety
        # fields while their live observation is unavailable.  Value-bearing
        # market, ledger, context, and event sections must be empty instead.
        static_sections = {"status", "settings"}
        if (
            availability == "unavailable"
            and name not in static_sections
            and not _is_unavailable_payload(data)
        ):
            findings.append(
                _finding(
                    "api_truthfulness",
                    AuditStatus.BLOCKED,
                    f"Dashboard section {name!r} contains fabricated data while unavailable.",
                    section=name,
                )
            )
        elif "availability" not in payload or "data" not in payload:
            findings.append(
                _finding(
                    "api_truthfulness",
                    AuditStatus.BLOCKED,
                    f"Dashboard section {name!r} is missing the provenance envelope.",
                    section=name,
                )
            )
    if not findings:
        findings.append(
            _finding(
                "api_truthfulness",
                AuditStatus.PASS,
                "Dashboard sections use provenance envelopes without unavailable values.",
                sections=len(envelope_sections),
            )
        )
    return tuple(findings)


def audit_runtime_and_events(snapshot: Mapping[str, Any] | None) -> tuple[AuditFinding, ...]:
    if snapshot is None:
        return (
            _finding(
                "runtime",
                AuditStatus.DEGRADED,
                "No running API snapshot supplied; runtime state and event stream are unobserved.",
            ),
            _finding(
                "event_stream",
                AuditStatus.DEGRADED,
                "No running API snapshot supplied; event stream is unobserved.",
            ),
        )
    findings: list[AuditFinding] = []
    # ``/api/dashboard`` calls this section ``botState``; ``/api/bot/status``
    # uses ``botStatus``.  The application ``status`` envelope is not a runtime
    # heartbeat and must not be treated as one.
    runtime_payload = snapshot.get("botStatus") or snapshot.get("botState")
    if isinstance(runtime_payload, Mapping):
        availability = str(runtime_payload.get("availability", "")).lower()
        data = runtime_payload.get("data", runtime_payload)
        if availability == "unavailable":
            detail = runtime_payload.get("detail", "")
            findings.append(
                _finding(
                    "runtime",
                    AuditStatus.DEGRADED if str(detail).strip() else AuditStatus.BLOCKED,
                    "Runtime status is unavailable in the API snapshot"
                    + (f": {detail}" if detail else "")
                    + ". The runtime has not initialised a live observation.",
                    availability=availability,
                    runtime_detail=detail,
                )
            )
        else:
            findings.append(
                _finding(
                    "runtime",
                    AuditStatus.PASS,
                    "Runtime status was returned by the API snapshot.",
                    running=bool(data.get("running", False)) if isinstance(data, Mapping) else False,
                )
            )
    else:
        findings.append(
            _finding("runtime", AuditStatus.DEGRADED, "API snapshot has no runtime status section.")
        )
    events_payload = snapshot.get("agentEvents")
    events_availability = (
        str(events_payload.get("availability", "")).lower()
        if isinstance(events_payload, Mapping)
        else ""
    )
    events = events_payload.get("data") if isinstance(events_payload, Mapping) else None
    if events_availability == "unavailable":
        findings.append(
            _finding(
                "event_stream",
                AuditStatus.DEGRADED,
                "Agent event stream is unavailable in the API snapshot.",
                availability=events_availability,
            )
        )
    elif isinstance(events, list) and len(events) <= 30:
        findings.append(
            _finding(
                "event_stream",
                AuditStatus.PASS if events else AuditStatus.DEGRADED,
                "Agent event snapshot is bounded to the 30-item display limit."
                if events
                else "Agent event stream is available but has no events yet.",
                count=len(events),
            )
        )
    elif isinstance(events, list):
        findings.append(
            _finding(
                "event_stream",
                AuditStatus.BLOCKED,
                "Agent event stream exceeds the 30-item display limit.",
                count=len(events),
            )
        )
    else:
        findings.append(
            _finding("event_stream", AuditStatus.DEGRADED, "API snapshot has no event list.")
        )
    return tuple(findings)


def audit_frontend(root: Path) -> tuple[AuditFinding, ...]:
    index = root / "frontend" / "dist" / "index.html"
    if not index.is_file():
        return (
            _finding(
                "frontend_root",
                AuditStatus.DEGRADED,
                "Built frontend root is missing; image build must run npm build before serving UI.",
                path=str(index),
            ),
        )
    return (
        _finding(
            "frontend_root",
            AuditStatus.PASS,
            "Built frontend root contains index.html.",
            path=str(index),
        ),
    )


def audit_docker_daemon(
    *,
    probe: Sequence[str] | None = None,
) -> tuple[AuditFinding, ...]:
    """Check daemon availability only; never run a build as part of the audit."""

    command = list(probe or ("docker", "info"))
    if shutil.which(command[0]) is None:
        return (
            _finding(
                "docker_daemon",
                AuditStatus.BLOCKED,
                "Docker CLI is unavailable; image build/release verification is blocked.",
            ),
        )
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (
            _finding(
                "docker_daemon",
                AuditStatus.BLOCKED,
                f"Docker daemon probe could not run: {exc}; build verification is blocked.",
            ),
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "daemon returned a non-zero status").strip()
        return (
            _finding(
                "docker_daemon",
                AuditStatus.BLOCKED,
                f"Docker daemon is unavailable; build verification is blocked ({detail}).",
            ),
        )
    return (
        _finding(
            "docker_daemon",
            AuditStatus.PASS,
            "Docker daemon responded to info; no build was run by the audit.",
        ),
    )


def _fetch_dashboard(api_url: str) -> Mapping[str, Any] | None:
    request = Request(
        api_url.rstrip("/") + "/api/dashboard",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def run_release_audit(
    root: Path | str = ".",
    *,
    env: Mapping[str, str] | None = None,
    api_snapshot: Mapping[str, Any] | None = None,
    api_url: str | None = None,
    include_docker_probe: bool = True,
) -> dict[str, Any]:
    """Run every read-only release check and return a JSON-safe report."""

    root_path = Path(root).resolve()
    values = _environment(root_path, env)
    if api_snapshot is None and api_url:
        api_snapshot = _fetch_dashboard(api_url)
    findings: list[AuditFinding] = []
    findings.extend(audit_compose_file(root_path / "docker-compose.yml", root=root_path))
    findings.extend(audit_compose_file(root_path / "docker-compose.prod.yml", root=root_path))
    findings.extend(audit_production_compose_safety(root_path / "docker-compose.prod.yml"))
    # Railway and other single-image deployments use the root Dockerfile directly,
    # outside either Compose manifest, so audit its package-copy order as well.
    root_dockerfile = root_path / "Dockerfile"
    if root_dockerfile.is_file():
        findings.append(_dockerfile_context_finding(root_dockerfile, root_path))
        dependency = _dockerfile_dependency_finding(root_dockerfile)
        if dependency is not None:
            findings.append(dependency)
    findings.extend(audit_provider(values))
    findings.extend(audit_market_source(values))
    findings.extend(audit_safety_gates(values))
    findings.extend(audit_database(root_path, values))
    findings.extend(audit_frontend(root_path))
    if api_snapshot is None:
        findings.extend(audit_runtime_and_events(None))
    else:
        findings.extend(audit_runtime_and_events(api_snapshot))
        findings.extend(audit_api_snapshot(api_snapshot))
    if include_docker_probe:
        findings.extend(audit_docker_daemon())

    statuses = {finding.status for finding in findings}
    overall = (
        AuditStatus.BLOCKED
        if AuditStatus.BLOCKED in statuses
        else AuditStatus.DEGRADED
        if AuditStatus.DEGRADED in statuses
        else AuditStatus.PASS
    )
    return {
        "status": overall.value,
        "root": str(root_path),
        "checks": [finding.as_dict() for finding in findings],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GoldGuard read-only deployment release audit")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--api-url",
        help="Optional running backend URL for dashboard truthfulness checks",
    )
    parser.add_argument("--skip-docker", action="store_true", help="Skip the Docker daemon probe")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)
    report = run_release_audit(
        args.root,
        api_url=args.api_url,
        include_docker_probe=not args.skip_docker,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Release audit: {report['status'].upper()}")
        for finding in report["checks"]:
            print(f"[{str(finding['status']).upper():9}] {finding['name']}: {finding['detail']}")
    return 0 if report["status"] == AuditStatus.PASS.value else 2


if __name__ == "__main__":
    # Running from a source checkout does not install the ``backend`` package yet.
    backend_path = str(Path(__file__).resolve().parents[1] / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    raise SystemExit(main())
