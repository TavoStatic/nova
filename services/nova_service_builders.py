from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from services.fulfillment_flow import FulfillmentFlowService
from services.identity_memory import IdentityMemoryService
from services.policy_manager import PolicyManager


def build_policy_manager(policy_path: Path, policy_audit_log: Path, base_dir: Path) -> PolicyManager:
    return PolicyManager(policy_path, policy_audit_log, base_dir)


def build_identity_memory_service(
    *,
    normalize_text_fn: Callable[[str], str],
) -> IdentityMemoryService:
    return IdentityMemoryService(
        normalize_text_fn=normalize_text_fn,
    )


def build_fulfillment_flow_service(
    *,
    probe_turn_routes_fn: Callable[..., Any],
    update_subconscious_state_fn: Callable[..., Any],
    session_state_service: type,
) -> FulfillmentFlowService:
    return FulfillmentFlowService(
        probe_turn_routes_fn=probe_turn_routes_fn,
        update_subconscious_state_fn=update_subconscious_state_fn,
        session_state_service=session_state_service,
    )
