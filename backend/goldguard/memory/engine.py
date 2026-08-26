import json
from typing import Any

from goldguard.memory.reflections import Reflection
from goldguard.storage.repositories import ReflectionRepository


class MemoryBank:
    """Dual-namespace persistent reflection and memory store for AI reasoning."""

    def __init__(self, reflection_repo: ReflectionRepository) -> None:
        self.repo = reflection_repo

    def record_reflection(self, reflection: Reflection) -> str:
        self.repo.record_reflection(
            reflection_id=reflection.identifier,
            trade_id=reflection.trade_id,
            namespace=reflection.namespace,
            lesson_code=reflection.lesson_code,
            lesson=reflection.lesson,
            regime_tags=list(reflection.regime_tags),
            net_pnl=reflection.net_pnl,
            fee_drag=reflection.fee_drag,
            mae=reflection.maximum_adverse_excursion,
            mfe=reflection.maximum_favorable_excursion,
            exit_reason=reflection.exit_reason,
            payload={"hypothesis": reflection.hypothesis},
        )
        return reflection.identifier

    def query_relevant_summaries(
        self,
        *,
        namespace: str = "forward",
        regime_tags: tuple[str, ...] = (),
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        rows = self.repo.list_reflections(namespace=namespace, limit=100)
        wanted = set(regime_tags)
        matches: list[dict[str, Any]] = []

        for row in rows:
            try:
                row_tags = set(json.loads(row["regime_tags_json"]))
            except Exception:
                row_tags = set()

            if not wanted or wanted.issubset(row_tags):
                matches.append(
                    {
                        "lesson_code": row["lesson_code"],
                        "lesson": row["lesson"],
                        "exit_reason": row["exit_reason"],
                        "net_pnl": row["net_pnl_text"],
                        "fee_drag": row["fee_drag_text"],
                        "regime_tags": list(row_tags),
                    }
                )

        return matches[: max(1, min(limit, 3))]
