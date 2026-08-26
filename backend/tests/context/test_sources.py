import httpx
import pytest
from goldguard.context.sources import (
    OpenCodexSearchProvider,
    RawSearchResult,
    classify_tier,
    deduplicate_and_filter_sources,
    normalize_url,
)
from goldguard.providers.client import GatewayClient


def test_classify_tier_hierarchy() -> None:
    assert classify_tier("https://www.federalreserve.gov/newsevents.htm") == 1
    assert classify_tier("https://www.bls.gov/cpi/") == 1
    assert classify_tier("https://paxos.com/paxg") == 1
    assert classify_tier("https://api.binance.com") == 1

    assert classify_tier("https://www.reuters.com/markets/commodities/gold") == 2
    assert classify_tier("https://www.bloomberg.com/news/articles/gold") == 2
    assert classify_tier("https://www.ft.com/content/12345") == 2

    assert classify_tier("https://www.kitco.com/news/gold") == 3
    assert classify_tier("https://gold.org/research") == 3
    assert classify_tier("https://www.coindesk.com/markets") == 3

    assert classify_tier("https://random-crypto-blog.org/post/1") == 4
    assert classify_tier("https://medium.com/@trader/gold-signals") == 4


def test_url_normalization() -> None:
    raw = "https://www.REUTERS.com/article/gold?utm_source=twitter&utm_medium=social&ref=123"
    clean = normalize_url(raw)
    assert clean == "https://www.reuters.com/article/gold"


def test_deduplicate_and_filter_sources_domain_diversity() -> None:
    raw = [
        RawSearchResult("https://reuters.com/art1", "Reuters 1", "Content 1"),
        RawSearchResult("https://reuters.com/art2", "Reuters 2", "Content 2"),
        RawSearchResult("https://reuters.com/art3", "Reuters 3", "Content 3"),
        RawSearchResult("https://reuters.com/art1?utm_source=x", "Reuters 1 Dup", "Content 1"),
        RawSearchResult("https://bloomberg.com/art1", "Bloomberg 1", "Content B1"),
    ]

    sources = deduplicate_and_filter_sources(raw, max_per_domain=2)
    assert len(sources) == 3
    assert [s.url for s in sources] == [
        "https://reuters.com/art1",
        "https://reuters.com/art2",
        "https://bloomberg.com/art1",
    ]


@pytest.mark.asyncio
async def test_opencodex_search_provider_fallback() -> None:
    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-grounding",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Gold is steady near $2500 on Fed rate cut optimism.",
                        },
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        provider = OpenCodexSearchProvider(gateway)
        results = await provider.search("PAXGUSDT gold news")

    assert len(results) == 1
    assert "World Gold Council" in results[0].title
    assert "Fed rate cut optimism" in results[0].content
