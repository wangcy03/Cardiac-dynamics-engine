"""Controller-facing contracts. No hidden physiology or future reference events."""
from dataclasses import dataclass
from typing import Literal, Protocol

Action = Literal["INFLATE", "DEFLATE", "CANCEL_PENDING"]


@dataclass(frozen=True)
class Sample:
    channel_id: str
    units: str
    sequence_id: int
    value: float
    t_available_us: int
    source_time_us: int | None
    source_clock_id: str | None
    observable_quality: str = "OK"


@dataclass(frozen=True)
class Command:
    command_id: str
    action: Action
    t_issued_us: int
    t_execute_us: int | None = None
    cancels_command_id: str | None = None


@dataclass(frozen=True)
class CommandStatus:
    command_id: str
    status: str
    at_us: int
    reason: str = ""


class Controller(Protocol):
    def on_samples(self, samples: list[Sample], now_us: int) -> list[Command]: ...
