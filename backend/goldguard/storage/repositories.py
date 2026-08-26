import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from goldguard.storage.database import Database
from goldguard.observability.events import AgentEvent
from goldguard.strategy.genome import StrategyGenome, genome_hash


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
        with self.database.connect() as connection:
            query = (
                "SELECT genome_id, genome_hash, parent_id, origin, status, "
                "hypothesis, created_at FROM genomes "
            )
            if status:
                rows = connection.execute(
                    query + "WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = connection.execute(query + "ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


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
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO reflections(
                    id, trade_id, namespace, lesson_code, lesson,
                    regime_tags_json, net_pnl_text, fee_drag_text,
                    mae_text, mfe_text, exit_reason, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                ),
            )

    def list_reflections(
        self,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
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
        return [dict(r) for r in rows]
