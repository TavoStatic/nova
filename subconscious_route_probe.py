"""Seam-local route pressure analysis for Nova.

This module does not route turns or claim ownership. It only analyzes the
existing route seam probe output and emits compact pressure signals that can be
used later for training and regression testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from subconscious_config import SUBCONSCIOUS_CHARTER


VALID_ROUTES = set(SUBCONSCIOUS_CHARTER["signal_handling_rules"]["valid_routes"])


def _route_payload(probe_result: Mapping[str, Any], route_name: str) -> dict[str, Any]:
    routes = probe_result.get("routes") if isinstance(probe_result.get("routes"), Mapping) else {}
    payload = routes.get(route_name) if isinstance(routes, Mapping) else None
    return dict(payload) if isinstance(payload, Mapping) else {}


def _route_viable(probe_result: Mapping[str, Any], route_name: str) -> bool:
    return bool(_route_payload(probe_result, route_name).get("viable"))


def _route_notes(probe_result: Mapping[str, Any], route_name: str) -> list[str]:
    payload = _route_payload(probe_result, route_name)
    return [str(note).strip() for note in list(payload.get("fit_notes") or []) if str(note).strip()]


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


@dataclass(slots=True)
class RoutePressureRecord:
    user_text: str
    chosen_route: str | None
    comparison_strength: str
    supervisor_viable: bool
    fulfillment_viable: bool
    fallback_viable: bool
    signals: list[str] = field(default_factory=list)
    weak_spots: list[str] = field(default_factory=list)
    route_notes: dict[str, list[str]] = field(default_factory=dict)


def analyze_route_pressure(
    probe_result: Mapping[str, Any],
    *,
    chosen_route: str | None = None,
) -> RoutePressureRecord:
    """Translate an existing route comparison probe into compact pressure signals.

    The input is expected to come from Nova's existing `_probe_turn_routes(...)`
    helper. This function does not select a route or affect ownership.
    """

    normalized_chosen_route = str(chosen_route or "").strip() or None
    if normalized_chosen_route not in VALID_ROUTES:
        normalized_chosen_route = None

    comparison_strength = str(probe_result.get("comparison_strength") or "weak").strip().lower() or "weak"
    supervisor_viable = _route_viable(probe_result, "supervisor_owned")
    fulfillment_viable = _route_viable(probe_result, "fulfillment_applicable")
    fallback_viable = _route_viable(probe_result, "generic_fallback")

    record = RoutePressureRecord(
        user_text=str(probe_result.get("user_text") or "").strip(),
        chosen_route=normalized_chosen_route,
        comparison_strength=comparison_strength,
        supervisor_viable=supervisor_viable,
        fulfillment_viable=fulfillment_viable,
        fallback_viable=fallback_viable,
        route_notes={
            route_name: _route_notes(probe_result, route_name)
            for route_name in sorted(VALID_ROUTES)
        },
    )

    if supervisor_viable and fulfillment_viable:
        _append_unique(record.signals, ["route_conflict"])
        _append_unique(record.weak_spots, ["supervisor and fulfillment both looked viable"])

    if comparison_strength != "clear":
        _append_unique(record.signals, ["route_unclear"])
        _append_unique(record.weak_spots, [f"route comparison strength is {comparison_strength}"])

    if comparison_strength == "weak":
        _append_unique(record.signals, ["route_fit_weak"])
        _append_unique(record.weak_spots, ["available route signals were weak"])

    if normalized_chosen_route == "supervisor_owned" and fulfillment_viable:
        _append_unique(record.signals, ["supervisor_overreach"])
        _append_unique(record.weak_spots, ["supervisor was chosen while fulfillment remained viable"])

    if normalized_chosen_route == "generic_fallback" and (supervisor_viable or fulfillment_viable):
        _append_unique(record.signals, ["fallback_overuse"])
        _append_unique(record.weak_spots, ["fallback was chosen even though a more specific route was viable"])

    if normalized_chosen_route in {None, "generic_fallback"} and fulfillment_viable and not supervisor_viable and comparison_strength == "clear":
        _append_unique(record.signals, ["fulfillment_missed"])
        _append_unique(record.weak_spots, ["fulfillment looked clearly applicable but was not chosen"])

    return record