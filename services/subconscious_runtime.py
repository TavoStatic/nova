"""Configured runtime boundary for Nova's subconscious state helpers."""

from __future__ import annotations

from typing import Optional

from subconscious_config import SUBCONSCIOUS_CHARTER

from services.session_state import SessionStateService, SubconsciousState


class ConfiguredSubconsciousService:
    """Bind subconscious charter/config once and expose runtime-safe helpers."""

    def __init__(self, subconscious_charter: dict):
        self._charter = subconscious_charter if isinstance(subconscious_charter, dict) else {}
        crack_rules = self._charter.get("crack_accumulation_rules") or {}
        self._max_recent_pressure_records = max(1, int(crack_rules.get("recent_pressure_window_cap", 12) or 12))

    def get_snapshot(self, session: object) -> dict:
        return SessionStateService.get_subconscious_snapshot(
            session,
            self._charter,
            self._max_recent_pressure_records,
        )

    def update_state(
        self,
        session: object,
        probe_result: dict,
        *,
        chosen_route: Optional[str] = None,
    ) -> Optional[SubconsciousState]:
        return SessionStateService.update_subconscious_state(
            session,
            probe_result,
            self._charter,
            self._max_recent_pressure_records,
            chosen_route=chosen_route,
        )

    def pressure_config(self) -> dict:
        return SessionStateService.get_subconscious_pressure_config(
            self._charter,
            self._max_recent_pressure_records,
        )


SUBCONSCIOUS_SERVICE = ConfiguredSubconsciousService(SUBCONSCIOUS_CHARTER)