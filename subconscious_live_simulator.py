"""Subconscious-local live pressure simulation for Nova.

This module simulates multi-turn usage pressure against Nova's current route
seam and feeds the same subconscious pressure, snapshot, and backlog helpers
already in place. It is observational only and does not influence routing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import nova_core
from conversation_manager import ConversationSession
from subconscious_config import SUBCONSCIOUS_CHARTER


_ROBUSTNESS_RULES = SUBCONSCIOUS_CHARTER["robustness_ranking_rules"]
_NOISE_SUPPRESSION_RULES = SUBCONSCIOUS_CHARTER["noise_suppression_rules"]


@dataclass(slots=True)
class LiveSimulationTurn:
    user_text: str
    chosen_route: str = "generic_fallback"
    pending_action: Optional[dict] = None
    conversation_state: Optional[dict] = None
    assistant_reply: str = ""


@dataclass(slots=True)
class LiveSimulationScenario:
    scenario_id: str
    target_seam: str
    turns: list[LiveSimulationTurn] = field(default_factory=list)
    variation_id: str = "baseline"


@dataclass(slots=True)
class LiveSimulationResult:
    scenario_id: str
    target_seam: str
    pressure_records: list[object] = field(default_factory=list)
    subconscious_snapshot: dict = field(default_factory=dict)
    training_backlog: Optional[dict] = None
    variation_id: str = "baseline"


@dataclass(slots=True)
class LiveSimulationFamily:
    family_id: str
    target_seam: str
    scenarios: list[LiveSimulationScenario] = field(default_factory=list)


@dataclass(slots=True)
class LiveSimulationFamilyResult:
    family_id: str
    target_seam: str
    variation_results: list[LiveSimulationResult] = field(default_factory=list)
    repeated_signals: list[dict] = field(default_factory=list)
    top_backlog_candidates: list[dict] = field(default_factory=list)
    noise_summary: dict = field(default_factory=dict)
    robust_signals: list[dict] = field(default_factory=list)
    script_specific_signals: list[dict] = field(default_factory=list)
    robust_backlog_candidates: list[dict] = field(default_factory=list)
    quiet_control_verdict: dict = field(default_factory=dict)


@dataclass(slots=True)
class TrainingPriorityItem:
    seam: str
    signal: str
    robustness: float
    suggested_test_name: str
    rationale: str
    urgency: str


def simulate_live_scenario(
    scenario: LiveSimulationScenario,
    *,
    session: Optional[ConversationSession] = None,
) -> LiveSimulationResult:
    """Run a single multi-turn scenario through Nova's current subconscious seam."""

    sim_session = session if isinstance(session, ConversationSession) else ConversationSession()
    recent_turns: list[tuple[str, str]] = []
    pressure_records: list[object] = []

    for turn in list(scenario.turns or []):
        pending_action = turn.pending_action if isinstance(turn.pending_action, dict) else getattr(sim_session, "pending_action", None)
        if isinstance(turn.pending_action, dict):
            sim_session.set_pending_action(turn.pending_action)
        if isinstance(turn.conversation_state, dict):
            sim_session.set_conversation_state(turn.conversation_state)

        probe = nova_core._probe_turn_routes(
            turn.user_text,
            sim_session,
            list(recent_turns),
            pending_action=pending_action,
        )
        state = nova_core._update_subconscious_state(
            sim_session,
            probe,
            chosen_route=turn.chosen_route,
        )
        if state is not None and list(getattr(state, "recent_pressure_records", []) or []):
            pressure_records.append(getattr(state, "recent_pressure_records")[-1])

        recent_turns.append(("user", str(turn.user_text or "").strip()))
        assistant_reply = str(turn.assistant_reply or "").strip()
        if assistant_reply:
            recent_turns.append(("assistant", assistant_reply))

    snapshot = nova_core._get_subconscious_snapshot(sim_session)
    backlog = nova_core._get_subconscious_training_backlog_summary(sim_session)
    return LiveSimulationResult(
        scenario_id=str(scenario.scenario_id or "scenario").strip() or "scenario",
        target_seam=str(scenario.target_seam or "route_seam").strip() or "route_seam",
        pressure_records=pressure_records,
        subconscious_snapshot=snapshot,
        training_backlog=backlog,
        variation_id=str(scenario.variation_id or "baseline").strip() or "baseline",
    )


