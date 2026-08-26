import re
from urllib.parse import urlparse


class SafetyGuardError(RuntimeError):
    """Raised when an operation attempts to violate runtime or test safety invariants."""

    pass


FORBIDDEN_HOST_PATTERNS = [
    re.compile(r"^(?:[a-zA-Z0-9-]+\.)*binance\.com$"),
    re.compile(r"^generativelanguage\.googleapis\.com$"),
]

FORBIDDEN_PATH_SUBSTRINGS = [
    "/api/v3/order",
    "/api/v3/openOrders",
    "/api/v3/allOrders",
    "/api/v3/orderList",
]


def check_safe_url(url: str, is_mock: bool = False) -> None:
    """Validate that a target URL is not a production order or restricted endpoint.

    Raises:
        SafetyGuardError: if the URL targets a forbidden endpoint without a mock.
    """
    if is_mock:
        return

    parsed = urlparse(url)
    host = parsed.netloc.split(":")[0].lower()
    path = parsed.path

    for pattern in FORBIDDEN_HOST_PATTERNS:
        if pattern.search(host):
            for forbidden_path in FORBIDDEN_PATH_SUBSTRINGS:
                if forbidden_path in path:
                    msg = (
                        f"GOLDGUARD_SAFETY_GUARD: Direct access to production endpoint {url} "
                        "is prohibited without a mock transport."
                    )
                    raise SafetyGuardError(msg)
            if host == "generativelanguage.googleapis.com":
                msg = f"GOLDGUARD_SAFETY_GUARD: Direct unmocked call to {url} is forbidden."
                raise SafetyGuardError(msg)
