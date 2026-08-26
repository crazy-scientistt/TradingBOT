import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from goldguard.backtest.engine import BacktestEngine
from goldguard.backtest.walk_forward import WalkForwardHarness
from goldguard.domain.models import Candle
from goldguard.hermes.generator import StrategyProposalGenerator
from goldguard.hermes.loop import HermesLoopConfig, HermesResearchLoop
from goldguard.memory.engine import MemoryBank
from goldguard.providers.client import GatewayClient
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    EvaluationRepository,
    GenomeRepository,
    PromotionRepository,
    QuotaRepository,
    ReflectionRepository,
)
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.promotion import PromotionPipeline

START = datetime(2023, 1, 1, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


def generate_market_data(num_days: int = 15) -> list[Candle]:
    candles: list[Candle] = []
    curr = START
    base_price = Decimal("2000")
    for i in range(num_days * 30):
        cycle = Decimal(str((i % 30) - 15)) / Decimal("10")
        close_p = base_price + Decimal(str(i // 30)) + cycle
        c = Candle(
            symbol="PAXGUSDT",
            timeframe="15m",
            open_time=curr,
            close_time=curr + timedelta(minutes=15) - timedelta(milliseconds=1),
            open=close_p - Decimal("1"),
            high=close_p + Decimal("3"),
            low=close_p - Decimal("3"),
            close=close_p,
            volume=Decimal("15"),
            closed=True,
        )
        candles.append(c)
        curr += timedelta(minutes=15)
    return candles


@pytest.mark.asyncio
async def test_hermes_research_loop_quota_exhaustion_blocks_iteration(
    database: Database,
) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)
    quota_repo = QuotaRepository(database)
    refl_repo = ReflectionRepository(database)
    mem_bank = MemoryBank(refl_repo)

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        generator = StrategyProposalGenerator(gateway_client=gateway)

        loop = HermesResearchLoop(
            proposal_generator=generator,
            backtest_engine=BacktestEngine(),
            wf_harness=WalkForwardHarness(),
            promotion_pipeline=pipeline,
            genome_repo=genome_repo,
            quota_repo=quota_repo,
            memory_bank=mem_bank,
            config=HermesLoopConfig(max_backtest_calls=1),
        )

        candles = generate_market_data(num_days=10)
        now = datetime(2026, 8, 26, 12, tzinfo=UTC)

        # 1. First iteration consumes the 1 allowed call
        quota_repo.consume_backtest("2026-08-26", max_limit=1)

        # 2. Next step attempt must return quota_exhausted
        result = await loop.step(
            candles_15m=candles,
            market_summary="Normal volatility",
            now=now,
        )
        assert result.status == "quota_exhausted"


@pytest.mark.asyncio
async def test_hermes_research_loop_successful_proposal_flow(database: Database) -> None:
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)
    quota_repo = QuotaRepository(database)
    refl_repo = ReflectionRepository(database)
    mem_bank = MemoryBank(refl_repo)

    # Set up baseline active genome
    active_genome = trend_pullback_v1()
    genome_repo.save_genome(active_genome, origin="baseline", status="active")

    pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    valid_proposal = {
        "hypothesis": "Adjust volume ratio threshold to filter noise.",
        "evidence_refs": ["ref-1"],
        "parameter_changes": {
            "minimum_volume_ratio": "0.85",
        },
    }

    async def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-loop-1",
                "model": "google-antigravity/gemini-3.7-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(valid_proposal)},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        generator = StrategyProposalGenerator(gateway_client=gateway)

        loop = HermesResearchLoop(
            proposal_generator=generator,
            backtest_engine=BacktestEngine(),
            wf_harness=WalkForwardHarness(),
            promotion_pipeline=pipeline,
            genome_repo=genome_repo,
            quota_repo=quota_repo,
            memory_bank=mem_bank,
            config=HermesLoopConfig(max_backtest_calls=10),
        )

        candles = generate_market_data(num_days=10)
        now = datetime(2026, 8, 26, 12, tzinfo=UTC)

        result = await loop.step(
            candles_15m=candles,
            market_summary="Normal volatility",
            now=now,
        )

        assert result.status in ("promoted_candidate", "dev_failed", "val_failed")
        assert result.candidate_genome_id is not None
        # Assert evaluation row written to database
        evals = eval_repo.get_evaluations_for_genome(result.candidate_genome_id)
        assert len(evals) >= 1
