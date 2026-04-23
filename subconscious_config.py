"""Centralized charter and rule configuration for Nova's subconscious layer."""

from __future__ import annotations


SUBCONSCIOUS_CHARTER = {
    "mission": {
        "mode": "observational_shaping",
        "primary_goals": [
            "observe_seam_behavior",
            "detect_repeated_weakness",
            "raise_advisory_pressure",
            "generate_diagnostic_and_training_outputs",
        ],
    },
    "allowed_actions": [
        "read_probe_results",
        "accumulate_crack_counts",
        "store_recent_pressure_records",
        "classify_robust_vs_script_specific",
        "emit_snapshot",
        "emit_backlog_summary",
        "emit_robust_weakness_summary",
        "emit_training_priorities",
        "request_re_evaluation_advisory_only",
    ],
    "forbidden_actions": [
        "own_turns",
        "route_turns",
        "force_behavior",
        "override_supervisor",
        "override_fulfillment",
        "create_controller_logic",
        "turn_diagnostics_into_commands",
    ],
    "signal_handling_rules": {
        "valid_routes": ["supervisor_owned", "fulfillment_applicable", "generic_fallback"],
        "pressure_signals": [
            "supervisor_overreach",
            "fulfillment_missed",
            "fallback_overuse",
            "route_unclear",
            "route_conflict",
            "route_fit_weak",
        ],
        "replan_immediate_signals": [
            "supervisor_overreach",
            "fulfillment_missed",
            "fallback_overuse",
            "route_conflict",
        ],
        "weak_crack_signals": ["route_unclear", "route_fit_weak"],
    },
    "crack_accumulation_rules": {
        "recent_pressure_window_cap": 12,
        "weak_crack_repeat_threshold": 3,
        "weak_crack_repeat_thresholds": {
            "route_unclear": 3,
            "route_fit_weak": 2,
        },
    },
    "re_evaluation_request_rules": {
        "advisory_only": True,
    },
    "training_backlog_generation_rules": {
        "immediate_priority_signals": [
            "supervisor_overreach",
            "fulfillment_missed",
            "fallback_overuse",
            "route_conflict",
        ],
        "signal_templates": {
            "supervisor_overreach": {
                "title": "Guard supervisor ownership drift",
                "suggested_test_name": "test_supervisor_guard_preserves_non_owned_route_conflict",
                "rationale": "Supervisor won a turn while fulfillment still looked viable.",
            },
            "fulfillment_missed": {
                "title": "Cover missed fulfillment entry",
                "suggested_test_name": "test_route_probe_surfaces_clear_fulfillment_without_fallback_loss",
                "rationale": "Fulfillment looked clearly applicable but Nova still fell through.",
            },
            "fallback_overuse": {
                "title": "Constrain fallback overuse",
                "suggested_test_name": "test_generic_fallback_does_not_hide_viable_specific_route",
                "rationale": "Generic fallback absorbed a turn that had a more specific viable route.",
            },
            "route_unclear": {
                "title": "Sharpen weak route comparisons",
                "suggested_test_name": "test_route_probe_marks_ambiguous_turns_without_overclaiming",
                "rationale": "Route comparison stayed unclear across recent pressure records.",
            },
            "route_conflict": {
                "title": "Exercise route conflict pressure",
                "suggested_test_name": "test_route_probe_records_conflict_when_supervisor_and_fulfillment_overlap",
                "rationale": "Supervisor and fulfillment both looked viable on the same turn.",
            },
            "route_fit_weak": {
                "title": "Strengthen route fit evidence",
                "suggested_test_name": "test_route_probe_exposes_weak_fit_without_forcing_routing",
                "rationale": "Route fit signals were too weak to support a confident comparison.",
            },
        },
    },
    "noise_suppression_rules": {
        "quiet_control_statuses": {
            "quiet": "quiet_control",
            "low_noise": "low_noise",
            "noise_present": "noise_present",
        },
        "training_priority_script_specific_min_robustness": 0.40,
        "training_priority_high_urgency_min_robustness": 0.85,
        "training_priority_low_urgency_min_robustness": 0.50,
    },
    "robustness_ranking_rules": {
        "consistency_threshold_ratio": 0.6,
        "consistency_threshold_min_hits": 2,
        "stability_factor_when_stable": 1.0,
        "robustness_score_ceiling": 0.97,
    },
}