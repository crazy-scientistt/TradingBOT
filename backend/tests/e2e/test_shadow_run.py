import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from goldguard.ai.decision import DecisionRequest, DecisionVetoEngine
from goldguard.backtest.engine import BacktestEngine
from goldguard.backtest.walk_forward import WalkForwardHarness
from goldguard.broker.paper import PaperBroker
from goldguard.context.models import ContextItem, ContextSnapshot, ContextSource
from goldguard.context.playbook import ChecklistInputs, ChecklistResult
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import AiDecision, CandidateAction, ChecklistAction
from goldguard.domain.models import Candle, Quote
from goldguard.hermes.generator import StrategyProposalGenerator
from goldguard.hermes.loop import HermesLoopConfig, HermesResearchLoop
from goldguard.market.binance import SymbolFilters
from goldguard.memory.engine import MemoryBank
from goldguard.memory.reflections import ReflectionEngine, TradeOutcome
from goldguard.providers.client import GatewayClient
from goldguard.providers.service import RouteService
from goldguard.risk.engine import RiskEngine
from goldguard.services.coordinator import TradingCoordinator
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    EvaluationRepository,
    GenomeRepository,
    LedgerRepository,
    PromotionRepository,
    ProviderRepository,
    QuotaRepository,
    ReflectionRepository,
)
from goldguard.strategy.engine import StrategyFeatures
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.promotion import PromotionPipeline
from goldguard.strategy.runtime import GenomeRuntime

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "goldguard_shadow.db")
    db.migrate()
    return db


def make_candle(index: int, base: Decimal, delta: Decimal) -> Candle:
    open_time = START + timedelta(minutes=15 * index)
    close_time = open_time + timedelta(minutes=15) - timedelta(milliseconds=1)
    p = base + delta
    return Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=close_time,
        open=p,
        high=p + Decimal("2"),
        low=p - Decimal("2"),
        close=p,
        volume=Decimal("15"),
        closed=True,
    )


class MockChecklist:
    def evaluate(self, inputs: ChecklistInputs) -> ChecklistResult:
        assert inputs.context.sources
        return ChecklistResult(action=ChecklistAction.PASS, reason_codes=("PRO_PASS",))


class MockVeto:
    def decide(self, request: DecisionRequest) -> Any:
        assert request.candidate is CandidateAction.ENTRY_CANDIDATE
        return SimpleNamespace(
            decision=AiDecision.APPROVE_ENTRY,
            confidence=85,
            reason_codes=("TREND_ALIGNED", "LIQUIDITY_GOOD"),
        )


