from __future__ import annotations

import time
from typing import Optional


def _load_fulfillment_dependencies() -> Optional[dict[str, object]]:
    try:
        from choice_presenter import ChoiceMode, ChoicePresenter
        from dynamic_replanner import DynamicReplanner
        from fit_evaluator import FitEvaluator
        from fulfillment_contracts import CollapseStatus, ReplanContext, ReplanReason
        from fulfillment_model_generator import FulfillmentModelGenerator
        from intent_interpreter import IntentInterpreter
    except Exception:
        return None
    return {
        "ChoiceMode": ChoiceMode,
        "ChoicePresenter": ChoicePresenter,
        "DynamicReplanner": DynamicReplanner,
        "FitEvaluator": FitEvaluator,
        "CollapseStatus": CollapseStatus,
        "ReplanContext": ReplanContext,
        "ReplanReason": ReplanReason,
        "FulfillmentModelGenerator": FulfillmentModelGenerator,
        "IntentInterpreter": IntentInterpreter,
    }


class FulfillmentFlowService:
    def __init__(
        self,
        *,
        probe_turn_routes_fn,
        update_subconscious_state_fn,
        session_state_service,
    ):
        self._probe_turn_routes = probe_turn_routes_fn
        self._update_subconscious_state = update_subconscious_state_fn
        self._session_state_service = session_state_service

    def should_attempt_fulfillment_flow(
        self,
        user_text: str,
        session: object,
        recent_turns: list[tuple[str, str]],
        *,
        pending_action: Optional[dict] = None,
    ) -> bool:
        probe = self._probe_turn_routes(
            user_text,
            session,
            recent_turns,
            pending_action=pending_action,
        )
        routes = probe.get("routes") if isinstance(probe.get("routes"), dict) else {}
        supervisor_route = routes.get("supervisor_owned") if isinstance(routes.get("supervisor_owned"), dict) else {}
        fulfillment_route = routes.get("fulfillment_applicable") if isinstance(routes.get("fulfillment_applicable"), dict) else {}
        if bool(supervisor_route.get("viable")):
            return False
        if not bool(fulfillment_route.get("viable")):
            return False
        return str(probe.get("comparison_strength") or "weak").strip().lower() == "clear"

    @staticmethod
    def build_fulfillment_state(
        intent: object,
        models: list[object],
        assessments: list[object],
        choice_set: object,
    ) -> dict:
        return {
            "intent": intent,
            "models": list(models or []),
            "assessments": list(assessments or []),
            "choice_set": choice_set,
        }

    @staticmethod
    def render_fulfillment_reply(choice_set: object) -> str:
        options = list(getattr(choice_set, "options", []) or [])
        if not options:
            return ""

        mode = str(getattr(getattr(choice_set, "mode", None), "value", getattr(choice_set, "mode", "")) or "")
        selected_model_id = str(getattr(choice_set, "selected_model_id", "") or "")
        if mode == "single_result":
            option = next((item for item in options if str(getattr(item, "model_id", "") or "") == selected_model_id), options[0])
            reply = f"I see one current fulfillment result: {str(getattr(option, 'label', '') or 'current path')}."
            why_distinct = [str(item).strip() for item in list(getattr(option, "why_distinct", []) or []) if str(item).strip()]
            tradeoffs = [str(item).strip() for item in list(getattr(option, "tradeoffs", []) or []) if str(item).strip()]
            if why_distinct:
                reply += f" Why this path: {'; '.join(why_distinct[:2])}."
            if tradeoffs:
                reply += f" Tradeoffs: {'; '.join(tradeoffs[:2])}."
            return reply

        lines = ["I see multiple meaningful fulfillment paths right now:"]
        for option in options[:3]:
            label = str(getattr(option, "label", "") or "option")
            why_distinct = [str(item).strip() for item in list(getattr(option, "why_distinct", []) or []) if str(item).strip()]
            tradeoffs = [str(item).strip() for item in list(getattr(option, "tradeoffs", []) or []) if str(item).strip()]
            line = f"- {label}"
            if why_distinct:
                line += f": {why_distinct[0]}"
            if tradeoffs:
                line += f"; tradeoff: {tradeoffs[0]}"
            lines.append(line)
        plurality_reason = str(getattr(choice_set, "plurality_reason", "") or "").strip()
        if plurality_reason:
            lines.append(f"Why they remain distinct: {plurality_reason}.")
        return "\n".join(lines)

    def maybe_run_fulfillment_flow(
        self,
        user_text: str,
        session: object,
        recent_turns: list[tuple[str, str]],
        *,
        pending_action: Optional[dict] = None,
    ) -> Optional[dict]:
        probe = self._probe_turn_routes(
            user_text,
            session,
            recent_turns,
            pending_action=pending_action,
        )
        routes = probe.get("routes") if isinstance(probe.get("routes"), dict) else {}
        supervisor_route = routes.get("supervisor_owned") if isinstance(routes.get("supervisor_owned"), dict) else {}
        fulfillment_route = routes.get("fulfillment_applicable") if isinstance(routes.get("fulfillment_applicable"), dict) else {}
        should_attempt = (
            not bool(supervisor_route.get("viable"))
            and bool(fulfillment_route.get("viable"))
            and str(probe.get("comparison_strength") or "weak").strip().lower() == "clear"
        )
        if not should_attempt:
            self._update_subconscious_state(session, probe, chosen_route="generic_fallback")
            return None

        deps = _load_fulfillment_dependencies()
        if deps is None:
            return None

        ChoiceMode = deps["ChoiceMode"]
        ChoicePresenter = deps["ChoicePresenter"]
        DynamicReplanner = deps["DynamicReplanner"]
        FitEvaluator = deps["FitEvaluator"]
        CollapseStatus = deps["CollapseStatus"]
        ReplanContext = deps["ReplanContext"]
        ReplanReason = deps["ReplanReason"]
        FulfillmentModelGenerator = deps["FulfillmentModelGenerator"]
        IntentInterpreter = deps["IntentInterpreter"]

        state = self._session_state_service.get_fulfillment_state(session)
        try:
            if state is None:
                interpreter = IntentInterpreter()
                generator = FulfillmentModelGenerator()
                evaluator = FitEvaluator()
                presenter = ChoicePresenter()

                intent = interpreter.interpret(
                    user_text,
                    current_intent=None,
                    shared_context={"recent_turns": list(recent_turns or [])},
                )
                models = generator.generate(
                    intent,
                    existing_models=None,
                    shared_context={"recent_turns": list(recent_turns or [])},
                )
                assessments = evaluator.evaluate(
                    intent,
                    models,
                    shared_context={"recent_turns": list(recent_turns or [])},
                )
                choice_set = presenter.present(
                    intent,
                    models,
                    assessments,
                    current_choice_set=None,
                    shared_context={"recent_turns": list(recent_turns or [])},
                )
                state = self.build_fulfillment_state(intent, models, assessments, choice_set)
            else:
                intent = state.get("intent")
                models = list(state.get("models") or [])
                assessments = list(state.get("assessments") or [])
                choice_set = state.get("choice_set")
                if intent is None or not models or choice_set is None:
                    return None

                replanner = DynamicReplanner()
                revised_intent, revised_models, revised_assessments, revised_choice_set = replanner.replan(
                    ReplanContext(
                        replan_id=f"replan:{str(getattr(intent, 'intent_id', '') or 'intent')}:{int(time.time() * 1000)}",
                        intent_id=str(getattr(intent, "intent_id", "") or ""),
                        reason=ReplanReason.NEW_INFORMATION,
                        trigger_summary=str(user_text or "")[:160],
                        changed_facts={"new_information": str(user_text or "")},
                        may_revise_fit=True,
                        may_revise_choice=True,
                        previous_active_model_ids=[str(getattr(model, "model_id", "") or "") for model in models],
                        previous_selected_model_id=str(getattr(choice_set, "selected_model_id", "") or "") or None,
                        previous_collapse_status=getattr(choice_set, "collapse_status", CollapseStatus.NOT_EVALUATED),
                    ),
                    intent=intent,
                    models=models,
                    assessments=assessments,
                    choice_set=choice_set,
                    shared_context={"recent_turns": list(recent_turns or []), "new_information": str(user_text or "")},
                )
                if revised_intent is None or revised_models is None or revised_assessments is None or revised_choice_set is None:
                    return None
                state = self.build_fulfillment_state(revised_intent, revised_models, revised_assessments, revised_choice_set)
        except NotImplementedError:
            self._update_subconscious_state(session, probe, chosen_route="generic_fallback")
            return None
        except Exception:
            self._update_subconscious_state(session, probe, chosen_route="generic_fallback")
            return None

        self._session_state_service.set_fulfillment_state(session, state)
        choice_set = state.get("choice_set")
        if choice_set is None or not list(getattr(choice_set, "options", []) or []):
            self._update_subconscious_state(session, probe, chosen_route="generic_fallback")
            return None

        mode = str(getattr(getattr(choice_set, "mode", None), "value", getattr(choice_set, "mode", "")) or "")
        if mode not in {ChoiceMode.SINGLE_RESULT.value, ChoiceMode.MULTI_CHOICE.value}:
            self._update_subconscious_state(session, probe, chosen_route="generic_fallback")
            return None

        self._update_subconscious_state(session, probe, chosen_route="fulfillment_applicable")

        return {
            "reply": self.render_fulfillment_reply(choice_set),
            "state": state,
            "choice_set": choice_set,
            "planner_decision": "fulfillment_single_result" if mode == ChoiceMode.SINGLE_RESULT.value else "fulfillment_choice",
            "grounded": True,
        }