def _classify_consistency(hit_count: int, total_variations: int) -> str:
    if total_variations <= 0 or hit_count <= 0:
        return "script_specific"
    threshold = max(
        int(_ROBUSTNESS_RULES["consistency_threshold_min_hits"]),
        math.ceil(total_variations * float(_ROBUSTNESS_RULES["consistency_threshold_ratio"])),
    )
    return "robust" if hit_count >= threshold else "script_specific"


def _score_ranked_weakness(
    *,
    hit_count: int,
    total_variations: int,
    noisy_variations: int,
) -> dict:
    if total_variations <= 0:
        return {
            "variation_hit_ratio": 0.0,
            "family_consistency": 0.0,
            "variation_survival_ratio": 0.0,
            "noise_resistance": 0.0,
            "robustness_score": 0.0,
        }

    variation_hit_ratio = hit_count / total_variations
    family_consistency = variation_hit_ratio
    variation_survival_ratio = min(1.0, hit_count / max(1, min(3, total_variations)))
    noise_resistance = max(0.0, 1.0 - (noisy_variations / total_variations))
    stability_factor = float(_ROBUSTNESS_RULES["stability_factor_when_stable"])
    raw_robustness = variation_hit_ratio * noise_resistance * stability_factor
    robustness_score = round(min(float(_ROBUSTNESS_RULES["robustness_score_ceiling"]), max(0.0, raw_robustness)), 4)
    return {
        "variation_hit_ratio": round(variation_hit_ratio, 4),
        "family_consistency": round(family_consistency, 4),
        "variation_survival_ratio": round(variation_survival_ratio, 4),
        "noise_resistance": round(noise_resistance, 4),
        "stability_factor": round(stability_factor, 4),
        "robustness_score": robustness_score,
    }


def _rank_family_weaknesses(
    *,
    repeated_signals: list[dict],
    top_backlog_candidates: list[dict],
    noise_summary: dict,
) -> dict:
    total_variations = max(0, int(noise_summary.get("variation_count", 0) or 0))
    noisy_variations = max(0, int(noise_summary.get("noisy_variations", 0) or 0))

    robust_signals = []
    script_specific_signals = []
    for item in list(repeated_signals or []):
        hit_count = max(0, int(item.get("hit_count", 0) or 0))
        ranked = {
            **dict(item),
            **_score_ranked_weakness(
                hit_count=hit_count,
                total_variations=total_variations,
                noisy_variations=noisy_variations,
            ),
        }
        if str(item.get("classification") or "") == "robust":
            robust_signals.append(ranked)
        else:
            script_specific_signals.append(ranked)

    robust_backlog_candidates = []
    for item in list(top_backlog_candidates or []):
        if str(item.get("classification") or "") != "robust":
            continue
        hit_count = max(0, int(item.get("hit_count", 0) or 0))
        robust_backlog_candidates.append(
            {
                **dict(item),
                **_score_ranked_weakness(
                    hit_count=hit_count,
                    total_variations=total_variations,
                    noisy_variations=noisy_variations,
                ),
            }
        )

    robust_signals.sort(key=lambda item: (-float(item.get("robustness_score", 0.0) or 0.0), str(item.get("signal") or "")))
    script_specific_signals.sort(key=lambda item: (-float(item.get("robustness_score", 0.0) or 0.0), str(item.get("signal") or "")))
    robust_backlog_candidates.sort(
        key=lambda item: (
            -float(item.get("robustness_score", 0.0) or 0.0),
            str(item.get("signal") or ""),
            str(item.get("suggested_test_name") or ""),
        )
    )

    quiet_control = bool(noise_summary.get("quiet_control"))
    quiet_statuses = _NOISE_SUPPRESSION_RULES["quiet_control_statuses"]
    quiet_control_verdict = {
        "quiet_control": quiet_control,
        "status": str(quiet_statuses["quiet"] if quiet_control else (quiet_statuses["low_noise"] if noisy_variations == 0 else quiet_statuses["noise_present"])),
        "reason": (
            "All variations stayed quiet, so this family acts as a control."
            if quiet_control
            else (
                "Variations stayed readable without noisy-only outcomes."
                if noisy_variations == 0
                else "Some variations produced noise without useful cracks."
            )
        ),
    }

    return {
        "robust_signals": robust_signals,
        "script_specific_signals": script_specific_signals,
        "robust_backlog_candidates": robust_backlog_candidates,
        "quiet_control_verdict": quiet_control_verdict,
    }


