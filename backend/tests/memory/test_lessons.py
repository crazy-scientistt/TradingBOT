from __future__ import annotations

from dataclasses import dataclass

from goldguard.memory.lessons import LessonEngine


@dataclass
class ReflectionMock:
    lesson_code: str
    lesson: str
    regime_tags: tuple[str, ...]


def test_lesson_engine_derivation() -> None:
    engine = LessonEngine()
    reflections = [
        ReflectionMock(
            lesson_code="TAKE_PROFIT_FAST",
            lesson="Take profit on high momentum",
            regime_tags=("trend",),
        )
    ]
    lessons = engine.derive(reflections)
    assert len(lessons) == 1
    assert lessons[0].lesson_code == "TAKE_PROFIT_FAST"

