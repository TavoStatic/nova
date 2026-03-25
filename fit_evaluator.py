"""Fit evaluation seams for Nova's shared-state architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, cast

from fulfillment_contracts import FitAssessment, FitFrame, FrameScore, FulfillmentModel, Intent


FRAME_NAMES = (
    "explicit_constraint_fit",
    "achievement_goal_fit",
    "friction",
    "timing",
    "risk",
    "usefulness",
)


def _tokenize(parts: list[str]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for raw in (part or "").lower().replace("-", " ").replace("_", " ").split():
            cleaned = "".join(ch for ch in raw if ch.isalnum())
            if cleaned:
                tokens.add(cleaned)
    return tokens


def _model_terms(model: FulfillmentModel) -> set[str]:
    return _tokenize(
        [
            model.label,
            model.description,
            model.path_shape,
            *model.differentiators,
            *model.assumptions,
            *model.prerequisites,
            *model.strengths,
            *model.expected_friction,
            *model.risks,
            *model.information_needs,
        ]
    )


def _intent_terms(intent: Intent) -> set[str]:
    return _tokenize(
        [
            intent.achievement_goal,
            *intent.success_criteria,
            *intent.constraints,
            *intent.friction_factors,
            *intent.preferences,
        ]
    )


def _overlap_score(left: set[str], right: set[str]) -> float:
    if not left:
        return 1.0
    if not right:
        return 0.0
    return len(left & right) / float(len(left))


def _frame_overrides(shared_context: Mapping[str, Any] | None) -> dict[str, dict[str, float]]:
    if not isinstance(shared_context, Mapping):
        return {}
    raw = shared_context.get("fit_frame_overrides")
    if not isinstance(raw, Mapping):
        return {}
    overrides: dict[str, dict[str, float]] = {}
    for model_id, frame_values in raw.items():
        if not isinstance(model_id, str) or not isinstance(frame_values, Mapping):
            continue
        parsed: dict[str, float] = {}
        for frame_name, score in frame_values.items():
            if isinstance(frame_name, str) and isinstance(score, (int, float)):
                parsed[frame_name] = max(0.0, min(1.0, float(score)))
        overrides[model_id] = parsed
    return overrides


def _frame_weights(intent: Intent, shared_context: Mapping[str, Any] | None) -> dict[str, float]:
    weights = {frame_name: 1.0 for frame_name in FRAME_NAMES}

    preference_terms = _tokenize(intent.preferences)
    friction_terms = _tokenize(intent.friction_factors)
    constraint_terms = _tokenize(intent.constraints)

    if constraint_terms:
        weights["explicit_constraint_fit"] += 0.2
    if friction_terms:
        weights["friction"] += 0.2

    if preference_terms & {"fast", "faster", "quick", "quickly", "timely", "immediate", "urgent", "soon"}:
        weights["timing"] += 0.75
    if preference_terms & {"safe", "safer", "safest", "careful", "carefully", "cautious", "cautiously", "reliable", "stability", "stable"}:
        weights["risk"] += 0.75
        weights["explicit_constraint_fit"] += 0.2
    if preference_terms & {"easy", "easier", "simple", "simpler", "lightweight", "effort", "effortless", "low", "friction"}:
        weights["friction"] += 0.6
    if preference_terms & {"useful", "usefulness", "thorough", "thoroughly", "complete", "comprehensive", "coverage"}:
        weights["usefulness"] += 0.35
        weights["achievement_goal_fit"] += 0.15

    if isinstance(shared_context, Mapping):
        raw = shared_context.get("fit_frame_weights")
        if isinstance(raw, Mapping):
            for frame_name, weight in raw.items():
                if isinstance(frame_name, str) and frame_name in weights and isinstance(weight, (int, float)):
                    weights[frame_name] = max(0.1, float(weight))

    return weights


def _weighted_summary_score(frame_scores: dict[str, float], frame_weights: Mapping[str, float]) -> float:
    total_weight = sum(max(0.1, float(frame_weights.get(frame_name, 1.0) or 1.0)) for frame_name in FRAME_NAMES)
    if total_weight <= 0.0:
        return sum(frame_scores.values()) / float(len(FRAME_NAMES))
    return sum(
        frame_scores[frame_name] * max(0.1, float(frame_weights.get(frame_name, 1.0) or 1.0))
        for frame_name in FRAME_NAMES
    ) / total_weight


def _heuristic_frame_scores(intent: Intent, model: FulfillmentModel) -> dict[str, float]:
    model_terms = _model_terms(model)
    goal_terms = _tokenize([intent.achievement_goal, *intent.success_criteria])
    constraint_terms = _tokenize(intent.constraints)
    friction_terms = _tokenize(intent.friction_factors)
    preference_terms = _tokenize(intent.preferences)
    risk_terms = _tokenize([*intent.constraints, *intent.preferences, *intent.friction_factors])
    need_penalty = min(0.4, 0.08 * len(model.information_needs))

    explicit_constraint_fit = _overlap_score(constraint_terms, model_terms) if constraint_terms else 1.0
    achievement_goal_fit = _overlap_score(goal_terms, model_terms)

    friction_hits = _overlap_score(friction_terms, _tokenize([*model.expected_friction, *model.risks])) if friction_terms else 0.0
    friction = max(0.0, 1.0 - friction_hits)

    timing_positive = _overlap_score(preference_terms | _tokenize(["fast", "faster", "quick", "timely"]), model_terms)
    timing = max(0.0, timing_positive - need_penalty / 2.0)

    risk_overlap = _overlap_score(risk_terms, _tokenize(model.risks)) if risk_terms else 0.0
    risk = max(0.0, 1.0 - risk_overlap)

    usefulness = max(0.0, min(1.0, ((achievement_goal_fit * 0.5) + (explicit_constraint_fit * 0.3) + (timing * 0.2)) - need_penalty))

    return {
        "explicit_constraint_fit": explicit_constraint_fit,
        "achievement_goal_fit": achievement_goal_fit,
        "friction": friction,
        "timing": timing,
        "risk": risk,
        "usefulness": usefulness,
    }


def _resolved_frame_scores(
    intent: Intent,
    model: FulfillmentModel,
    shared_context: Mapping[str, Any] | None,
) -> dict[str, float]:
    scores = _heuristic_frame_scores(intent, model)
    override_scores = _frame_overrides(shared_context).get(model.model_id, {})
    scores.update({name: score for name, score in override_scores.items() if name in FRAME_NAMES})
    return scores


def _frame_rationale(frame_name: str, score: float) -> list[str]:
    if score >= 0.85:
        return [f"{frame_name} strongly supports this model"]
    if score >= 0.65:
        return [f"{frame_name} supports this model"]
    if score >= 0.4:
        return [f"{frame_name} is mixed for this model"]
    return [f"{frame_name} is weak for this model"]


def _fit_band(frame_scores: dict[str, float]) -> tuple[bool, str, list[str], list[str], list[str]]:
    blockers: list[str] = []
    keep_reasons: list[str] = []
    reject_reasons: list[str] = []

    if frame_scores["explicit_constraint_fit"] < 0.5:
        blockers.append("explicit constraints are not sufficiently satisfied")
        reject_reasons.append("constraint fit too low")
        return False, "not_fit", keep_reasons, reject_reasons, blockers

    if frame_scores["achievement_goal_fit"] < 0.45:
        reject_reasons.append("achievement goal fit too low")
        return False, "not_fit", keep_reasons, reject_reasons, blockers

    high_frames = sum(1 for value in frame_scores.values() if value >= 0.75)
    viable_frames = sum(1 for value in frame_scores.values() if value >= 0.6)

    if high_frames >= 3 and frame_scores["usefulness"] >= 0.65:
        keep_reasons.append("multiple fit frames score strongly")
        return True, "strong_fit", keep_reasons, reject_reasons, blockers

    if viable_frames >= 3 and frame_scores["usefulness"] >= 0.5:
        keep_reasons.append("enough fit frames remain meaningfully positive")
        return True, "viable_fit", keep_reasons, reject_reasons, blockers

    reject_reasons.append("insufficient cross-frame support")
    return False, "weak_fit", keep_reasons, reject_reasons, blockers


@dataclass(slots=True)
class FitEvaluator:
    """Evaluate fulfillment models across multiple fit frames.

    The evaluator must support simultaneous viable fits and must not collapse to
    a single best answer merely because one aggregate score is numerically high.
    """

    config: Mapping[str, Any] = field(default_factory=dict)

    def evaluate(
        self,
        intent: Intent,
        models: list[FulfillmentModel],
        *,
        prior_assessments: list[FitAssessment] | None = None,
        shared_context: Mapping[str, Any] | None = None,
    ) -> list[FitAssessment]:
        """Return fit assessments for the current intent/model set.

        This evaluator keeps fit frames separate. It does not collapse to a
        single winner and it permits multiple models to remain high-fit when
        tradeoffs are materially different.

        TODO:
        - Refine heuristic scoring once execution evidence is available.
        - Add dominance analysis without collapsing away meaningful tradeoffs.
        """
        assessments: list[FitAssessment] = []
        frame_weights = _frame_weights(intent, shared_context)
        for index, model in enumerate(models or []):
            frame_scores = _resolved_frame_scores(intent, model, shared_context)
            valid, fit_band, keep_reasons, reject_reasons, blockers = _fit_band(frame_scores)
            frame_score_objects = [
                FrameScore(
                    frame=cast(FitFrame, frame_name),
                    score=frame_scores[frame_name],
                    rationale=_frame_rationale(frame_name, frame_scores[frame_name]),
                    sensitivity_factors=[],
                )
                for frame_name in FRAME_NAMES
            ]
            summary_score = _weighted_summary_score(frame_scores, frame_weights)
            assessments.append(
                FitAssessment(
                    assessment_id=f"fit:{intent.intent_id}:{model.model_id}:{index}",
                    intent_id=intent.intent_id,
                    model_id=model.model_id,
                    frame_scores=frame_score_objects,
                    overall_fit_score=summary_score,
                    valid=valid,
                    keep_reasons=keep_reasons,
                    reject_reasons=reject_reasons,
                    blockers=blockers,
                    missing_information_dependencies=list(model.information_needs),
                    compared_model_ids=[other.model_id for other in models if other.model_id != model.model_id],
                    fit_band=fit_band,
                )
            )
        return assessments


def evaluate_model_fit(
    intent: Intent,
    models: list[FulfillmentModel],
    *,
    prior_assessments: list[FitAssessment] | None = None,
    shared_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[FitAssessment]:
    """Convenience wrapper for fit evaluation.

    The wrapper preserves a pure-style seam so tests can exercise evaluator
    behavior without relying on broader Nova runtime state.
    """
    evaluator = FitEvaluator(config=config or {})
    return evaluator.evaluate(
        intent,
        models,
        prior_assessments=prior_assessments,
        shared_context=shared_context,
    )