def build_training_priorities(family_result: LiveSimulationFamilyResult | dict) -> list[TrainingPriorityItem]:
    """Build read-only training priorities from an existing family ranking result."""

    result_payload = family_result if isinstance(family_result, dict) else {
        "target_seam": getattr(family_result, "target_seam", ""),
        "robust_signals": list(getattr(family_result, "robust_signals", []) or []),
        "script_specific_signals": list(getattr(family_result, "script_specific_signals", []) or []),
        "robust_backlog_candidates": list(getattr(family_result, "robust_backlog_candidates", []) or []),
        "quiet_control_verdict": dict(getattr(family_result, "quiet_control_verdict", {}) or {}),
    }

    quiet_control_verdict = result_payload.get("quiet_control_verdict") if isinstance(result_payload, dict) else {}
    if isinstance(quiet_control_verdict, dict) and bool(quiet_control_verdict.get("quiet_control")):
        return []

    seam = str((result_payload.get("target_seam") if isinstance(result_payload, dict) else "") or "route_seam").strip() or "route_seam"
    priorities: list[TrainingPriorityItem] = []

    robust_backlog = result_payload.get("robust_backlog_candidates") if isinstance(result_payload, dict) else []
    for item in list(robust_backlog or []):
        payload = dict(item) if isinstance(item, dict) else {}
        signal = str(payload.get("signal") or "").strip()
        suggested_test_name = str(payload.get("suggested_test_name") or "").strip()
        if not signal or not suggested_test_name:
            continue
        robustness = round(float(payload.get("robustness_score", 0.0) or 0.0), 4)
        rationale = str(payload.get("rationale") or "").strip() or f"Robust family pressure kept surfacing {signal}."
        priorities.append(
            TrainingPriorityItem(
                seam=seam,
                signal=signal,
                robustness=robustness,
                suggested_test_name=suggested_test_name,
                rationale=rationale,
                urgency="high" if robustness >= float(_NOISE_SUPPRESSION_RULES["training_priority_high_urgency_min_robustness"]) else "medium",
            )
        )

    script_specific = result_payload.get("script_specific_signals") if isinstance(result_payload, dict) else []
    seen_script_specific: set[str] = set()
    for item in list(script_specific or []):
        payload = dict(item) if isinstance(item, dict) else {}
        signal = str(payload.get("signal") or "").strip()
        if not signal or signal in seen_script_specific:
            continue
        seen_script_specific.add(signal)
        robustness = round(float(payload.get("robustness_score", 0.0) or 0.0), 4)
        if robustness < float(_NOISE_SUPPRESSION_RULES["training_priority_script_specific_min_robustness"]):
            continue
        priorities.append(
            TrainingPriorityItem(
                seam=seam,
                signal=signal,
                robustness=robustness,
                suggested_test_name=str(payload.get("suggested_test_name") or f"defer_{signal}").strip(),
                rationale=str(payload.get("rationale") or "").strip() or f"{signal} appeared, but only in narrow or script-specific family pressure.",
                urgency="deferred" if robustness < float(_NOISE_SUPPRESSION_RULES["training_priority_low_urgency_min_robustness"]) else "low",
            )
        )

    priorities.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2, "deferred": 3}.get(item.urgency, 4),
            -float(item.robustness),
            item.signal,
        )
    )
    return priorities