def fresh_context(now: datetime) -> ContextSnapshot:
    return ContextSnapshot.build(
        fetched_at=now,
        sources=(
            ContextSource(
                url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                title="FOMC calendar",
                published_at=now,
            ),
        ),
        items=(
            ContextItem(
                summary="No blocking macro release is active during this paper run.",
                driver="rates",
                direction="neutral",
                severity="low",
                published_at=now,
                source_indexes=(0,),
                contradictory=False,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_end_to_end_shadow_trading_and_research_cycle(database: Database) -> None:
    # 1. Repositories
    ledger_repo = LedgerRepository(database)
    genome_repo = GenomeRepository(database)
    eval_repo = EvaluationRepository(database)
    prom_repo = PromotionRepository(database)
    quota_repo = QuotaRepository(database)
    refl_repo = ReflectionRepository(database)
    prov_repo = ProviderRepository(database)
    mem_bank = MemoryBank(refl_repo)

    # 2. Seed active baseline genome & paper session
    active_genome = trend_pullback_v1()
    genome_repo.save_genome(active_genome, origin="baseline", status="active")
    session_id = ledger_repo.create_paper_session(initial_balance=Decimal("100.0"))

    # 3. Seed AI Provider and Model Route
    prov_repo.upsert_provider(
        name="opencodex",
        kind="proxy",
        base_url="http://localhost:10100",
        key_fingerprint="sk-mock-1234",
        status="active",
    )
    prov_repo.set_route(
        role="decision",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
    )

    # Mock gateway response for Decision Veto and Hermes Proposal
    async def mock_gateway_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode())
        messages = body.get("messages", [])
        prompt_str = " ".join(m.get("content", "") for m in messages)

        if "decision" in prompt_str.lower() or "veto" in prompt_str.lower():
            return httpx.Response(
                200,
                json={
                    "id": "chat-decision",
                    "model": "google-antigravity/gemini-3.7-flash",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "decision": "APPROVE_ENTRY",
                                        "confidence": 85,
                                        "reason_codes": ["TREND_ALIGNED", "LIQUIDITY_GOOD"],
                                        "rationale": "Trend and momentum are aligned.",
                                        "memory_refs": [],
                                    }
                                ),
                            },
                        }
                    ],
                },
            )
        else:
            return httpx.Response(
                200,
                json={
                    "id": "chat-hermes",
                    "model": "google-antigravity/gemini-3.7-flash",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "hypothesis": "Volume filter improves consistency.",
                                        "evidence_refs": ["ref-f-1"],
                                        "parameter_changes": {
                                            "minimum_volume_ratio": "0.90",
                                        },
                                    }
                                ),
                            },
                        }
                    ],
                },
            )

    transport = httpx.MockTransport(mock_gateway_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gateway_client = GatewayClient(base_url="http://localhost:10100", http_client=http_client)
        route_service = RouteService(prov_repo)
        decision_veto = DecisionVetoEngine(
            route_service=route_service,
            gateway_client=gateway_client,
        )
        hermes_generator = StrategyProposalGenerator(gateway_client=gateway_client)

        # Test live async decision veto engine directly
        dec_req = DecisionRequest(
            candidate=CandidateAction.ENTRY_CANDIDATE,
            strategy_version="trend-pullback-v1",
            features={"rsi": 52.0, "volume_ratio": 1.2},
            context={"macro_bias": "bullish"},
            memory_summaries=(),
        )
        veto_assessment = await decision_veto.decide(dec_req)
        assert veto_assessment.decision == AiDecision.APPROVE_ENTRY

        broker = PaperBroker(
            starting_cash=Decimal("100.0"),
            fee_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0002"),
        )
        filters = SymbolFilters(
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.0001"),
            minimum_quantity=Decimal("0.0001"),
            maximum_quantity=Decimal("100"),
            minimum_notional=Decimal("5"),
        )
        runtime = GenomeRuntime()
        risk_engine = RiskEngine(SAFE_DEFAULT_V1)

        coordinator = TradingCoordinator(
            broker=broker,
            genome_repo=genome_repo,
            ledger_repo=ledger_repo,
            runtime=runtime,
            risk_engine=risk_engine,
            checklist=MockChecklist(),
            ai_veto=MockVeto(),
            filters=filters,
        )

        candles_15m: list[Candle] = []
        for i in range(40):
            delta = Decimal(str(i % 5))
            c = make_candle(i, Decimal("2500"), delta)
            candles_15m.append(c)

            quote = Quote(
                bid=c.close - Decimal("0.05"),
                ask=c.close + Decimal("0.05"),
                observed_at=c.close_time,
            )
            features = StrategyFeatures(
                previous_close=float(c.close - Decimal("1")),
                latest_close=float(c.close),
                ema20_15m=2498.0,
                ema50_15m=2495.0,
                previous_rsi14=48.0,
                rsi14=52.0,
                atr14=4.5,
                atr_rate=0.0018,
                volume_ratio=1.2,
                spread_rate=0.0001,
                latest_close_1h=float(c.close),
                ema50_1h=2490.0,
                ema200_1h=2470.0,
                ema50_slope_1h=0.002,
                consecutive_closes_below_ema50=0,
                sufficient_history=True,
                contiguous=True,
                quote_fresh=True,
            )

            coordinator.monitor_open_position(quote=quote)
            coordinator.scan_closed_candle(
                symbol="PAXGUSDT",
                closed_at=c.close_time,
                quote=quote,
                features=features,
                context_snapshot=fresh_context(c.close_time),
                account_scope=session_id,
            )

        test_quote = Quote(bid=Decimal("2500"), ask=Decimal("2500"), observed_at=START)
        assert broker.equity(test_quote) > Decimal("0")

        # Record forward trade reflection in MemoryBank
        refl_engine = ReflectionEngine()
        f_outcome = TradeOutcome(
            trade_id="f-trade-e2e",
            namespace="forward",
            hypothesis="Trend pullback follow-through",
            realized_pnl=Decimal("1.85"),
            maximum_adverse_excursion=Decimal("-0.25"),
            maximum_favorable_excursion=Decimal("2.10"),
            fees=Decimal("0.18"),
            exit_reason="TAKE_PROFIT",
            regime_tags=("trend", "low-volatility"),
            context_error=False,
            rule_adherent=True,
        )
        mem_bank.record_reflection(refl_engine.create(f_outcome))
        stored_refs = refl_repo.list_reflections(namespace="forward")
        assert len(stored_refs) >= 1

        # Run Hermes Autonomous Research Loop step
        pipeline = PromotionPipeline(
            genome_repo=genome_repo,
            eval_repo=eval_repo,
            promotion_repo=prom_repo,
        )
        loop = HermesResearchLoop(
            proposal_generator=hermes_generator,
            backtest_engine=BacktestEngine(),
            wf_harness=WalkForwardHarness(),
            promotion_pipeline=pipeline,
            genome_repo=genome_repo,
            quota_repo=quota_repo,
            memory_bank=mem_bank,
            config=HermesLoopConfig(max_backtest_calls=20),
        )

        loop_res = await loop.step(
            candles_15m=candles_15m,
            market_summary="Low volatility trend continuation",
            now=START + timedelta(days=1),
        )

        assert loop_res.status in ("promoted_candidate", "dev_failed", "val_failed")
        assert loop_res.candidate_genome_id is not None

        evals = eval_repo.get_evaluations_for_genome(loop_res.candidate_genome_id)
        assert len(evals) >= 1

        usage = quota_repo.get_usage((START + timedelta(days=1)).strftime("%Y-%m-%d"))
        assert usage[0] >= 1
