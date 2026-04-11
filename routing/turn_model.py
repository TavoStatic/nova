from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TurnUnderstanding:
    raw_text: str
    text: str
    low: str
    url: str = ""
    mentions_location: bool = False
    mentions_shared_location: bool = False
    mentions_weather: bool = False


@dataclass(frozen=True)
class RouteDecision:
    kind: str
    tool: str = ""
    args: Tuple[str, ...] = ()
    message: str = ""
