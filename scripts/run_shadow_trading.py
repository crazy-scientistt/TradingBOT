"""Shadow trading and autonomous research runner for GoldGuard."""

import argparse
import asyncio
import logging
import sys
from decimal import Decimal
from pathlib import Path

from goldguard.ai.decision import DecisionVetoEngine
from goldguard.backtest.engine import BacktestEngine
from goldguard.backtest.walk_forward import WalkForwardHarness
from goldguard.broker.paper import PaperBroker
from goldguard.context.engine import ContextEngine
from goldguard.context.playbook import ProfessionalChecklist
from goldguard.context.sources import OpenCodexSearchProvider
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.hermes.generator import StrategyProposalGenerator
from goldguard.hermes.loop import HermesLoopConfig, HermesResearchLoop
from goldguard.market.binance import SymbolFilters
from goldguard.memory.engine import MemoryBank
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
from goldguard.strategy.genome import trend_pullback_v1
from goldguard.strategy.promotion import PromotionPipeline
from goldguard.strategy.runtime import GenomeRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("goldguard.shadow")


async def main() -> int:
    parser = argparse.ArgumentParser(description="GoldGuard Autonomous Shadow Trader")
    parser.add_argument("--db", default="data/goldguard.db", help="Path to SQLite database")
    parser.add_argument(
        "--gateway-url", default="http://localhost:10100", help="OpenCodex Gateway URL"
    )
    parser.add_argument("--symbol", default="PAXGUSDT", help="Trading Symbol")
    parser.add_argument("--cash", default="100.0", help="Initial paper starting balance")
    parser.add_argument(
        "--autonomy", action="store_true", help="Enable autonomous strategy promotion"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    db.migrate()

    logger.info("Database initialized at %s", db_path)

    # Initialize Repositories
    ledger_repo = LedgerRepository(db)
    genome_repo = GenomeRepository(db)
    eval_repo = EvaluationRepository(db)
    prom_repo = PromotionRepository(db)
    quota_repo = QuotaRepository(db)
    refl_repo = ReflectionRepository(db)
    prov_repo = ProviderRepository(db)
    mem_bank = MemoryBank(refl_repo)

    # Seed baseline if not exists
    if not genome_repo.get_genome("trend-pullback-v1"):
        baseline = trend_pullback_v1()
        genome_repo.save_genome(baseline, origin="baseline", status="active")
        logger.info("Seeded active baseline genome: trend-pullback-v1")

    # Seed OpenCodex Gateway Provider
    prov_repo.upsert_provider(
        name="opencodex",
        kind="proxy",
        base_url=args.gateway_url,
        key_fingerprint="sk-mock-proxy",
        status="active",
    )
    prov_repo.set_route(
        role="decision",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
    )
    prov_repo.set_route(
        role="hermes",
        provider="opencodex",
        model="google-antigravity/gemini-3.7-flash",
    )

    # Gateway client
    gateway_client = GatewayClient(base_url=args.gateway_url)
    route_service = RouteService(prov_repo, gateway_client)
    decision_veto = DecisionVetoEngine(route_service=route_service)
    hermes_gen = StrategyProposalGenerator(gateway_client=gateway_client)

    # Context Engine with OpenCodex grounded search fallback
    search_provider = OpenCodexSearchProvider(gateway_client)
    _context_engine = ContextEngine(search_provider=search_provider, quota_repo=quota_repo)
    checklist = ProfessionalChecklist()

    # Broker & Risk Engine
    broker = PaperBroker(starting_cash=Decimal(args.cash))
    filters = SymbolFilters(
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.0001"),
        minimum_quantity=Decimal("0.0001"),
        maximum_quantity=Decimal("100"),
        minimum_notional=Decimal("5"),
    )
    risk_engine = RiskEngine(SAFE_DEFAULT_V1)
    runtime = GenomeRuntime()

    _coordinator = TradingCoordinator(
        broker=broker,
        genome_repo=genome_repo,
        ledger_repo=ledger_repo,
        runtime=runtime,
        risk_engine=risk_engine,
        checklist=checklist,
        ai_veto=decision_veto,
        filters=filters,
    )

    promotion_pipeline = PromotionPipeline(
        genome_repo=genome_repo,
        eval_repo=eval_repo,
        promotion_repo=prom_repo,
    )

    _hermes_loop = HermesResearchLoop(
        proposal_generator=hermes_gen,
        backtest_engine=BacktestEngine(),
        wf_harness=WalkForwardHarness(),
        promotion_pipeline=promotion_pipeline,
        genome_repo=genome_repo,
        quota_repo=quota_repo,
        memory_bank=mem_bank,
        config=HermesLoopConfig(max_iterations_per_day=10),
    )

    logger.info(
        "GoldGuard Shadow Trader is ACTIVE. Symbol: %s | Cash: %s USDT | Autonomy: %s",
        args.symbol,
        args.cash,
        args.autonomy,
    )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
