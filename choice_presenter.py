"""Choice presentation seams for Nova's shared-state architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fulfillment_contracts import (
    ChoiceMode,
    ChoiceOption,
    ChoiceSet,
    CollapseStatus,
    FitAssessment,
    FulfillmentModel,
    Intent,
)


FRAME_LABELS = {
    "explicit_constraint_fit": "constraint fit",
    "achievement_goal_fit": "goal fit",
    "friction": "friction",
    "timing": "timing",
    "risk": "risk",
    "usefulness": "usefulness",
    "goal_attainment": "goal fit",
    "practical_friction": "friction",
    "feasibility": "feasibility",
    "time_to_value": "timing",
    "user_effort": "user effort",
}


FIT_BAND_WEIGHT = {
    "strong_fit": 3,
    "viable_fit": 2,
    "weak_fit": 1,
    "not_fit": 0,
}


def _is_valid_assessment(assessment: FitAssessment) -> bool:
    return bool(assessment.valid) and assessment.fit_band != "not_fit"


def _model_signature(model: FulfillmentModel) -> tuple[object, ...]:
    return (
        model.path_shape,
        tuple(sorted(model.differentiators)),
        tuple(sorted(model.assumptions)),
        tuple(sorted(model.prerequisites)),
        tuple(sorted(model.strengths)),
        tuple(sorted(model.expected_friction)),
        tuple(sorted(model.risks)),
    )


def _assessment_rank(assessment: FitAssessment) -> tuple[int, float]:
    return (
        FIT_BAND_WEIGHT.get(assessment.fit_band, 0),
        assessment.overall_fit_score or 0.0,
    )


def _dedupe_meaningless_variants(
    models: list[FulfillmentModel],
    assessments: Mapping[str, FitAssessment],
) -> list[FulfillmentModel]:
    retained_by_signature: dict[tuple[object, ...], FulfillmentModel] = {}
    for model in models:
        signature = _model_signature(model)
        current = retained_by_signature.get(signature)
        if current is None:
            retained_by_signature[signature] = model
            continue

        current_assessment = assessments[current.model_id]
        candidate_assessment = assessments[model.model_id]
        if _assessment_rank(candidate_assessment) > _assessment_rank(current_assessment):
            retained_by_signature[signature] = model
    return list(retained_by_signature.values())


def _frame_name(frame: object) -> str:
    value = getattr(frame, "value", frame)
    return str(value)


def _frame_scores(assessment: FitAssessment) -> dict[str, float]:
    return {
        _frame_name(frame_score.frame): frame_score.score
        for frame_score in assessment.frame_scores
    }


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def _comparative_frame_notes(
    model: FulfillmentModel,
    assessments: Mapping[str, FitAssessment],
    peer_models: list[FulfillmentModel],
) -> tuple[list[str], list[str], list[str]]:
    current_scores = _frame_scores(assessments[model.model_id])
    peer_score_maps = [
        _frame_scores(assessments[peer.model_id])
        for peer in peer_models
        if peer.model_id != model.model_id
    ]

    strength_candidates: list[tuple[float, str, str]] = []
    tradeoff_candidates: list[tuple[float, str, str]] = []
    distinct_dimensions: list[str] = []
    for frame_name, score in current_scores.items():
        label = FRAME_LABELS.get(frame_name, frame_name.replace("_", " "))
        peer_scores = [peer_map.get(frame_name, 0.0) for peer_map in peer_score_maps]
        if peer_scores:
            best_peer = max(peer_scores)
            worst_peer = min(peer_scores)
            if score - best_peer >= 0.15:
                note = f"stronger {label}"
                strength_candidates.append((score - best_peer, note, label))
                distinct_dimensions.append(label)
            elif worst_peer - score >= 0.15:
                note = f"weaker {label}"
                tradeoff_candidates.append((worst_peer - score, note, label))
                distinct_dimensions.append(label)
            continue

        if score >= 0.8:
            strength_candidates.append((score, f"strong {label}", label))
        elif score <= 0.45:
            tradeoff_candidates.append((1.0 - score, f"weaker {label}", label))

    strength_candidates.sort(key=lambda item: (-item[0], item[2]))
    tradeoff_candidates.sort(key=lambda item: (-item[0], item[2]))

    ordered_dimensions: list[str] = []
    for _, _, label in [*strength_candidates, *tradeoff_candidates]:
        if label not in ordered_dimensions:
            ordered_dimensions.append(label)
    for label in distinct_dimensions:
        if label not in ordered_dimensions:
            ordered_dimensions.append(label)

    return [item[1] for item in strength_candidates[:3]], [item[1] for item in tradeoff_candidates[:3]], ordered_dimensions


def _format_dimension_list(dimensions: list[str]) -> str:
    if not dimensions:
        return ""
    if len(dimensions) == 1:
        return dimensions[0]
    if len(dimensions) == 2:
        return f"{dimensions[0]} and {dimensions[1]}"
    return ", ".join(dimensions[:-1]) + f", and {dimensions[-1]}"


def _build_choice_option(
    model: FulfillmentModel,
    assessment: FitAssessment,
    peer_models: list[FulfillmentModel],
    assessments: Mapping[str, FitAssessment],
    *,
    recommended: bool,
) -> tuple[ChoiceOption, list[str]]:
    frame_strengths, frame_tradeoffs, distinct_dimensions = _comparative_frame_notes(
        model,
        assessments,
        peer_models,
    )

    why_distinct: list[str] = []
    _append_unique(why_distinct, list(model.differentiators))
    _append_unique(why_distinct, list(model.strengths))
    _append_unique(why_distinct, list(assessment.keep_reasons))
    _append_unique(why_distinct, frame_strengths)

    tradeoffs: list[str] = []
    _append_unique(tradeoffs, list(model.expected_friction))
    _append_unique(tradeoffs, list(model.risks))
    _append_unique(tradeoffs, list(assessment.reject_reasons))
    _append_unique(tradeoffs, list(assessment.blockers))
    _append_unique(tradeoffs, frame_tradeoffs)

    return (
        ChoiceOption(
            model_id=model.model_id,
            label=model.label,
            why_distinct=why_distinct,
            tradeoffs=tradeoffs,
            recommended=recommended,
        ),
        distinct_dimensions,
    )


def _base_choice_set_id(intent: Intent, current_choice_set: ChoiceSet | None) -> str:
    return current_choice_set.choice_set_id if current_choice_set else f"choice:{intent.intent_id}"


@dataclass(slots=True)
class ChoicePresenter:
    """Present either one justified result or multiple distinct choices.

    The presenter must respect explicit collapse/plurality state and should not
    flatten meaningful alternatives into a single synthesized answer.
    """

    config: Mapping[str, Any] = field(default_factory=dict)

    def present(
        self,
        intent: Intent,
        models: list[FulfillmentModel],
        assessments: list[FitAssessment],
        *,
        current_choice_set: ChoiceSet | None = None,
        shared_context: Mapping[str, Any] | None = None,
    ) -> ChoiceSet:
        """Return a ChoiceSet reflecting the current valid fulfillment space.

        TODO:
        - Preserve multiple valid fulfillment shapes as distinct options.
        - Collapse to one result only when explicitly justified.
        - Surface decisive tradeoffs without inventing fake diversity.
        """
        choice_set_id = _base_choice_set_id(intent, current_choice_set)
        assessment_by_model = {
            assessment.model_id: assessment
            for assessment in (assessments or [])
            if _is_valid_assessment(assessment)
        }
        valid_models = [
            model
            for model in (models or [])
            if model.active and model.model_id in assessment_by_model
        ]
        distinct_models = _dedupe_meaningless_variants(valid_models, assessment_by_model)
        distinct_models.sort(key=lambda model: _assessment_rank(assessment_by_model[model.model_id]), reverse=True)
        if not distinct_models:
            return ChoiceSet(
                choice_set_id=choice_set_id,
                intent_id=intent.intent_id,
                mode=ChoiceMode.MULTI_CHOICE,
                collapse_status=CollapseStatus.NOT_EVALUATED,
                options=[],
                selected_model_id=None,
                plurality_reason="no valid fulfillment shapes remain",
                collapse_reason=None,
                user_decision_needed=False,
            )

        if len(distinct_models) == 1:
            model = distinct_models[0]
            option, _ = _build_choice_option(
                model,
                assessment_by_model[model.model_id],
                distinct_models,
                assessment_by_model,
                recommended=True,
            )
            return ChoiceSet(
                choice_set_id=choice_set_id,
                intent_id=intent.intent_id,
                mode=ChoiceMode.SINGLE_RESULT,
                collapse_status=CollapseStatus.COLLAPSED,
                options=[option],
                selected_model_id=model.model_id,
                plurality_reason=None,
                collapse_reason="single distinct valid fulfillment shape",
                user_decision_needed=False,
            )

        options: list[ChoiceOption] = []
        distinct_dimensions: list[str] = []
        for model in distinct_models:
            option, option_dimensions = _build_choice_option(
                model,
                assessment_by_model[model.model_id],
                distinct_models,
                assessment_by_model,
                recommended=False,
            )
            options.append(option)
            _append_unique(distinct_dimensions, option_dimensions)

        plurality_reason = "multiple materially distinct valid fulfillment shapes remain"
        if distinct_dimensions:
            plurality_reason = (
                "multiple materially distinct valid fulfillment shapes remain across "
                + _format_dimension_list(distinct_dimensions[:3])
            )

        return ChoiceSet(
            choice_set_id=choice_set_id,
            intent_id=intent.intent_id,
            mode=ChoiceMode.MULTI_CHOICE,
            collapse_status=CollapseStatus.MANY_VALID,
            options=options,
            selected_model_id=None,
            plurality_reason=plurality_reason,
            collapse_reason=None,
            user_decision_needed=True,
        )


def build_choice_set(
    intent: Intent,
    models: list[FulfillmentModel],
    assessments: list[FitAssessment],
    *,
    current_choice_set: ChoiceSet | None = None,
    shared_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ChoiceSet:
    """Convenience wrapper for choice-set construction.

    TODO:
    - Keep this wrapper free of presentation-side mutation.
    - Make it easy to compare expected single-result vs multi-choice outputs.
    """
    presenter = ChoicePresenter(config=config or {})
    return presenter.present(
        intent,
        models,
        assessments,
        current_choice_set=current_choice_set,
        shared_context=shared_context,
    )
