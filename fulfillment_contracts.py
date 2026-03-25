"""Shared contract types for Nova's intent-first fulfillment model system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FitFrame(str, Enum):
    GOAL_ATTAINMENT = "goal_attainment"
    PRACTICAL_FRICTION = "practical_friction"
    FEASIBILITY = "feasibility"
    TIME_TO_VALUE = "time_to_value"
    USER_EFFORT = "user_effort"


class ChoiceMode(str, Enum):
    SINGLE_RESULT = "single_result"
    MULTI_CHOICE = "multi_choice"


class CollapseStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    MANY_VALID = "many_valid"
    SINGLE_VALID = "single_valid"
    COLLAPSED = "collapsed"


class ReplanReason(str, Enum):
    NEW_INFORMATION = "new_information"
    CONSTRAINT_CHANGED = "constraint_changed"
    PREFERENCE_CHANGED = "preference_changed"
    ENVIRONMENT_CHANGED = "environment_changed"
    FIT_CHANGED = "fit_changed"
    MODEL_INVALIDATED = "model_invalidated"
    BRANCH_REQUIRED = "branch_required"
    COLLAPSE_REVERSED = "collapse_reversed"
    AMBIGUITY_DISCOVERED = "ambiguity_discovered"
    AMBIGUITY_RESOLVED = "ambiguity_resolved"
    FRICTION_CHANGED = "friction_changed"


@dataclass(slots=True)
class Intent:
    intent_id: str
    achievement_goal: str
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    friction_factors: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    ambiguity_notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(slots=True)
class FulfillmentModel:
    model_id: str
    intent_id: str
    label: str
    description: str
    path_shape: str
    differentiators: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    expected_friction: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    information_needs: list[str] = field(default_factory=list)
    compared_against_model_ids: list[str] = field(default_factory=list)
    active: bool = True


@dataclass(slots=True)
class FrameScore:
    frame: FitFrame
    score: float
    rationale: list[str] = field(default_factory=list)
    sensitivity_factors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FitAssessment:
    assessment_id: str
    intent_id: str
    model_id: str
    frame_scores: list[FrameScore] = field(default_factory=list)
    overall_fit_score: float | None = None
    valid: bool = True
    keep_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    missing_information_dependencies: list[str] = field(default_factory=list)
    compared_model_ids: list[str] = field(default_factory=list)
    fit_band: str = "viable_fit"


@dataclass(slots=True)
class ChoiceOption:
    model_id: str
    label: str
    why_distinct: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    recommended: bool = False


@dataclass(slots=True)
class ChoiceSet:
    choice_set_id: str
    intent_id: str
    mode: ChoiceMode
    collapse_status: CollapseStatus = CollapseStatus.NOT_EVALUATED
    options: list[ChoiceOption] = field(default_factory=list)
    selected_model_id: str | None = None
    plurality_reason: str | None = None
    collapse_reason: str | None = None
    user_decision_needed: bool = False


@dataclass(slots=True)
class ReplanContext:
    replan_id: str
    intent_id: str
    reason: ReplanReason
    trigger_summary: str
    changed_facts: dict[str, object] = field(default_factory=dict)
    may_revise_intent: bool = False
    may_revise_models: bool = False
    may_revise_fit: bool = False
    may_revise_choice: bool = False
    previous_active_model_ids: list[str] = field(default_factory=list)
    previous_selected_model_id: str | None = None
    previous_collapse_status: CollapseStatus = CollapseStatus.NOT_EVALUATED
    invalidation_notes: list[str] = field(default_factory=list)
