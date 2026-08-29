from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Lesson:
    lesson_id: str
    lesson_code: str
    summary: str
    regime_tags: tuple[str, ...]
    mode: str
    product: str
    symbol: str


class LessonEngine:
    def derive(self, reflections: list[Any]) -> tuple[Lesson, ...]:
        lessons: list[Lesson] = []
        for index, ref in enumerate(reflections):
            code = getattr(ref, "lesson_code", "GENERAL")
            summary = getattr(ref, "lesson", "Maintain risk adherence")
            tags = tuple(getattr(ref, "regime_tags", ("trend",)))
            lessons.append(
                Lesson(
                    lesson_id=f"les-{index+1}",
                    lesson_code=code,
                    summary=summary,
                    regime_tags=tags,
                    mode="paper",
                    product="spot",
                    symbol="PAXGUSDT",
                )
            )
        return tuple(lessons)

