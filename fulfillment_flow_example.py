"""Small end-to-end demonstration of Nova's fulfillment architecture.

This module uses placeholder example content only to exercise the shape of the
architecture. It is not intended to define domain logic or become the basis for
content-first routing.
"""

from __future__ import annotations

from dataclasses import dataclass

from choice_presenter import ChoicePresenter
from dynamic_replanner import DynamicReplanner
from fit_evaluator import FitEvaluator
from fulfillment_contracts import ChoiceSet, FitAssessment, FulfillmentModel, Intent, ReplanContext, ReplanReason
from fulfillment_model_generator import FulfillmentModelGenerator
from intent_interpreter import IntentInterpreter


@dataclass(slots=True)
class DemoFlowResult:
    intent: Intent
    models: list[FulfillmentModel]
    assessments: list[FitAssessment]
    choice_set: ChoiceSet
    replanned_models: list[FulfillmentModel]
    replanned_assessments: list[FitAssessment]
    replanned_choice_set: ChoiceSet


class DemoIntentInterpreter(IntentInterpreter):
    """Minimal demo interpreter that keeps the intent stable and generic."""

    def interpret(
        self,
        raw_input: str,
        *,
        current_intent: Intent | None = None,
        shared_context: dict[str, object] | None = None,
    ) -> Intent:
        preferences = ["useful", "low friction", "timely"]
        constraints = ["stay within current constraints"]
        if current_intent is not None:
            evidence = list(current_intent.evidence)
            evidence.append(raw_input)
            return Intent(
                intent_id=current_intent.intent_id,
                achievement_goal=current_intent.achievement_goal,
                success_criteria=list(current_intent.success_criteria),
                constraints=list(current_intent.constraints),
                friction_factors=list(current_intent.friction_factors),
                preferences=list(current_intent.preferences),
                unresolved_questions=list(current_intent.unresolved_questions),
                ambiguity_notes=list(current_intent.ambiguity_notes),
                evidence=evidence,
                confidence=current_intent.confidence,
            )

        return Intent(
            intent_id="demo-intent",
            achievement_goal="reach a workable result",
            success_criteria=["result is achieved", "path remains explainable"],
            constraints=constraints,
            friction_factors=["avoid unnecessary effort"],
            preferences=preferences,
            unresolved_questions=["which tradeoff balance is best under the latest facts"],
            ambiguity_notes=["several fulfillment shapes may remain valid"],
            evidence=[raw_input],
            confidence=0.7,
        )


class DemoFulfillmentModelGenerator(FulfillmentModelGenerator):
    """Minimal demo generator that produces distinct path shapes."""

    def generate(
        self,
        intent: Intent,
        *,
        existing_models: list[FulfillmentModel] | None = None,
        shared_context: dict[str, object] | None = None,
    ) -> list[FulfillmentModel]:
        generated = [
            FulfillmentModel(
                model_id="demo-guided",
                intent_id=intent.intent_id,
                label="Guided lower-friction path",
                description="Reduce effort before committing.",
                path_shape="guided_decision",
                differentiators=["lower user effort", "more feedback before commit"],
                strengths=["lower friction"],
                expected_friction=["slower than direct resolution"],
                risks=["may take longer to converge"],
            ),
            FulfillmentModel(
                model_id="demo-direct",
                intent_id=intent.intent_id,
                label="Direct faster path",
                description="Move directly toward the result.",
                path_shape="direct_resolution",
                differentiators=["faster completion", "higher immediate commitment"],
                strengths=["faster time to value"],
                expected_friction=["more commitment earlier"],
                risks=["higher mismatch risk if assumptions are wrong"],
            ),
        ]

        if not existing_models:
            return generated

        retained_by_id = {model.model_id: model for model in existing_models}
        for model in generated:
            retained_by_id[model.model_id] = model
        return list(retained_by_id.values())


def run_demo_flow() -> DemoFlowResult:
    interpreter = DemoIntentInterpreter()
    generator = DemoFulfillmentModelGenerator()
    evaluator = FitEvaluator()
    presenter = ChoicePresenter()
    replanner = DynamicReplanner()

    intent = interpreter.interpret(
        "Show a workable way to achieve the result while keeping friction reasonable and preserving useful alternatives."
    )
    models = generator.generate(intent)

    initial_assessments = evaluator.evaluate(
        intent,
        models,
        shared_context={
            "fit_frame_overrides": {
                "demo-guided": {
                    "explicit_constraint_fit": 0.91,
                    "achievement_goal_fit": 0.82,
                    "friction": 0.95,
                    "timing": 0.6,
                    "risk": 0.84,
                    "usefulness": 0.86,
                },
                "demo-direct": {
                    "explicit_constraint_fit": 0.92,
                    "achievement_goal_fit": 0.83,
                    "friction": 0.62,
                    "timing": 0.96,
                    "risk": 0.74,
                    "usefulness": 0.85,
                },
            }
        },
    )
    choice_set = presenter.present(intent, models, initial_assessments)

    replan_context = ReplanContext(
        replan_id="demo-replan-1",
        intent_id=intent.intent_id,
        reason=ReplanReason.NEW_INFORMATION,
        trigger_summary="new information makes the direct path less safe under current constraints",
        may_revise_fit=True,
        may_revise_choice=True,
        previous_selected_model_id=choice_set.selected_model_id,
        previous_collapse_status=choice_set.collapse_status,
    )
    replanned_intent, replanned_models, replanned_assessments, replanned_choice_set = replanner.replan(
        replan_context,
        intent=intent,
        models=models,
        assessments=None,
        choice_set=choice_set,
        shared_context={
            "fit_frame_overrides": {
                "demo-guided": {
                    "explicit_constraint_fit": 0.91,
                    "achievement_goal_fit": 0.85,
                    "friction": 0.96,
                    "timing": 0.72,
                    "risk": 0.88,
                    "usefulness": 0.9,
                },
                "demo-direct": {
                    "explicit_constraint_fit": 0.38,
                    "achievement_goal_fit": 0.83,
                    "friction": 0.6,
                    "timing": 0.95,
                    "risk": 0.42,
                    "usefulness": 0.7,
                },
            }
        },
    )
    if replanned_intent is None or replanned_models is None or replanned_assessments is None or replanned_choice_set is None:
        raise RuntimeError("demo flow expected complete replanned state")

    return DemoFlowResult(
        intent=intent,
        models=models,
        assessments=initial_assessments,
        choice_set=choice_set,
        replanned_models=replanned_models,
        replanned_assessments=replanned_assessments,
        replanned_choice_set=replanned_choice_set,
    )
