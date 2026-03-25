"""Fulfillment model generation seams for Nova's shared-state architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fulfillment_contracts import FulfillmentModel, Intent


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _model_by_id(models: list[FulfillmentModel] | None) -> dict[str, FulfillmentModel]:
    return {model.model_id: model for model in list(models or []) if isinstance(model, FulfillmentModel)}


def _filtered_existing_models(intent: Intent, models: list[FulfillmentModel] | None) -> list[FulfillmentModel]:
    retained_by_shape: dict[str, FulfillmentModel] = {}
    for model in list(models or []):
        if not isinstance(model, FulfillmentModel):
            continue
        if str(model.intent_id or "") != str(intent.intent_id or ""):
            continue
        path_shape = str(model.path_shape or "").strip()
        if not path_shape:
            continue
        current = retained_by_shape.get(path_shape)
        if current is None:
            retained_by_shape[path_shape] = model
            continue
        current_strength = len(list(current.differentiators or [])) + len(list(current.strengths or []))
        candidate_strength = len(list(model.differentiators or [])) + len(list(model.strengths or []))
        if candidate_strength > current_strength:
            retained_by_shape[path_shape] = model
    return list(retained_by_shape.values())


def _dedupe_models_by_path_shape(models: list[FulfillmentModel]) -> list[FulfillmentModel]:
    retained_by_shape: dict[str, FulfillmentModel] = {}
    for model in list(models or []):
        if not isinstance(model, FulfillmentModel):
            continue
        path_shape = str(model.path_shape or "").strip()
        if not path_shape:
            continue
        retained_by_shape[path_shape] = model
    return list(retained_by_shape.values())


def _needs_evidence_first_model(intent: Intent) -> bool:
    if intent.constraints or intent.unresolved_questions:
        return True
    low_prefs = " ".join(intent.preferences).lower()
    return any(token in low_prefs for token in ("higher certainty", "preserve alternatives", "keep ambiguity visible"))


def _build_model(intent: Intent, *, model_id: str, label: str, path_shape: str, differentiators: list[str], strengths: list[str], expected_friction: list[str], risks: list[str], information_needs: list[str] | None = None) -> FulfillmentModel:
    return FulfillmentModel(
        model_id=model_id,
        intent_id=intent.intent_id,
        label=label,
        description=(
            f"Reach the requested result through a {path_shape.replace('_', ' ')} path. "
            f"Goal context: {intent.achievement_goal}"
        ),
        path_shape=path_shape,
        differentiators=_unique(differentiators + list(intent.preferences[:2])),
        strengths=_unique(strengths + list(intent.success_criteria[:2])),
        expected_friction=_unique(expected_friction),
        risks=_unique(risks),
        information_needs=_unique(list(information_needs or []) + list(intent.unresolved_questions[:1])),
    )


@dataclass(slots=True)
class FulfillmentModelGenerator:
    """Generate materially distinct fulfillment models for an intent.

    The generator must produce genuinely different fulfillment shapes rather
    than reworded duplicates. It should update shared state-friendly model sets
    without collapsing to a single answer.
    """

    config: Mapping[str, Any] = field(default_factory=dict)

    def generate(
        self,
        intent: Intent,
        *,
        existing_models: list[FulfillmentModel] | None = None,
        shared_context: Mapping[str, Any] | None = None,
    ) -> list[FulfillmentModel]:
        """Return a revised set of fulfillment models for the given intent.

        TODO:
        - Produce structurally distinct models with explicit differentiators.
        - Preserve viable prior models when new input does not invalidate them.
        - Avoid fake alternatives that differ only in phrasing.
        """
        retained = _filtered_existing_models(intent, existing_models)
        generated = [
            _build_model(
                intent,
                model_id=f"{intent.intent_id}:guided",
                label="Guided lower-friction path",
                path_shape="guided_decision",
                differentiators=["lower user effort", "more clarification before commitment"],
                strengths=["lower friction", "keeps tradeoffs visible"],
                expected_friction=["may take longer before final commitment"],
                risks=["can feel slower when a direct answer is acceptable"],
                information_needs=["latest constraints"],
            ),
            _build_model(
                intent,
                model_id=f"{intent.intent_id}:direct",
                label="Direct faster path",
                path_shape="direct_resolution",
                differentiators=["faster completion", "earlier commitment"],
                strengths=["timely path", "shorter route to a result"],
                expected_friction=["requires faster commitment"],
                risks=["can over-commit if important information is still missing"],
                information_needs=[],
            ),
        ]
        if _needs_evidence_first_model(intent):
            generated.append(
                _build_model(
                    intent,
                    model_id=f"{intent.intent_id}:evidence",
                    label="Evidence-first path",
                    path_shape="evidence_first_then_commit",
                    differentiators=["more verification before commitment", "better when certainty matters"],
                    strengths=["higher certainty", "safer under unresolved questions"],
                    expected_friction=["slower upfront evaluation"],
                    risks=["may delay delivery when timing matters more than certainty"],
                    information_needs=["missing assumptions", "decision criteria"],
                )
            )

        combined = _dedupe_models_by_path_shape(list(retained) + generated)
        return sorted(combined, key=lambda model: str(model.model_id or ""))


def generate_fulfillment_models(
    intent: Intent,
    *,
    existing_models: list[FulfillmentModel] | None = None,
    shared_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[FulfillmentModel]:
    """Convenience wrapper for fulfillment model generation.

    TODO:
    - Keep wrapper behavior minimal and deterministic.
    - Allow tests to inject model fixtures without hidden side effects.
    """
    generator = FulfillmentModelGenerator(config=config or {})
    return generator.generate(
        intent,
        existing_models=existing_models,
        shared_context=shared_context,
    )
