# Subconscious Batch Summary

Generated: 2026-09-05 08:39:57
Label: phase1_auto

## Totals

- Families: 7
- Variations: 26
- Useful variations: 5
- Quiet variations: 10
- Noisy variations: 11
- Robust signals: 8
- Script-specific signals: 2
- Training priorities: 2

## supervisor-boundary-family

Target seam: supervisor_ownership_boundary
Variations: 4
Quiet control: True

No robust cracks surfaced in this family.

## fulfillment-fallthrough-family

Target seam: fulfillment_bridge_entry_fallthrough
Variations: 4
Quiet control: False

Robust signals:
- route_fit_weak: score=0.25 hit_ratio=1.0
- route_unclear: score=0.25 hit_ratio=1.0

## repeated-weak-pressure-family

Target seam: subconscious_pressure_backlog_generation
Variations: 4
Quiet control: False

Robust signals:
- route_fit_weak: score=0.97 hit_ratio=1.0
- route_unclear: score=0.97 hit_ratio=1.0

Training priorities:
- route_fit_weak -> test_route_probe_exposes_weak_fit_without_forcing_routing [high]
- route_unclear -> test_route_probe_marks_ambiguous_turns_without_overclaiming [high]

## weather-continuation-fallthrough-family

Target seam: weather_continuation_route_fallthrough
Variations: 4
Quiet control: False

No robust cracks surfaced in this family.

## retrieval-followup-fallthrough-family

Target seam: retrieval_followup_route_fallthrough
Variations: 3
Quiet control: True

No robust cracks surfaced in this family.

## patch-routing-fallthrough-family

Target seam: patch_routing_fallthrough
Variations: 3
Quiet control: False

Robust signals:
- route_fit_weak: score=0.0 hit_ratio=1.0
- route_unclear: score=0.0 hit_ratio=1.0

## session-fact-recall-fallthrough-family

Target seam: session_fact_recall_route_fallthrough
Variations: 4
Quiet control: False

Robust signals:
- route_fit_weak: score=0.0 hit_ratio=1.0
- route_unclear: score=0.0 hit_ratio=1.0
