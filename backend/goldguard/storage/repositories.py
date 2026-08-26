import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from goldguard.storage.database import Database


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class PaperSession:
    identifier: str
    initial_balance: Decimal
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
