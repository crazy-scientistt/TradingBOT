import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from goldguard.domain.profile import ActiveProfile, AutonomousProfile
from goldguard.storage.database import Database


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _canonical_data(profile: AutonomousProfile) -> dict[str, object]:
    payload: dict[str, object] = profile.model_dump(mode="json")
    payload["spot_pairs"] = sorted(set(profile.spot_pairs))
    payload["futures_pairs"] = sorted(set(profile.futures_pairs))
    payload["risk"] = {
        "max_capital_per_trade_rate": _decimal_text(profile.risk.max_capital_per_trade_rate),
        "max_futures_leverage": profile.risk.max_futures_leverage,
        "max_total_exposure_rate": _decimal_text(profile.risk.max_total_exposure_rate),
        "rolling_24h_loss_limit_rate": _decimal_text(profile.risk.rolling_24h_loss_limit_rate),
    }
    return payload


def _canonical_payload(profile: AutonomousProfile) -> str:
    return json.dumps(
        _canonical_data(profile),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _execution_payload(profile: AutonomousProfile) -> str:
    payload = _canonical_data(profile)
    payload.pop("notifications", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class ProfileRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def active(self) -> ActiveProfile | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT v.hash, v.payload, v.created_at, v.created_by, v.correlation_id "
                "FROM active_profile a "
                "JOIN profile_versions v ON a.hash = v.hash "
                "WHERE a.id = 1"
            ).fetchone()
            if row is None:
                return None
            return ActiveProfile(
                profile=AutonomousProfile.model_validate_json(row["payload"]),
                hash=row["hash"],
                created_at=row["created_at"],
                created_by=row["created_by"],
                correlation_id=row["correlation_id"],
            )

    def activate(
        self, profile: AutonomousProfile, actor: str, correlation_id: str
    ) -> ActiveProfile:
        payload = _canonical_payload(profile)
        profile_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()

        with self.database.transaction() as tx:
            previous_row = tx.execute(
                "SELECT v.hash, v.payload FROM active_profile a "
                "JOIN profile_versions v ON a.hash = v.hash "
                "WHERE a.id = 1"
            ).fetchone()
            previous_profile = (
                None
                if previous_row is None
                else AutonomousProfile.model_validate_json(previous_row["payload"])
            )
            execution_changed = previous_row is not None and (
                previous_profile is not None
                and _execution_payload(previous_profile) != _execution_payload(profile)
            )
            tx.execute(
                "INSERT OR IGNORE INTO profile_versions "
                "(hash, payload, created_at, created_by, correlation_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (profile_hash, payload, now, actor, correlation_id),
            )
            tx.execute(
                "INSERT INTO active_profile (id, hash) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET hash=excluded.hash",
                (profile_hash,),
            )

            tx.execute(
                "INSERT INTO security_events "
                "(event_type, actor, correlation_id, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "profile_activated",
                    actor,
                    correlation_id,
                    json.dumps(
                        {
                            "execution_affecting_change": execution_changed,
                            "new_profile": _canonical_data(profile),
                            "new_profile_hash": profile_hash,
                            "outcome": "success",
                            "previous_profile": (
                                None
                                if previous_profile is None
                                else _canonical_data(previous_profile)
                            ),
                            "previous_profile_hash": (
                                None if previous_row is None else str(previous_row["hash"])
                            ),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    now,
                ),
            )

            if execution_changed:
                tx.execute(
                    "UPDATE live_arming_state "
                    "SET status = 'armed_pending_reconciliation', profile_hash = ? "
                    "WHERE id = 1 AND status = 'armed_ready'",
                    (profile_hash,),
                )
            tx.execute(
                "UPDATE live_arming_state SET profile_hash = ? "
                "WHERE id = 1 AND status != 'disarmed'",
                (profile_hash,),
            )

            persisted = tx.execute(
                "SELECT hash, payload, created_at, created_by, correlation_id "
                "FROM profile_versions WHERE hash = ?",
                (profile_hash,),
            ).fetchone()

        if persisted is None:
            raise RuntimeError("Activated profile version was not persisted")

        return ActiveProfile(
            profile=AutonomousProfile.model_validate_json(persisted["payload"]),
            hash=str(persisted["hash"]),
            created_at=str(persisted["created_at"]),
            created_by=str(persisted["created_by"]),
            correlation_id=str(persisted["correlation_id"]),
        )
