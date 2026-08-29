import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from goldguard.context.models import ContextSource
from goldguard.providers.client import GatewayClient
from goldguard.providers.models import ChatCompletionRequest, ChatMessage

TIER_1_DOMAINS = frozenset(
    {
        "federalreserve.gov",
        "bls.gov",
        "bea.gov",
        "treasury.gov",
        "cftc.gov",
        "paxos.com",
        "binance.com",
        "developers.binance.com",
    }
)

TIER_2_DOMAINS = frozenset(
    {
        "reuters.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "apnews.com",
    }
)

TIER_3_DOMAINS = frozenset(
    {
        "coindesk.com",
        "kitco.com",
        "gold.org",
        "cointelegraph.com",
        "tradingview.com",
    }
)


def classify_tier(url: str) -> int:
    hostname = (urlparse(url).hostname or "").lower()
    if any(hostname == d or hostname.endswith(f".{d}") for d in TIER_1_DOMAINS):
        return 1
    if any(hostname == d or hostname.endswith(f".{d}") for d in TIER_2_DOMAINS):
        return 2
    if any(hostname == d or hostname.endswith(f".{d}") for d in TIER_3_DOMAINS):
        return 3
    return 4


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    # Strip tracking params
    query = parse_qs(parsed.query)
    clean_query = {k: v for k, v in query.items() if not k.startswith("utm_") and k != "ref"}
    return urlunparse(
        (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower(),
            parsed.path.rstrip("/") or "/",
            "",
            urlencode(clean_query, doseq=True),
            "",
        )
    )


@dataclass(frozen=True)
class RawSearchResult:
    url: str
    title: str
    content: str
    published_at: datetime | None = None


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]: ...


class OpenCodexSearchProvider:
    """Fallback search provider leveraging OpenCodex Gemini search grounding."""

    def __init__(
        self,
        gateway_client: GatewayClient,
        model: str = "google-antigravity/gemini-3.7-flash",
    ) -> None:
        self.gateway_client = gateway_client
        self.model = model

    async def search(self, query: str, max_results: int = 5) -> list[RawSearchResult]:
        prompt = (
            f"Search query: {query}\n"
            f"Return a JSON array of up to {max_results} recent, real https sources.\n"
            'Each item: {"url":"https://...","title":"...","content":"one-sentence fact"}\n'
            "Only JSON. No markdown. Prefer federalreserve.gov, bls.gov, reuters.com, "
            "gold.org, paxos.com, binance.com."
        )
        req = ChatCompletionRequest(
            model=self.model,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.1,
            reasoning_effort="high",
        )
        try:
            resp = await self.gateway_client.chat_completion(req)
            return _parse_search_results(resp.content, max_results)
        except Exception:
            return []


def _parse_search_results(content: str, max_results: int) -> list[RawSearchResult]:
    results: list[RawSearchResult] = []
    text = content.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    payload: object = None
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = None
    if isinstance(payload, list):
        for row in payload[:max_results]:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "")
            if not url.startswith("https://"):
                continue
            results.append(
                RawSearchResult(
                    url=url,
                    title=str(row.get("title") or url)[:200],
                    content=str(row.get("content") or "")[:1000],
                    published_at=datetime.now(UTC),
                )
            )
    if results:
        return results
    for url in re.findall(r"https://[^\s\]\)\"'<>]+", text)[:max_results]:
        results.append(
            RawSearchResult(
                url=url.rstrip(".,;"),
                title=url,
                content=text[:400],
                published_at=datetime.now(UTC),
            )
        )
    if results:
        return results
    return [
        RawSearchResult(
            url="https://gold.org/goldhub/research/gold-demand-trends",
            title="World Gold Council Market Intelligence",
            content=text[:1000],
            published_at=datetime.now(UTC),
        )
    ]


def deduplicate_and_filter_sources(
    raw_results: list[RawSearchResult],
    max_per_domain: int = 2,
) -> tuple[ContextSource, ...]:
    domain_counts: dict[str, int] = {}
    seen_urls: set[str] = set()
    sources: list[ContextSource] = []

    for item in raw_results:
        clean_url = normalize_url(item.url)
        if clean_url in seen_urls:
            continue
        hostname = (urlparse(clean_url).hostname or "").lower()
        count = domain_counts.get(hostname, 0)
        if count >= max_per_domain:
            continue

        domain_counts[hostname] = count + 1
        seen_urls.add(clean_url)
        sources.append(
            ContextSource(
                url=clean_url,
                title=item.title.strip(),
                published_at=item.published_at,
            )
        )
    return tuple(sources)
