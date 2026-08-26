from decimal import Decimal

from goldguard.memory.reflections import ReflectionEngine, ReflectionStore, TradeOutcome


def outcome(
    identifier: str,
    *,
    namespace: str = "forward",
    pnl: str = "1.25",
    regime: tuple[str, ...] = ("trend", "normal-volatility"),
) -> TradeOutcome:
    return TradeOutcome(
        trade_id=identifier,
        namespace=namespace,
        hypothesis="Pullback recovery should continue with the hourly trend.",
        realized_pnl=Decimal(pnl),
        maximum_adverse_excursion=Decimal("-0.30"),
        maximum_favorable_excursion=Decimal("1.80"),
        fees=Decimal("0.15"),
        exit_reason="TAKE_PROFIT" if Decimal(pnl) > 0 else "STOP_LOSS",
        regime_tags=regime,
        context_error=False,
        rule_adherent=True,
    )


def test_closed_trade_becomes_a_complete_immutable_reflection() -> None:
    reflection = ReflectionEngine().create(outcome("trade-1"))

    assert reflection.trade_id == "trade-1"
    assert reflection.namespace == "forward"
    assert reflection.net_pnl == Decimal("1.25")
    assert reflection.fee_drag == Decimal("0.15")
    assert reflection.maximum_adverse_excursion == Decimal("-0.30")
    assert reflection.maximum_favorable_excursion == Decimal("1.80")
    assert reflection.lesson_code == "VALID_SETUP_WIN"
    assert reflection.identifier


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
    bad = outcome("trade-violation", pnl="-1")
    bad = TradeOutcome(**{**bad.__dict__, "rule_adherent": False})

    reflection = ReflectionEngine().create(bad)

    assert reflection.lesson_code == "PROCESS_VIOLATION"
    assert "strategy" not in reflection.lesson.lower()
