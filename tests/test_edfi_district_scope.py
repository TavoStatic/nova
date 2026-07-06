from __future__ import annotations

import unittest

from services.edfi.district_scope import (
    district_lea_filter_clause,
    item_matches_district,
    merge_filter_params,
    normalize_district_lea_id,
    uses_client_side_district_filter,
)


class TestEdFiDistrictScope(unittest.TestCase):
    def test_normalize_accepts_numeric_strings(self) -> None:
        self.assertEqual(normalize_district_lea_id("31901"), 31901)
        self.assertEqual(normalize_district_lea_id("031901"), 31901)
        self.assertIsNone(normalize_district_lea_id(""))

    def test_school_filter_uses_lea_reference(self) -> None:
        clause = district_lea_filter_clause("ed-fi/schools", "31901")
        self.assertEqual(clause, "localEducationAgencyReference/localEducationAgencyId eq 31901")

    def test_lea_resource_filters_direct_id(self) -> None:
        clause = district_lea_filter_clause("ed-fi/localEducationAgencies", 31901)
        self.assertEqual(clause, "localEducationAgencyId eq 31901")

    def test_tea_uses_client_side_filter(self) -> None:
        self.assertTrue(
            uses_client_side_district_filter("https://odsprod.tea.texas.gov/odsedfiapi2026")
        )

    def test_item_matches_district_by_lea_reference(self) -> None:
        item = {
            "schoolId": 99999001,
            "localEducationAgencyReference": {"localEducationAgencyId": 31901},
        }
        self.assertTrue(item_matches_district(item, 31901))
        self.assertFalse(item_matches_district(item, 1902))

    def test_item_matches_district_by_school_id_prefix(self) -> None:
        item = {"schoolId": 31901001, "nameOfInstitution": "Hanna Early College High School"}
        self.assertTrue(item_matches_district(item, 31901))

    def test_merge_filter_params_combines_clauses(self) -> None:
        merged = merge_filter_params(
            {"$filter": "name eq 'Main'"},
            "localEducationAgencyReference/localEducationAgencyId eq 31901",
        )
        self.assertEqual(
            merged["$filter"],
            "(name eq 'Main') and (localEducationAgencyReference/localEducationAgencyId eq 31901)",
        )


if __name__ == "__main__":
    unittest.main()