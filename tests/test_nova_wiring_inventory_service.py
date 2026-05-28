from __future__ import annotations

import unittest

from services.nova_root_inventory import source_root_ids
from services.nova_wiring_inventory import DEFAULT_ADVISORY_ACTIONS
from services.nova_wiring_inventory import DEFAULT_PLANNED_TOOLS
from services.nova_wiring_inventory import DEFAULT_SIGNAL_SOURCES
from services.nova_wiring_inventory import REQUIRED_CLOSURE_PATHS
from services.nova_wiring_inventory import REQUIRED_EVIDENCE_PATHS
from services.nova_wiring_inventory import REQUIRED_JUDGMENT_PATHS
from services.nova_wiring_inventory import REQUIRED_OPERATOR_OUTBOX_PATHS
from services.nova_wiring_inventory import REQUIRED_OWNED_ROOT_ROUTES
from services.nova_wiring_inventory import WIRING_SURFACES
from services.nova_wiring_inventory import build_self_repair_closure_inventory_payload
from services.nova_wiring_inventory import build_source_wiring_probe_payload
from services.nova_wiring_inventory import wiring_surface_ids


def _status_contract() -> dict[str, object]:
    payload: dict[str, object] = {}
    for surface in WIRING_SURFACES:
        for key in surface.status_keys:
            payload[key] = True
    return payload


class NovaWiringInventoryServiceTests(unittest.TestCase):
    def test_empty_status_is_not_self_repair_closed(self) -> None:
        payload = build_self_repair_closure_inventory_payload({})

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["gap_count"], payload["root_count"])
        self.assertEqual(payload["depth_counts"], {"visible_only": payload["root_count"]})

    def test_missing_execution_path_is_reported_as_action_wired_only(self) -> None:
        payload = build_self_repair_closure_inventory_payload(
            _status_contract(),
            signal_sources=DEFAULT_SIGNAL_SOURCES,
            planned_tools=DEFAULT_PLANNED_TOOLS,
            advisory_actions=DEFAULT_ADVISORY_ACTIONS,
            owned_root_routes=REQUIRED_OWNED_ROOT_ROUTES,
            executable_tools=[],
            executable_actions=[],
            evidence_paths=REQUIRED_EVIDENCE_PATHS,
            judgment_paths=REQUIRED_JUDGMENT_PATHS,
            closure_paths=REQUIRED_CLOSURE_PATHS,
            operator_outbox_paths=REQUIRED_OPERATOR_OUTBOX_PATHS,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["gap_count"], payload["root_count"])
        self.assertEqual(payload["depth_counts"], {"action_wired": payload["root_count"]})
        self.assertEqual(len(payload["missing_execution_roots"]), payload["root_count"])

    def test_borrowed_global_signal_without_owned_root_route_is_not_wired(self) -> None:
        payload = build_self_repair_closure_inventory_payload(
            _status_contract(),
            signal_sources=DEFAULT_SIGNAL_SOURCES,
            planned_tools=DEFAULT_PLANNED_TOOLS,
            advisory_actions=DEFAULT_ADVISORY_ACTIONS,
            executable_tools=DEFAULT_PLANNED_TOOLS,
            executable_actions=DEFAULT_ADVISORY_ACTIONS,
            evidence_paths=REQUIRED_EVIDENCE_PATHS,
            judgment_paths=REQUIRED_JUDGMENT_PATHS,
            closure_paths=REQUIRED_CLOSURE_PATHS,
            operator_outbox_paths=REQUIRED_OPERATOR_OUTBOX_PATHS,
            owned_root_routes=[],
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["depth_counts"], {"signal_borrowed": payload["root_count"]})
        self.assertEqual(len(payload["missing_owned_route_roots"]), payload["root_count"])

    def test_source_contract_reports_all_roots_have_direct_signal_routes(self) -> None:
        payload = build_self_repair_closure_inventory_payload(_status_contract())

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["source_contract_ready_count"], payload["root_count"])
        self.assertEqual(payload["gap_count"], 0)
        self.assertEqual(payload["gap_roots"], [])
        self.assertEqual(payload["depth_counts"], {"source_contract_ready": payload["root_count"]})

    def test_source_probe_finds_owned_root_signal_route(self) -> None:
        payload = build_source_wiring_probe_payload()

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["gap_count"], 0)
        self.assertIn("source_wiring_probe", payload["signal_sources"])
        self.assertIn("self_repair_closure_inventory", payload["owned_root_routes"])

    def test_source_probe_reports_missing_path_sets(self) -> None:
        payload = build_source_wiring_probe_payload()

        self.assertEqual(payload["missing_signal_sources"], [])
        self.assertEqual(payload["missing_planned_tools"], [])
        self.assertEqual(payload["missing_advisory_actions"], [])
        self.assertEqual(payload["planned_tools_without_execution"], [])
        self.assertEqual(payload["advisory_actions_without_execution"], [])
        self.assertEqual(payload["missing_required_evidence_paths"], [])
        self.assertEqual(payload["missing_required_judgment_paths"], [])
        self.assertEqual(payload["missing_required_closure_paths"], [])
        self.assertEqual(payload["missing_required_operator_outbox_paths"], [])
        self.assertEqual(payload["missing_required_owned_root_routes"], [])

    def test_source_probe_has_direct_signal_for_every_source_root(self) -> None:
        payload = build_source_wiring_probe_payload()
        missing = sorted(set(source_root_ids()) - set(payload["signal_sources"]))

        self.assertEqual(missing, [])

    def test_identity_profile_answers_is_declared_as_a_root_and_surface(self) -> None:
        self.assertIn("identity_profile_answers", source_root_ids())
        self.assertIn("identity_profile_answers", wiring_surface_ids())

    def test_model_runtime_declares_owned_signal_and_os_capability_route(self) -> None:
        surface = next(item for item in WIRING_SURFACES if item.surface_id == "model_runtime")

        self.assertEqual(surface.signal_sources, ("model_runtime",))
        self.assertIn("os_capability", surface.planned_tools)

        payload = build_source_wiring_probe_payload()
        self.assertIn("model_runtime", payload["signal_sources"])
        self.assertIn("os_capability", payload["planned_tools"])

    def test_runtime_search_and_scheduler_roots_do_not_borrow_control_status_signal_routes(self) -> None:
        by_id = {item.surface_id: item for item in WIRING_SURFACES}

        self.assertIn("runtime_core", by_id["runtime_core"].signal_sources)
        self.assertIn("web_search", by_id["web_search"].signal_sources)
        self.assertIn("scheduler_registry", by_id["scheduler_registry"].signal_sources)

        payload = build_source_wiring_probe_payload()
        for source in ("runtime_core", "web_search", "scheduler_registry"):
            self.assertIn(source, payload["signal_sources"])


if __name__ == "__main__":
    unittest.main()
