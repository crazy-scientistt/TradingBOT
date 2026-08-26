from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MacroRiskWindow:
    event_name: str
    starts_at: datetime
    ends_at: datetime
    source_url: str

    def contains(self, moment: datetime) -> bool:
        return self.starts_at <= moment <= self.ends_at


def active_macro_windows(
    windows: tuple[MacroRiskWindow, ...],
    moment: datetime,
) -> tuple[MacroRiskWindow, ...]:
    return tuple(window for window in windows if window.contains(moment))
