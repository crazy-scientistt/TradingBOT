from decimal import Decimal

from goldguard.memory.reflections import (
    ReflectionEngine,
    ReflectionStore,
    TradeOutcome,
)


def outcome(
    identifier: str,
    *,
    namespace: str = "forward",
    pnl: str = "1.25",
    fees: str = "0.15",
    mae: str = "-0.30",
    mfe: str = "1.80",
    exit_reason: str = "TAKE_PROFIT",
    regime: tuple[str, ...] = ("trend", "normal-volatility"),
    context_error: bool = False,
    rule_adherent: bool = True,
) -> TradeOutcome:
    return TradeOutcome(
        trade_id=identifier,
        namespace=namespace,  # type: ignore[arg-type]
        hypothesis="Pullback recovery should continue with the hourly trend.",
        realized_pnl=Decimal(pnl),
        maximum_adverse_excursion=Decimal(mae),
        maximum_favorable_excursion=Decimal(mfe),
        fees=Decimal(fees),
        exit_reason=exit_reason,
        regime_tags=regime,
        context_error=context_error,
        rule_adherent=rule_adherent,
    )


def test_closed_trade_lesson_codes() -> None:
    engine = ReflectionEngine()

    # 1. Clean TP
    tp_ref = engine.create(outcome("t-tp", pnl="2.50", exit_reason="TAKE_PROFIT"))
    assert tp_ref.lesson_code == "TP_CLEAN"

    # 2. Stop hit with adverse expansion
    sl_ref = engine.create(
        outcome("t-sl", pnl="-1.50", mae="-1.50", mfe="0.10", exit_reason="STOP_LOSS")
    )
    assert sl_ref.lesson_code == "STOP_HIT_EXPANSION"

    # 3. Chop whipsaw (ran into positive MFE before getting stopped out)
    chop_ref = engine.create(
        outcome("t-chop", pnl="-1.50", mae="-1.50", mfe="1.50", exit_reason="STOP_LOSS")
    )
    assert chop_ref.lesson_code == "CHOP_WHIPSAW"

    # 4. Regime shift exit
    regime_ref = engine.create(outcome("t-regime", pnl="-0.50", exit_reason="REGIME_INVALIDATION"))
    assert regime_ref.lesson_code == "REGIME_SHIFT"

    # 5. High fee drag
    fee_ref = engine.create(outcome("t-fee", pnl="-0.20", fees="0.50", exit_reason="STOP_LOSS"))
    assert fee_ref.lesson_code == "FEE_DRAG_HIGH"


def test_retrieval_is_namespace_isolated_regime_matched_and_limited() -> None:
    store = ReflectionStore()
    engine = ReflectionEngine()
    for item in (
        outcome("forward-win-1"),
        outcome("forward-loss-1", pnl="-0.70"),
        outcome("forward-win-2"),
        outcome("historical-win", namespace="historical"),
        outcome("range-win", regime=("range", "normal-volatility")),
    ):
        store.add(engine.create(item))

    relevant = store.relevant(
        namespace="forward",
        regime_tags=("trend", "normal-volatility"),
        limit=3,
    )

    assert len(relevant) == 3
    assert {item.trade_id for item in relevant} == {
        "forward-win-1",
        "forward-loss-1",
        "forward-win-2",
    }
    assert {item.namespace for item in relevant} == {"forward"}


def test_rule_violation_is_never_mislabeled_as_strategy_learning() -> None:
    bad = outcome("trade-violation", pnl="-1", rule_adherent=False)
    reflection = ReflectionEngine().create(bad)

    assert reflection.lesson_code == "PROCESS_VIOLATION"
    assert "strategy" not in reflection.lesson.lower()
