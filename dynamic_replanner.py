"""Dynamic replanning seams for Nova's shared-state architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from choice_presenter import ChoicePresenter
from fit_evaluator import FitEvaluator
from fulfillment_contracts import ChoiceMode, ChoiceSet, FitAssessment, FulfillmentModel, Intent, ReplanContext


FIT_BAND_WEIGHT = {
    "strong_fit": 3,
    "viable_fit": 2,
    "weak_fit": 1,
    "not_fit": 0,
}


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


def _assessment_rank(assessment: FitAssessment | None) -> tuple[int, float]:
    if assessment is None:
        return (-1, -1.0)
    return (
        FIT_BAND_WEIGHT.get(assessment.fit_band, 0),
        assessment.overall_fit_score or 0.0,
    )


def _is_valid_assessment(assessment: FitAssessment | None) -> bool:
    return bool(assessment and assessment.valid and assessment.fit_band != "not_fit")


def _resolve_assessments(
    intent: Intent | None,
    models: list[FulfillmentModel] | None,
    assessments: list[FitAssessment] | None,
    replan_context: ReplanContext,
    shared_context: Mapping[str, Any] | None,
    config: Mapping[str, Any],
) -> list[FitAssessment] | None:
    if assessments is not None:
        return assessments
    if not replan_context.may_revise_fit:
        return assessments
    if intent is None or models is None:
        return assessments
    return FitEvaluator(config=config).evaluate(
        intent,
        models,
        prior_assessments=assessments,
        shared_context=shared_context,
    )


def _dedupe_models(
    models: list[FulfillmentModel],
    assessment_by_model: Mapping[str, FitAssessment],
) -> list[FulfillmentModel]:
    retained_by_signature: dict[tuple[object, ...], FulfillmentModel] = {}
    for model in models:
        signature = _model_signature(model)
        current = retained_by_signature.get(signature)
        if current is None:
            retained_by_signature[signature] = model
            continue
        if _assessment_rank(assessment_by_model.get(model.model_id)) > _assessment_rank(
            assessment_by_model.get(current.model_id)
        ):
            retained_by_signature[signature] = model
    return list(retained_by_signature.values())


def _rank_models(
    models: list[FulfillmentModel],
    assessment_by_model: Mapping[str, FitAssessment],
    previous_selected_model_id: str | None,
) -> list[FulfillmentModel]:
    return sorted(
        models,
        key=lambda model: (
            model.model_id == previous_selected_model_id,
            *_assessment_rank(assessment_by_model.get(model.model_id)),
            model.model_id,
        ),
        reverse=True,
    )


def _prune_models_and_assessments(
    models: list[FulfillmentModel] | None,
    assessments: list[FitAssessment] | None,
    replan_context: ReplanContext,
    config: Mapping[str, Any],
) -> tuple[list[FulfillmentModel] | None, list[FitAssessment] | None]:
    if models is None or assessments is None:
        return models, assessments

    assessment_by_model = {assessment.model_id: assessment for assessment in assessments}
    active_models = [model for model in models if model.active and model.model_id in assessment_by_model]
    deduped_models = _dedupe_models(active_models, assessment_by_model)

    valid_models = [
        model for model in deduped_models if _is_valid_assessment(assessment_by_model.get(model.model_id))
    ]
    ranked_models = _rank_models(valid_models, assessment_by_model, replan_context.previous_selected_model_id)

    max_paths = int(config.get("max_replan_paths", 3)) if config.get("max_replan_paths") is not None else 3
    if max_paths < 1:
        max_paths = 1
    bounded_models = ranked_models[:max_paths]

    retained_ids = {model.model_id for model in bounded_models}
    bounded_assessments = [assessment_by_model[model_id] for model_id in retained_ids]
    bounded_assessments.sort(key=lambda assessment: assessment.model_id)
    bounded_models.sort(key=lambda model: model.model_id)
    return bounded_models, bounded_assessments


def _stabilize_selected_path(
    revised_choice_set: ChoiceSet | None,
    replan_context: ReplanContext,
    assessments: list[FitAssessment] | None,
) -> ChoiceSet | None:
    if revised_choice_set is None or revised_choice_set.mode != ChoiceMode.MULTI_CHOICE:
        return revised_choice_set

    previous_selected_model_id = replan_context.previous_selected_model_id
    if not previous_selected_model_id:
        return revised_choice_set

    option_ids = {option.model_id for option in revised_choice_set.options}
    if previous_selected_model_id not in option_ids:
        return revised_choice_set

    assessment_by_model = {assessment.model_id: assessment for assessment in (assessments or [])}
    if not _is_valid_assessment(assessment_by_model.get(previous_selected_model_id)):
        return revised_choice_set

    revised_choice_set.selected_model_id = previous_selected_model_id
    revised_choice_set.user_decision_needed = True
    return revised_choice_set


@dataclass(slots=True)
class DynamicReplanner:
    """Re-open and revise prior state when new information changes fit.

    The replanner may revise any earlier state, including intent, active models,
    fit assessments, and prior collapse decisions. It should not behave like a
    linear append-only step engine.
    """

    config: Mapping[str, Any] = field(default_factory=dict)

    def replan(
        self,
        replan_context: ReplanContext,
        *,
        intent: Intent | None = None,
        models: list[FulfillmentModel] | None = None,
        assessments: list[FitAssessment] | None = None,
        choice_set: ChoiceSet | None = None,
        shared_context: Mapping[str, Any] | None = None,
    ) -> tuple[
        Intent | None,
        list[FulfillmentModel] | None,
        list[FitAssessment] | None,
        ChoiceSet | None,
    ]:
        """Return revised state fragments in response to a replanning trigger.

        TODO:
        - Allow earlier state to be revised, reopened, or invalidated.
        - Support many-to-one and one-to-many transitions explicitly.
        - Keep replan triggers observable and testable via ReplanContext.
        """
        if intent is not None and intent.intent_id != replan_context.intent_id:
            raise ValueError("replan_context.intent_id must match the stable intent being replanned")

        revised_intent = intent
        revised_assessments = _resolve_assessments(
            intent,
            models,
            assessments,
            replan_context,
            shared_context,
            self.config,
        )
        revised_models = models
        if replan_context.may_revise_fit or replan_context.may_revise_models:
            revised_models, revised_assessments = _prune_models_and_assessments(
                models,
                revised_assessments,
                replan_context,
                self.config,
            )

        revised_choice_set: ChoiceSet | None = choice_set
        if (
            replan_context.may_revise_choice
            and revised_intent is not None
            and revised_models is not None
            and revised_assessments is not None
        ):
            revised_choice_set = ChoicePresenter(config=self.config).present(
                intent,
                revised_models,
                revised_assessments,
                current_choice_set=choice_set,
                shared_context=shared_context,
            )
            revised_choice_set = _stabilize_selected_path(
                revised_choice_set,
                replan_context,
                revised_assessments,
            )
        return revised_intent, revised_models, revised_assessments, revised_choice_set


def replan_state(
    replan_context: ReplanContext,
    *,
    intent: Intent | None = None,
    models: list[FulfillmentModel] | None = None,
    assessments: list[FitAssessment] | None = None,
    choice_set: ChoiceSet | None = None,
    shared_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> tuple[
    Intent | None,
    list[FulfillmentModel] | None,
    list[FitAssessment] | None,
    ChoiceSet | None,
]:
    """Convenience wrapper for dynamic replanning.

    TODO:
    - Keep wrapper behavior transparent for tests.
    - Preserve the ability to replan partial state without hidden defaults.
    """
    replanner = DynamicReplanner(config=config or {})
    return replanner.replan(
        replan_context,
        intent=intent,
        models=models,
        assessments=assessments,
        choice_set=choice_set,
        shared_context=shared_context,
    )
