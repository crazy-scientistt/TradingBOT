import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from goldguard.observability.events import AgentEvent
from goldguard.storage.database import Database
from goldguard.strategy.genome import StrategyGenome, genome_hash

if TYPE_CHECKING:
    from goldguard.ai.gemini import AiAssessment
    from goldguard.context.models import ContextSnapshot
    from goldguard.domain.models import Candle


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


@dataclass(frozen=True)
class PaperSession:
    identifier: str
    initial_balance: Decimal
    created_at: str


@dataclass(frozen=True)
class RouteRow:
    id: str
    role: str
    provider: str
    model: str
    pinned: bool
    version: int
    created_at: str


@dataclass(frozen=True)
class ProviderRow:
    name: str
    kind: str
    base_url: str
    key_fingerprint: str
    status: str
    last_probe_at: str | None
    created_at: str


@dataclass(frozen=True)
class MeasuredRiskInputs:
    """The risk engine's circuit-breaker inputs, measured from the ledger.

    Frozen because the risk engine's decision must not be adjustable after measurement.
    """

    rolling_24h_loss_rate: Decimal
    peak_drawdown_rate: Decimal
    consecutive_losses: int
    minutes_since_exit: int | None
    trade_count: int


class LedgerRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_paper_session(self, initial_balance: Decimal) -> str:
        if initial_balance <= 0:
            raise ValueError("paper starting balance must be positive")
        identifier = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO paper_accounts(id, initial_balance_text, created_at) VALUES (?, ?, ?)",
                (identifier, str(initial_balance), utc_now_iso()),
            )
            connection.execute(
                "UPDATE app_state SET current_paper_account_id = ? WHERE singleton = 1",
                (identifier,),
            )
        return identifier

    def current_paper_session_id(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT current_paper_account_id FROM app_state WHERE singleton = 1"
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def list_paper_sessions(self) -> list[PaperSession]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, initial_balance_text, created_at FROM paper_accounts ORDER BY rowid"
            ).fetchall()
        return [
            PaperSession(
                identifier=str(row["id"]),
                initial_balance=Decimal(str(row["initial_balance_text"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def get_paper_session(self, session_id: str) -> PaperSession | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id, initial_balance_text, created_at FROM paper_accounts WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return PaperSession(
            identifier=str(row["id"]),
            initial_balance=Decimal(str(row["initial_balance_text"])),
            created_at=str(row["created_at"]),
        )

    def save_settings_version(self, version: str, payload: dict[str, Any]) -> str:
        encoded = canonical_json(payload)
        identifier = hashlib.sha256(f"{version}\n{encoded}".encode()).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO settings_versions"
                "(id, version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (identifier, version, encoded, utc_now_iso()),
            )
        return identifier

    def activate_settings(self, version: str, payload: dict[str, Any]) -> str:
        identifier = self.save_settings_version(version, payload)
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE app_state SET active_settings_id = ? WHERE singleton = 1",
                (identifier,),
            )
        return identifier

    def load_active_settings(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.payload_json
                FROM app_state s
                JOIN settings_versions v ON v.id = s.active_settings_id
                WHERE s.singleton = 1
                """
            ).fetchone()
        if row is None or row[0] is None:
            return None
        payload = json.loads(str(row["payload_json"]))
        return payload if isinstance(payload, dict) else None

    def append_audit(self, actor: str, action: str, details: dict[str, Any]) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO audit_events(occurred_at, actor, action, details_json) "
                "VALUES (?, ?, ?, ?)",
                (utc_now_iso(), actor, action, canonical_json(details)),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("audit insert returned no identifier")
        return int(cursor.lastrowid)

    def record_state_transition(
        self,
        *,
        from_state: str,
        to_state: str,
        reason: str,
        occurred_at: str | None = None,
    ) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO state_transitions(from_state, to_state, reason, occurred_at) "
                "VALUES (?, ?, ?, ?)",
                (from_state, to_state, reason, occurred_at or utc_now_iso()),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("state transition insert returned no identifier")
        return int(cursor.lastrowid)

    def record_decision_chain(
        self,
        *,
        mode: str,
        account_scope: str,
        symbol: str,
        timeframe: str,
        candle_close_time: str,
    ) -> str:
        material = "|".join((mode, account_scope, symbol, timeframe, candle_close_time))
        identifier = hashlib.sha256(material.encode()).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO decision_chains"
                "(id, mode, account_scope, symbol, timeframe, candle_close_time, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    mode,
                    account_scope,
                    symbol,
                    timeframe,
                    candle_close_time,
                    utc_now_iso(),
                ),
            )
        return identifier

    def count_decision_chains(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT count(*) FROM decision_chains").fetchone()
        if row is None:
            raise RuntimeError("decision count returned no row")
        return int(row[0])

    def save_context_snapshot(
        self,
        *,
        snapshot: "ContextSnapshot",
        event_time: datetime | None = None,
        freshness: str,
    ) -> str:
        identifier = snapshot.content_hash
        summary = {
            "fetched_at": snapshot.fetched_at.isoformat(),
            "conflict_level": snapshot.conflict_level,
            "prompt_injection_suspected": snapshot.prompt_injection_suspected,
            "items": [
                {
                    "summary": item.summary,
                    "driver": item.driver,
                    "direction": item.direction,
                    "severity": item.severity,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "source_indexes": list(item.source_indexes),
                    "contradictory": item.contradictory,
                }
                for item in snapshot.items
            ],
        }
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO context_snapshots(
                    id, fetched_at, event_time, freshness, conflict_level,
                    content_hash, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    snapshot.fetched_at.isoformat(),
                    event_time.isoformat() if event_time else None,
                    freshness,
                    snapshot.conflict_level,
                    snapshot.content_hash,
                    canonical_json(summary),
                ),
            )
            for index, source in enumerate(snapshot.sources):
                source_id = hashlib.sha256(
                    f"{identifier}|{index}|{source.url}".encode()
                ).hexdigest()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO context_sources(
                        id, context_snapshot_id, url, title, published_at, source_tier
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        identifier,
                        source.url,
                        source.title,
                        source.published_at.isoformat() if source.published_at else None,
                        source.tier,
                    ),
                )
        return identifier

    def save_ai_decision(
        self,
        *,
        decision_chain_id: str,
        context_snapshot_id: str | None,
        assessment: "AiAssessment",
    ) -> str:
        identifier = hashlib.sha256(f"ai|{decision_chain_id}".encode()).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO ai_decisions(
                    id, decision_chain_id, context_snapshot_id, decision,
                    confidence, reason_codes_json, prompt_hash, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    decision_chain_id,
                    context_snapshot_id,
                    assessment.decision.value,
                    assessment.confidence,
                    canonical_json(assessment.reason_codes),
                    assessment.prompt_hash,
                    assessment.model,
                    utc_now_iso(),
                ),
            )
        return identifier

    def save_risk_decision(
        self,
        *,
        decision_chain_id: str,
        approved: bool,
        details: dict[str, Any],
    ) -> str:
        identifier = hashlib.sha256(f"risk|{decision_chain_id}".encode()).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO risk_decisions(
                    id, decision_chain_id, approved, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    decision_chain_id,
                    1 if approved else 0,
                    canonical_json(details),
                    utc_now_iso(),
                ),
            )
        return identifier

    def latest_equity_snapshot(self, paper_account_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM equity_snapshots
                WHERE paper_account_id = ?
                ORDER BY observed_at DESC, rowid DESC
                LIMIT 1
                """,
                (paper_account_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_equity_snapshots(
        self,
        paper_account_id: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Oldest-first equity history. Empty until the runtime records its first snapshot."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT equity_text, cash_text, observed_at FROM equity_snapshots
                WHERE paper_account_id = ?
                ORDER BY observed_at DESC, rowid DESC
                LIMIT ?
                """,
                (paper_account_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def realized_pnl_since(self, paper_account_id: str, since: datetime) -> Decimal:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT realized_pnl_text FROM trades
                WHERE paper_account_id = ? AND status = 'CLOSED' AND closed_at >= ?
                """,
                (paper_account_id, since.isoformat()),
            ).fetchall()
        return sum(
            (Decimal(str(row["realized_pnl_text"] or "0")) for row in rows),
            start=Decimal("0"),
        )

    def measure_risk_inputs(
        self,
        paper_account_id: str,
        *,
        equity: Decimal,
        now: datetime | None = None,
    ) -> MeasuredRiskInputs:
        """Measure the risk engine's circuit-breaker inputs from recorded rows only.

        Every value traces to a closed trade or an equity snapshot; nothing is estimated.
        `minutes_since_exit` is None when no trade has ever closed, so the caller can tell
        "there is no cooldown to serve" apart from "the cooldown has elapsed".
        """
        moment = now or datetime.now(UTC)
        realized_24h = self.realized_pnl_since(paper_account_id, moment - timedelta(hours=24))
        # The window's opening equity is the current equity backed out by the realized flow,
        # which needs no snapshot at the exact window boundary to be exact.
        window_open_equity = equity - realized_24h
        loss_rate = Decimal("0")
        if realized_24h < 0 and window_open_equity > 0:
            loss_rate = -realized_24h / window_open_equity

        peak = equity
        for snapshot in self.list_equity_snapshots(paper_account_id):
            peak = max(peak, Decimal(str(snapshot["equity_text"])))
        drawdown = (peak - equity) / peak if peak > equity and peak > 0 else Decimal("0")

        closed = sorted(
            (
                trade
                for trade in self.list_trades(paper_account_id)
                if str(trade["status"]) == "CLOSED" and trade["closed_at"]
            ),
            key=lambda trade: str(trade["closed_at"]),
            reverse=True,
        )
        streak = 0
        for trade in closed:
            if Decimal(str(trade["realized_pnl_text"] or "0")) >= 0:
                break
            streak += 1

        minutes_since_exit: int | None = None
        if closed:
            last_exit = datetime.fromisoformat(str(closed[0]["closed_at"]))
            if last_exit.tzinfo is None:
                last_exit = last_exit.replace(tzinfo=UTC)
            minutes_since_exit = max(int((moment - last_exit).total_seconds() // 60), 0)

        return MeasuredRiskInputs(
            rolling_24h_loss_rate=loss_rate,
            peak_drawdown_rate=drawdown,
            consecutive_losses=streak,
            minutes_since_exit=minutes_since_exit,
            trade_count=len(closed),
        )

    def count_runtime_errors_since(self, since: datetime) -> int:
        """Count durable runtime error health events after ``since``.

        An empty table is a measured zero; no in-memory exception counter is promoted to
        canary evidence because it would disappear on restart.
        """
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM system_health_events "
                "WHERE occurred_at >= ? AND lower(status) IN ('error', 'failed')",
                (since.isoformat(),),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def record_runtime_error(self, detail: str, *, occurred_at: datetime | None = None) -> str:
        """Persist one runtime failure so restart-safe canary budgets can observe it."""
        identifier = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO system_health_events(" 
                "id, component, status, details_json, occurred_at) "
                "VALUES (?, 'trading_runtime', 'error', ?, ?)",
                (
                    identifier,
                    canonical_json({"error": detail}),
                    (occurred_at or datetime.now(UTC)).isoformat(),
                ),
            )
        return identifier

    def latest_context_snapshot(self) -> dict[str, Any] | None:
        """Most recent persisted context snapshot with its sources, or None."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM context_snapshots
                ORDER BY fetched_at DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            sources = connection.execute(
                """
                SELECT url, title, published_at, source_tier FROM context_sources
                WHERE context_snapshot_id = ?
                ORDER BY rowid
                """,
                (str(row["id"]),),
            ).fetchall()
        snapshot = dict(row)
        snapshot["summary"] = json.loads(str(row["summary_json"]))
        snapshot["sources"] = [dict(source) for source in sources]
        return snapshot

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Decision chains joined to the AI verdict and risk verdict that produced them.

        The chain row alone carries no reason, so the audit tab used to show empty cells.
        """
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    dc.id, dc.mode, dc.account_scope, dc.symbol, dc.timeframe,
                    dc.candle_close_time, dc.created_at,
                    ai.decision AS ai_decision,
                    ai.confidence AS ai_confidence,
                    ai.reason_codes_json AS ai_reason_codes_json,
                    ai.model AS ai_model,
                    rd.approved AS risk_approved,
                    rd.details_json AS risk_details_json
                FROM decision_chains dc
                LEFT JOIN ai_decisions ai ON ai.decision_chain_id = dc.id
                LEFT JOIN risk_decisions rd ON rd.decision_chain_id = dc.id
                ORDER BY dc.candle_close_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        decisions: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            raw_codes = record.pop("ai_reason_codes_json", None)
            record["ai_reason_codes"] = json.loads(str(raw_codes)) if raw_codes else []
            raw_details = record.pop("risk_details_json", None)
            details = json.loads(str(raw_details)) if raw_details else {}
            record["risk_reason_codes"] = details.get("reason_codes", [])
            record["plan"] = details.get("plan")
            record["risk_approved"] = (
                None if record["risk_approved"] is None else bool(record["risk_approved"])
            )
            decisions.append(record)
        return decisions

    def list_order_fills(self, paper_account_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    o.id AS order_id,
                    o.client_order_id,
                    o.side,
                    o.status,
                    o.created_at AS order_created_at,
                    f.id AS fill_id,
                    f.price_text,
                    f.quantity_text,
                    f.fee_text,
                    f.occurred_at
                FROM orders o
                LEFT JOIN fills f ON f.order_id = o.id
                WHERE o.paper_account_id = ?
                ORDER BY f.occurred_at ASC, o.created_at ASC
                """,
                (paper_account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_trades(self, paper_account_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM trades
                WHERE paper_account_id = ?
                ORDER BY opened_at ASC, id ASC
                """,
                (paper_account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def load_trade_plan(
        self,
        *,
        paper_account_id: str,
        opened_at: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT rd.details_json
                FROM risk_decisions rd
                INNER JOIN decision_chains dc ON dc.id = rd.decision_chain_id
                WHERE dc.account_scope = ?
                  AND dc.candle_close_time = ?
                  AND rd.approved = 1
                ORDER BY rd.created_at DESC
                LIMIT 1
                """,
                (paper_account_id, opened_at),
            ).fetchone()
        if row is None:
            return None
        details = json.loads(row["details_json"])
        plan = details.get("plan")
        return plan if isinstance(plan, dict) else None


class MarketCandleRepository:
    """Durable candle store. Prices round-trip as text so no float ever touches money."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_candles(self, candles: Sequence["Candle"], *, source: str) -> int:
        if not candles:
            return 0
        rows = [
            (
                candle.symbol,
                candle.timeframe,
                candle.open_time.isoformat(),
                candle.close_time.isoformat(),
                str(candle.open),
                str(candle.high),
                str(candle.low),
                str(candle.close),
                str(candle.volume),
                hashlib.sha256(
                    f"{source}|{candle.symbol}|{candle.timeframe}|"
                    f"{candle.open_time.isoformat()}|{candle.close}".encode()
                ).hexdigest(),
            )
            for candle in candles
            if candle.closed
        ]
        with self.database.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO market_candles(
                    symbol, timeframe, open_time, close_time,
                    open_text, high_text, low_text, close_text, volume_text, source_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, open_time) DO UPDATE SET
                    close_time = excluded.close_time,
                    open_text = excluded.open_text,
                    high_text = excluded.high_text,
                    low_text = excluded.low_text,
                    close_text = excluded.close_text,
                    volume_text = excluded.volume_text,
                    source_hash = excluded.source_hash
                """,
                rows,
            )
        return len(rows)

    def load_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list["Candle"]:
        from goldguard.domain.models import Candle

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM market_candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY open_time DESC
                LIMIT ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        return [
            Candle(
                symbol=str(row["symbol"]),
                timeframe=str(row["timeframe"]),
                open_time=datetime.fromisoformat(str(row["open_time"])),
                close_time=datetime.fromisoformat(str(row["close_time"])),
                open=Decimal(str(row["open_text"])),
                high=Decimal(str(row["high_text"])),
                low=Decimal(str(row["low_text"])),
                close=Decimal(str(row["close_text"])),
                volume=Decimal(str(row["volume_text"])),
                closed=True,
            )
            for row in reversed(rows)
        ]

    def latest_close_time(self, symbol: str, timeframe: str) -> datetime | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT MAX(close_time) AS newest FROM market_candles "
                "WHERE symbol = ? AND timeframe = ?",
                (symbol, timeframe),
            ).fetchone()
        if row is None or row["newest"] is None:
            return None
        return datetime.fromisoformat(str(row["newest"]))

    def record_quality_event(
        self,
        *,
        symbol: str,
        timeframe: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO data_quality_events(
                    id, symbol, timeframe, event_type, details_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    symbol,
                    timeframe,
                    event_type,
                    canonical_json(details),
                    utc_now_iso(),
                ),
            )


class AgentEventRepository:
    """Durable sink for audit-worthy agent events."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, event: AgentEvent) -> None:
        if not event.audit_worthy:
            return
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO agent_events "
                "(event_id, action, reason, reason_codes_json, payload_json, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.action,
                    event.reason,
                    canonical_json(event.reason_codes),
                    canonical_json(dict(event.payload)),
                    event.occurred_at.isoformat(),
                ),
            )

    def list_events(self, limit: int = 30) -> tuple[AgentEvent, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_events ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return tuple(
            AgentEvent(
                event_id=str(row["event_id"]),
                action=str(row["action"]),
                reason=str(row["reason"]),
                reason_codes=tuple(json.loads(row["reason_codes_json"])),
                payload=MappingProxyType(json.loads(row["payload_json"])),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                audit_worthy=True,
            )
            for row in rows
        )


class GenomeRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_genome(
        self,
        genome: StrategyGenome,
        origin: str = "baseline",
        status: str = "candidate",
    ) -> str:
        payload = genome.model_dump(mode="json")
        g_hash = genome_hash(genome)
        evidence = list(genome.evidence_refs)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO genomes(
                    genome_id, genome_hash, parent_id, origin, status,
                    hypothesis, payload_json, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(genome_id) DO UPDATE SET
                    genome_hash = excluded.genome_hash,
                    parent_id = excluded.parent_id,
                    origin = excluded.origin,
                    status = excluded.status,
                    hypothesis = excluded.hypothesis,
                    payload_json = excluded.payload_json,
                    evidence_json = excluded.evidence_json
                """,
                (
                    genome.genome_id,
                    g_hash,
                    genome.parent_id,
                    origin,
                    status,
                    genome.hypothesis,
                    canonical_json(payload),
                    canonical_json(evidence),
                    utc_now_iso(),
                ),
            )
        return genome.genome_id

    def get_genome(self, genome_id: str) -> StrategyGenome | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM genomes WHERE genome_id = ?",
                (genome_id,),
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload_json"])
        return StrategyGenome.model_validate(data)

    def get_genome_row(self, genome_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM genomes WHERE genome_id = ?",
                (genome_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_genome_status(self, genome_id: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM genomes WHERE genome_id = ?",
                (genome_id,),
            ).fetchone()
        return str(row["status"]) if row else None

    def update_status(self, genome_id: str, new_status: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE genomes SET status = ? WHERE genome_id = ?",
                (new_status, genome_id),
            )

    def get_active_genome(self) -> StrategyGenome | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM genomes WHERE status = 'active' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload_json"])
        return StrategyGenome.model_validate(data)

    def transition_genome_status(
        self,
        genome_id: str,
        new_status: str,
        promoted_by: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT status, origin FROM genomes WHERE genome_id = ?",
                (genome_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Genome {genome_id} not found")

            current_status = row["status"]

            # Validate transition rules
            if current_status == new_status:
                return

            if new_status == "active":
                # Candidate can become active directly ONLY if promoted_by='human'
                if current_status == "candidate" and promoted_by != "human":
                    msg = (
                        f"invalid status transition from {current_status} to {new_status} "
                        "without intermediate shadow status"
                    )
                    raise ValueError(msg)
                # If promoting to active, retire previous active genomes
                connection.execute(
                    "UPDATE genomes SET status = 'retired' "
                    "WHERE status = 'active' AND genome_id != ?",
                    (genome_id,),
                )
            elif new_status == "shadow":
                if current_status not in ("candidate", "holdout_passed"):
                    raise ValueError(
                        f"invalid status transition from {current_status} to {new_status}"
                    )
            elif new_status in ("quarantined", "retired", "archived"):
                pass

            connection.execute(
                "UPDATE genomes SET status = ? WHERE genome_id = ?",
                (new_status, genome_id),
            )

    def list_genomes(self, status: str | None = None) -> list[dict[str, Any]]:
        """Registry rows merged with the stored specification.

        The Studio editor dereferences ``evidence_refs``, ``regime``, ``guard``, ``entry``,
        and ``exit``; returning only the index columns crashed the tab.
        """
        with self.database.connect() as connection:
            query = (
                "SELECT genome_id, genome_hash, parent_id, origin, status, "
                "hypothesis, payload_json, created_at FROM genomes "
            )
            if status:
                rows = connection.execute(
                    query + "WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = connection.execute(query + "ORDER BY created_at DESC").fetchall()

        genomes: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            payload = json.loads(str(record.pop("payload_json")))
            payload.update(record)
            genomes.append(payload)
        return genomes


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record_evaluation(
        self,
        *,
        genome_id: str,
        partition: str,
        window: str,
        metrics: dict[str, Any],
        run_hash: str,
        evaluation_id: str | None = None,
    ) -> None:
        eval_id = evaluation_id or str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO evaluations(
                    evaluation_id, genome_id, partition, window,
                    metrics_json, run_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_id,
                    genome_id,
                    partition,
                    window,
                    canonical_json(metrics),
                    run_hash,
                    utc_now_iso(),
                ),
            )

    def get_evaluations_for_genome(self, genome_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evaluations WHERE genome_id = ? ORDER BY created_at DESC",
                (genome_id,),
            ).fetchall()
        return [dict(r) for r in rows]


class PromotionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record_promotion(
        self,
        *,
        promotion_id: str,
        genome_id: str,
        promoted_by: str,
        mode: str,
        gate_report: dict[str, Any],
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO promotions(
                    promotion_id, genome_id, promoted_by, mode,
                    gate_report_json, at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    promotion_id,
                    genome_id,
                    promoted_by,
                    mode,
                    canonical_json(gate_report),
                    utc_now_iso(),
                ),
            )

    def get_promotions_in_last_days(self, days: int = 7) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT count(*) FROM promotions WHERE at >= ?",
                (cutoff,),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_promotions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT promotion_id, genome_id, promoted_by, mode, gate_report_json, at "
                "FROM promotions ORDER BY at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        promotions: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["gate_report"] = json.loads(str(record.pop("gate_report_json")))
            promotions.append(record)
        return promotions

    # -- canary observation --------------------------------------------------------

    def open_canary(
        self,
        *,
        genome_id: str,
        promotion_id: str,
        baseline_genome_id: str,
        baseline_hash: str,
    ) -> None:
        """Record that ``genome_id`` is live under observation, and what to revert to."""
        now = utc_now_iso()
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT genome_id FROM promotion_canary WHERE stage = 'canary' LIMIT 1"
            ).fetchone()
            if existing is not None and str(existing["genome_id"]) != genome_id:
                raise ValueError("another canary is already open")
            connection.execute(
                """
                INSERT INTO promotion_canary(
                    genome_id, promotion_id, baseline_genome_id, baseline_hash,
                    stage, rollback_reason, circuit_breaker_tripped, opened_at, updated_at
                ) VALUES (?, ?, ?, ?, 'canary', NULL, 0, ?, ?)
                ON CONFLICT(genome_id) DO UPDATE SET
                    promotion_id = excluded.promotion_id,
                    baseline_genome_id = excluded.baseline_genome_id,
                    baseline_hash = excluded.baseline_hash,
                    stage = 'canary',
                    rollback_reason = NULL,
                    circuit_breaker_tripped = 0,
                    updated_at = excluded.updated_at
                """,
                (genome_id, promotion_id, baseline_genome_id, baseline_hash, now, now),
            )

    def activate_with_canary(
        self,
        *,
        genome_id: str,
        promotion_id: str,
        baseline_genome_id: str,
        baseline_hash: str,
        promoted_by: str,
        mode: str,
        gate_report: dict[str, Any],
    ) -> str:
        """Atomically activate a candidate, record its canary, and record promotion.

        The transaction rechecks the durable autonomy switch while holding the database
        write lock. A revocation that wins the race therefore leaves both genome status and
        canary state untouched, while a concurrent activation cannot create two open canaries.
        """
        now = utc_now_iso()
        cutoff = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        with self.database.transaction() as connection:
            autonomy = connection.execute(
                "SELECT full_autonomy, revoked_reason FROM autonomy_state WHERE singleton = 1"
            ).fetchone()
            if autonomy is not None and not bool(autonomy["full_autonomy"]):
                reason = autonomy["revoked_reason"] or "no reason recorded"
                raise ValueError(f"AUTONOMY_REVOKED: autonomy is revoked: {reason}")

            promotion_count = connection.execute(
                "SELECT COUNT(*) AS count FROM promotions WHERE at >= ?", (cutoff,)
            ).fetchone()
            if promotion_count is not None and int(promotion_count["count"]) >= 1:
                raise ValueError("PROMOTION_CHURN_HALT: promotion churn guard is active")

            candidate = connection.execute(
                "SELECT status FROM genomes WHERE genome_id = ?", (genome_id,)
            ).fetchone()
            if candidate is None:
                raise ValueError(f"genome {genome_id} not found")

            existing = connection.execute(
                "SELECT genome_id FROM promotion_canary WHERE stage = 'canary' LIMIT 1"
            ).fetchone()
            if existing is not None and str(existing["genome_id"]) != genome_id:
                raise ValueError("another canary is already open")

            connection.execute(
                "UPDATE genomes SET status = 'archived' "
                "WHERE status = 'active' AND genome_id != ?",
                (genome_id,),
            )
            connection.execute(
                """
                INSERT INTO promotion_canary(
                    genome_id, promotion_id, baseline_genome_id, baseline_hash,
                    stage, rollback_reason, circuit_breaker_tripped, opened_at, updated_at
                ) VALUES (?, ?, ?, ?, 'canary', NULL, 0, ?, ?)
                """,
                (genome_id, promotion_id, baseline_genome_id, baseline_hash, now, now),
            )
            connection.execute(
                "UPDATE genomes SET status = 'active' WHERE genome_id = ?", (genome_id,)
            )
            connection.execute(
                """
                INSERT INTO promotions(
                    promotion_id, genome_id, promoted_by, mode, gate_report_json, at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    promotion_id,
                    genome_id,
                    promoted_by,
                    mode,
                    canonical_json(gate_report),
                    now,
                ),
            )
        return promotion_id

    def get_canary(self, genome_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM promotion_canary WHERE genome_id = ?",
                (genome_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_open_canary(self) -> dict[str, Any] | None:
        """The candidate still under observation, if any. At most one can be open."""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM promotion_canary WHERE stage = 'canary' "
                "ORDER BY opened_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get_latest_canary(self) -> dict[str, Any] | None:
        """Return the newest canary record, including a settled or rolled-back one."""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM promotion_canary ORDER BY updated_at DESC, opened_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def close_canary(
        self,
        genome_id: str,
        *,
        stage: str,
        rollback_reason: str | None = None,
        circuit_breaker_tripped: bool = False,
    ) -> bool:
        """Close an open canary. Returns False when it was already closed, so a repeated
        rollback signal cannot revert the same candidate twice."""
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE promotion_canary
                SET stage = ?, rollback_reason = ?, circuit_breaker_tripped = ?, updated_at = ?
                WHERE genome_id = ? AND stage = 'canary'
                """,
                (
                    stage,
                    rollback_reason,
                    1 if circuit_breaker_tripped else 0,
                    utc_now_iso(),
                    genome_id,
                ),
            )
            return cursor.rowcount > 0


class AutonomyRepository:
    """The durable autonomy kill switch.

    Revoking autonomy blocks research mutation and automatic promotion. It is persisted
    because a switch an operator threw must not come back on after a restart.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def state(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT full_autonomy, revoked_reason, updated_at FROM autonomy_state "
                "WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return {"full_autonomy": True, "revoked_reason": None, "updated_at": None}
        return {
            "full_autonomy": bool(row["full_autonomy"]),
            "revoked_reason": row["revoked_reason"],
            "updated_at": row["updated_at"],
        }

    def is_full_autonomy(self) -> bool:
        return bool(self.state()["full_autonomy"])

    def revoke(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("revoking autonomy requires a reason")
        self._write(full_autonomy=False, reason=reason)

    def restore(self) -> None:
        self._write(full_autonomy=True, reason=None)

    def _write(self, *, full_autonomy: bool, reason: str | None) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO autonomy_state(singleton, full_autonomy, revoked_reason, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    full_autonomy = excluded.full_autonomy,
                    revoked_reason = excluded.revoked_reason,
                    updated_at = excluded.updated_at
                """,
                (1 if full_autonomy else 0, reason, utc_now_iso()),
            )


class QuotaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def consume_backtest(self, date_str: str, max_limit: int) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT backtests_used FROM research_quota WHERE date = ?",
                (date_str,),
            ).fetchone()
            used = int(row["backtests_used"]) if row else 0
            if used >= max_limit:
                return False
            connection.execute(
                """
                INSERT INTO research_quota(date, backtests_used, web_calls_used)
                VALUES (?, 1, 0)
                ON CONFLICT(date) DO UPDATE SET backtests_used = backtests_used + 1
                """,
                (date_str,),
            )
            return True

    def consume_web_call(self, date_str: str, max_limit: int) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT web_calls_used FROM research_quota WHERE date = ?",
                (date_str,),
            ).fetchone()
            used = int(row["web_calls_used"]) if row else 0
            if used >= max_limit:
                return False
            connection.execute(
                """
                INSERT INTO research_quota(date, backtests_used, web_calls_used)
                VALUES (?, 0, 1)
                ON CONFLICT(date) DO UPDATE SET web_calls_used = web_calls_used + 1
                """,
                (date_str,),
            )
            return True

    def get_usage(self, date_str: str) -> tuple[int, int]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT backtests_used, web_calls_used FROM research_quota WHERE date = ?",
                (date_str,),
            ).fetchone()
        if row is None:
            return (0, 0)
        return (int(row["backtests_used"]), int(row["web_calls_used"]))

    def record_research_event(
        self,
        *,
        event_id: str,
        tool: str,
        bytes_out: int,
        started_at: str,
        finished_at: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO research_events(event_id, tool, bytes_out, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, tool, bytes_out, started_at, finished_at),
            )


class ProviderRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_provider(
        self,
        *,
        name: str,
        kind: str,
        base_url: str,
        key_fingerprint: str,
        status: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO providers(name, kind, base_url, key_fingerprint, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    kind = excluded.kind,
                    base_url = excluded.base_url,
                    key_fingerprint = excluded.key_fingerprint,
                    status = excluded.status
                """,
                (name, kind, base_url, key_fingerprint, status, utc_now_iso()),
            )

    def set_route(
        self,
        role: str,
        provider: str,
        model: str,
        pinned: bool = True,
    ) -> int:
        route_id = str(uuid4())
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM model_routes WHERE role = ?",
                (role,),
            ).fetchone()
            next_version = (int(row[0]) if row else 0) + 1
            connection.execute(
                """
                INSERT INTO model_routes(id, role, provider, model, pinned, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    role,
                    provider,
                    model,
                    1 if pinned else 0,
                    next_version,
                    utc_now_iso(),
                ),
            )
        return next_version

    def list_providers(self) -> list[ProviderRow]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM providers ORDER BY name").fetchall()
        return [
            ProviderRow(
                name=str(row["name"]),
                kind=str(row["kind"]),
                base_url=str(row["base_url"]),
                key_fingerprint=str(row["key_fingerprint"]),
                status=str(row["status"]),
                last_probe_at=(None if row["last_probe_at"] is None else str(row["last_probe_at"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def record_probe(self, name: str, *, probed_at: str | None = None) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE providers SET last_probe_at = ? WHERE name = ?",
                (probed_at or utc_now_iso(), name),
            )

    def get_active_routes(self) -> dict[str, RouteRow]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM active_routes").fetchall()
        result: dict[str, RouteRow] = {}
        for r in rows:
            result[r["role"]] = RouteRow(
                id=str(r["id"]),
                role=str(r["role"]),
                provider=str(r["provider"]),
                model=str(r["model"]),
                pinned=bool(r["pinned"]),
                version=int(r["version"]),
                created_at=str(r["created_at"]),
            )
        return result


class ReflectionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record_reflection(
        self,
        *,
        reflection_id: str,
        trade_id: str,
        namespace: str,
        lesson_code: str,
        lesson: str,
        regime_tags: list[str],
        net_pnl: Decimal,
        fee_drag: Decimal,
        mae: Decimal,
        mfe: Decimal,
        exit_reason: str,
        payload: dict[str, Any],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        params = (
            reflection_id,
            trade_id,
            namespace,
            lesson_code,
            lesson,
            canonical_json(regime_tags),
            str(net_pnl),
            str(fee_drag),
            str(mae),
            str(mfe),
            exit_reason,
            canonical_json(payload),
            utc_now_iso(),
        )
        sql = """
                INSERT OR IGNORE INTO reflections(
                    id, trade_id, namespace, lesson_code, lesson,
                    regime_tags_json, net_pnl_text, fee_drag_text,
                    mae_text, mfe_text, exit_reason, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        if connection is not None:
            connection.execute(sql, params)
            return
        with self.database.transaction() as owned:
            owned.execute(sql, params)

    def enqueue_outbox(
        self,
        *,
        trade_id: str,
        payload: dict[str, Any],
        error: str,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        now = utc_now_iso()
        params = (
            f"outbox-{trade_id}",
            trade_id,
            canonical_json(payload),
            "pending",
            1,
            error[:500],
            now,
            now,
        )
        sql = """
            INSERT INTO learning_outbox(
                id, trade_id, payload_json, status, attempts, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                attempts = attempts + 1,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """
        if connection is not None:
            connection.execute(sql, params)
            return
        with self.database.transaction() as owned:
            owned.execute(sql, params)

    def mark_outbox(
        self, connection: sqlite3.Connection, trade_id: str, status: str
    ) -> None:
        connection.execute(
            """
            UPDATE learning_outbox
            SET status = ?, updated_at = ?
            WHERE trade_id = ?
            """,
            (status, utc_now_iso(), trade_id),
        )

    def has_pending_outbox(self) -> bool:
        try:
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM learning_outbox WHERE status = 'pending' LIMIT 1"
                ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False

    def get_by_trade_id(self, trade_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reflections WHERE trade_id = ? LIMIT 1",
                (trade_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "trade_id": str(row["trade_id"]),
            "namespace": str(row["namespace"]),
            "lesson_code": str(row["lesson_code"]),
            "lesson": str(row["lesson"]),
        }

    def list_reflections(
        self,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lessons with decoded, un-suffixed field names the memory tab can render directly."""
        with self.database.connect() as connection:
            query = "SELECT * FROM reflections "
            if namespace:
                rows = connection.execute(
                    query + "WHERE namespace = ? ORDER BY created_at DESC LIMIT ?",
                    (namespace, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    query + "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "trade_id": str(row["trade_id"]),
                "namespace": str(row["namespace"]),
                "lesson_code": str(row["lesson_code"]),
                "lesson": str(row["lesson"]),
                "regime_tags": json.loads(str(row["regime_tags_json"])),
                "net_pnl": str(row["net_pnl_text"]),
                "fee_drag": str(row["fee_drag_text"]),
                "mae": str(row["mae_text"]),
                "mfe": str(row["mfe_text"]),
                "exit_reason": str(row["exit_reason"]),
                "payload": json.loads(str(row["payload_json"])),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]
