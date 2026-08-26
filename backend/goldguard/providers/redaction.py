import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{8,}"),
    re.compile(r"sk-[a-zA-Z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[:=]\s*['\"]?)[^\s'\",]{6,}"),
]

SENSITIVE_KEYS = frozenset(
    {"api_key", "token", "password", "secret", "private_key", "key_fingerprint"}
)


def redact_string(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        replacement = r"\1[REDACTED]" if r"\1" in pattern.pattern else "[REDACTED]"
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_secrets(data: Any) -> Any:
    if isinstance(data, str):
        return redact_string(data)
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if k.lower() in SENSITIVE_KEYS and isinstance(v, str):
                result[k] = "[REDACTED]"
            else:
                result[k] = redact_secrets(v)
        return result
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_secrets(item) for item in data)
    return data