def simulate_live_family(
    family: LiveSimulationFamily,
) -> LiveSimulationFamilyResult:
    """Run a family of small scenario variations against one current seam target."""

    variation_results = [simulate_live_scenario(scenario) for scenario in list(family.scenarios or [])]
    total_variations = len(variation_results)
    signal_hits: dict[str, int] = {}
    backlog_hits: dict[tuple[str, str], int] = {}
    quiet_variations = 0
    noisy_variations = 0
    useful_variations = 0

    for result in variation_results:
        snapshot = result.subconscious_snapshot if isinstance(result.subconscious_snapshot, dict) else {}
        active_signals = [str(item).strip() for item in list(snapshot.get("active_recent_signals") or []) if str(item).strip()]
        backlog = result.training_backlog if isinstance(result.training_backlog, dict) else {}
        candidate_tests = list(backlog.get("candidate_tests") or [])

        if not active_signals and not candidate_tests:
            quiet_variations += 1
        elif active_signals and candidate_tests:
            useful_variations += 1
        else:
            noisy_variations += 1

        for signal in list(dict.fromkeys(active_signals)):
            signal_hits[signal] = int(signal_hits.get(signal, 0)) + 1

        seen_backlog_keys: set[tuple[str, str]] = set()
        for item in candidate_tests:
            signal = str(item.get("signal") or "").strip()
            suggested_test_name = str(item.get("suggested_test_name") or "").strip()
            key = (signal, suggested_test_name)
            if not signal or not suggested_test_name or key in seen_backlog_keys:
                continue
            seen_backlog_keys.add(key)
            backlog_hits[key] = int(backlog_hits.get(key, 0)) + 1

    repeated_signals = [
        {
            "signal": signal,
            "hit_count": hit_count,
            "variation_count": total_variations,
            "consistency_ratio": round(hit_count / total_variations, 4) if total_variations else 0.0,
            "classification": _classify_consistency(hit_count, total_variations),
        }
        for signal, hit_count in sorted(signal_hits.items(), key=lambda item: (-item[1], item[0]))
    ]
    top_backlog_candidates = [
        {
            "signal": signal,
            "suggested_test_name": suggested_test_name,
            "hit_count": hit_count,
            "variation_count": total_variations,
            "consistency_ratio": round(hit_count / total_variations, 4) if total_variations else 0.0,
            "classification": _classify_consistency(hit_count, total_variations),
        }
        for (signal, suggested_test_name), hit_count in sorted(backlog_hits.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]
    noise_summary = {
        "quiet_variations": quiet_variations,
        "noisy_variations": noisy_variations,
        "useful_variations": useful_variations,
        "variation_count": total_variations,
        "quiet_control": quiet_variations == total_variations and noisy_variations == 0 and useful_variations == 0,
    }
    ranked_summary = _rank_family_weaknesses(
        repeated_signals=repeated_signals,
        top_backlog_candidates=top_backlog_candidates,
        noise_summary=noise_summary,
    )

    return LiveSimulationFamilyResult(
        family_id=str(family.family_id or "family").strip() or "family",
        target_seam=str(family.target_seam or "route_seam").strip() or "route_seam",
        variation_results=variation_results,
        repeated_signals=repeated_signals,
        top_backlog_candidates=top_backlog_candidates,
        noise_summary=noise_summary,
        robust_signals=list(ranked_summary.get("robust_signals") or []),
        script_specific_signals=list(ranked_summary.get("script_specific_signals") or []),
        robust_backlog_candidates=list(ranked_summary.get("robust_backlog_candidates") or []),
        quiet_control_verdict=dict(ranked_summary.get("quiet_control_verdict") or {}),
    )


def simulate_live_use(
    scenarios: list[LiveSimulationScenario],
) -> list[LiveSimulationResult]:
    """Run several seam-local pressure scenarios independently."""

    results: list[LiveSimulationResult] = []
    for scenario in list(scenarios or []):
        results.append(simulate_live_scenario(scenario))
    return results


def simulate_live_families(
    families: list[LiveSimulationFamily],
) -> list[LiveSimulationFamilyResult]:
    """Run several seam-local scenario families and aggregate variation consistency."""

    return [simulate_live_family(family) for family in list(families or [])]


def build_default_live_scenarios() -> list[LiveSimulationScenario]:
    """Provide minimal scenarios targeting current subconscious route seams."""

    return [
        LiveSimulationScenario(
            scenario_id="supervisor-boundary",
            target_seam="supervisor_ownership_boundary",
            turns=[
                LiveSimulationTurn(
                    user_text="go ahead",
                    chosen_route="supervisor_owned",
                    pending_action={
                        "kind": "weather_lookup",
                        "status": "awaiting_location",
                        "saved_location_available": True,
                        "preferred_tool": "weather_current_location",
                    },
                    assistant_reply="Using the saved location for the weather lookup.",
                ),
            ],
        ),
        LiveSimulationScenario(
            scenario_id="fulfillment-fallthrough",
            target_seam="fulfillment_bridge_entry_fallthrough",
            turns=[
                LiveSimulationTurn(
                    user_text="Show me workable options without collapsing too early.",
                    chosen_route="generic_fallback",
                ),
            ],
        ),
        LiveSimulationScenario(
            scenario_id="repeated-weak-pressure",
            target_seam="subconscious_pressure_backlog_generation",
            turns=[
                LiveSimulationTurn(user_text="how are you doing today ?", chosen_route="generic_fallback"),
                LiveSimulationTurn(user_text="what now", chosen_route="generic_fallback"),
            ],
        ),
    ]


def build_default_live_scenario_families() -> list[LiveSimulationFamily]:
    """Provide small variation families for the current subconscious route seam."""

    return [
        LiveSimulationFamily(
            family_id="supervisor-boundary-family",
            target_seam="supervisor_ownership_boundary",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="supervisor-boundary",
                    variation_id="direct_go_ahead",
                    target_seam="supervisor_ownership_boundary",
                    turns=[
                        LiveSimulationTurn(
                            user_text="go ahead",
                            chosen_route="supervisor_owned",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="supervisor-boundary",
                    variation_id="polite_confirmation",
                    target_seam="supervisor_ownership_boundary",
                    turns=[
                        LiveSimulationTurn(
                            user_text="yes please use the saved location",
                            chosen_route="supervisor_owned",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="supervisor-boundary",
                    variation_id="short_okay",
                    target_seam="supervisor_ownership_boundary",
                    turns=[
                        LiveSimulationTurn(
                            user_text="okay do that",
                            chosen_route="supervisor_owned",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="supervisor-boundary",
                    variation_id="clarification_then_confirm",
                    target_seam="supervisor_ownership_boundary",
                    turns=[
                        LiveSimulationTurn(
                            user_text="sure use that one",
                            chosen_route="supervisor_owned",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                            assistant_reply="Using the saved location for the weather lookup.",
                        )
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="fulfillment-fallthrough-family",
            target_seam="fulfillment_bridge_entry_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="fulfillment-fallthrough",
                    variation_id="direct_compare_request",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="Show me workable options without collapsing too early.",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="fulfillment-fallthrough",
                    variation_id="polite_compare_request",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="Can you compare a few viable ways forward before picking one for me ?",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="fulfillment-fallthrough",
                    variation_id="direct_options_language",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="I need options here. Do not collapse to one answer yet.",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="fulfillment-fallthrough",
                    variation_id="clarified_second_turn",
                    target_seam="fulfillment_bridge_entry_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="I need help deciding.",
                            chosen_route="generic_fallback",
                            assistant_reply="Tell me whether you want a comparison of options or a single answer.",
                        ),
                        LiveSimulationTurn(
                            user_text="Show me the possible paths first so I can compare tradeoffs.",
                            chosen_route="generic_fallback",
                        ),
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="repeated-weak-pressure-family",
            target_seam="subconscious_pressure_backlog_generation",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="repeated-weak-pressure",
                    variation_id="plain_followup",
                    target_seam="subconscious_pressure_backlog_generation",
                    turns=[
                        LiveSimulationTurn(user_text="how are you doing today ?", chosen_route="generic_fallback"),
                        LiveSimulationTurn(user_text="what now", chosen_route="generic_fallback"),
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="repeated-weak-pressure",
                    variation_id="casual_checkin",
                    target_seam="subconscious_pressure_backlog_generation",
                    turns=[
                        LiveSimulationTurn(user_text="how is your day going right now ?", chosen_route="generic_fallback"),
                        LiveSimulationTurn(user_text="where does that leave us ?", chosen_route="generic_fallback"),
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="repeated-weak-pressure",
                    variation_id="ambiguous_clarification",
                    target_seam="subconscious_pressure_backlog_generation",
                    turns=[
                        LiveSimulationTurn(
                            user_text="can you help me a little here ?",
                            chosen_route="generic_fallback",
                            assistant_reply="What kind of help do you want?",
                        ),
                        LiveSimulationTurn(user_text="what do you think then ?", chosen_route="generic_fallback"),
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="repeated-weak-pressure",
                    variation_id="soft_smalltalk_then_ambiguity",
                    target_seam="subconscious_pressure_backlog_generation",
                    turns=[
                        LiveSimulationTurn(user_text="are you doing alright today nova ?", chosen_route="generic_fallback"),
                        LiveSimulationTurn(user_text="okay so what next ?", chosen_route="generic_fallback"),
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="memory-capture-fallthrough-family",
            target_seam="memory_capture_route_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="memory-capture-fallthrough",
                    variation_id="favorite_color_fact",
                    target_seam="memory_capture_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="Remember this: my favorite color is teal. Don't forget.",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="memory-capture-fallthrough",
                    variation_id="location_fact",
                    target_seam="memory_capture_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="remember this Brownsville is my location",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="memory-capture-fallthrough",
                    variation_id="preference_fact",
                    target_seam="memory_capture_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="remember this I prefer concise summaries with the key facts first",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="memory-capture-fallthrough",
                    variation_id="identity_fact",
                    target_seam="memory_capture_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="remember this my integration marker is memory-route-alpha",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="weather-continuation-fallthrough-family",
            target_seam="weather_continuation_route_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="weather-continuation-fallthrough",
                    variation_id="bare_go_ahead",
                    target_seam="weather_continuation_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="go ahead",
                            chosen_route="generic_fallback",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="weather-continuation-fallthrough",
                    variation_id="polite_saved_location",
                    target_seam="weather_continuation_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="yes please use the saved location",
                            chosen_route="generic_fallback",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="weather-continuation-fallthrough",
                    variation_id="shared_location_followup",
                    target_seam="weather_continuation_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="yes get the weather for our location",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="weather-continuation-fallthrough",
                    variation_id="short_okay_do_that",
                    target_seam="weather_continuation_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="okay do that",
                            chosen_route="generic_fallback",
                            pending_action={
                                "kind": "weather_lookup",
                                "status": "awaiting_location",
                                "saved_location_available": True,
                                "preferred_tool": "weather_current_location",
                            },
                        )
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="retrieval-followup-fallthrough-family",
            target_seam="retrieval_followup_route_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="retrieval-followup-fallthrough",
                    variation_id="selected_result_followup",
                    target_seam="retrieval_followup_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="tell me about the first one",
                            chosen_route="generic_fallback",
                            conversation_state={
                                "kind": "retrieval",
                                "subject": "web_research",
                                "query": "PEIMS attendance",
                                "result_count": 2,
                                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="retrieval-followup-fallthrough",
                    variation_id="meta_question_followup",
                    target_seam="retrieval_followup_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="what did you find",
                            chosen_route="generic_fallback",
                            conversation_state={
                                "kind": "retrieval",
                                "subject": "web_research",
                                "query": "PEIMS attendance",
                                "result_count": 2,
                                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
                            },
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="retrieval-followup-fallthrough",
                    variation_id="keyword_continue",
                    target_seam="retrieval_followup_route_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="web continue",
                            chosen_route="generic_fallback",
                            conversation_state={
                                "kind": "retrieval",
                                "subject": "web_research",
                                "query": "PEIMS attendance",
                                "result_count": 2,
                                "urls": ["https://tea.texas.gov/a", "https://tea.texas.gov/b"],
                            },
                            assistant_reply="I found more sources. Type web continue to keep going.",
                        )
                    ],
                ),
            ],
        ),
        LiveSimulationFamily(
            family_id="patch-routing-fallthrough-family",
            target_seam="patch_routing_fallthrough",
            scenarios=[
                LiveSimulationScenario(
                    scenario_id="patch-routing-fallthrough",
                    variation_id="patch_apply_direct_tool",
                    target_seam="patch_routing_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="please patch apply updates.zip",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="patch-routing-fallthrough",
                    variation_id="patch_preview_command",
                    target_seam="patch_routing_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="patch preview teach.zip",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
                LiveSimulationScenario(
                    scenario_id="patch-routing-fallthrough",
                    variation_id="patch_rollback_command",
                    target_seam="patch_routing_fallthrough",
                    turns=[
                        LiveSimulationTurn(
                            user_text="patch rollback",
                            chosen_route="generic_fallback",
                        )
                    ],
                ),
            ],
        ),
    ]