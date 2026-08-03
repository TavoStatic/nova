from __future__ import annotations

import unittest

from services.edfi.present import (
    format_lea_display,
    present_operation_result,
    shape_school_row,
)


class TestEdFiPresent(unittest.TestCase):
    def test_lea_display_zero_pads(self) -> None:
        self.assertEqual(format_lea_display("31901"), "031901")
        self.assertEqual(format_lea_display("031901"), "031901")

    def test_shape_school_row(self) -> None:
        raw = {
            "schoolId": 31901001,
            "nameOfInstitution": "Example High",
            "localEducationAgencyReference": {"localEducationAgencyId": 31901},
            "schoolTypeDescriptor": "uri://ed-fi.org/SchoolTypeDescriptor#High School",
            "operationalStatusDescriptor": "uri://ed-fi.org/OperationalStatusDescriptor#Active",
            "gradeLevels": [
                {"gradeLevelDescriptor": "uri://ed-fi.org/GradeLevelDescriptor#Ninth grade"},
                {"gradeLevelDescriptor": "uri://ed-fi.org/GradeLevelDescriptor#Tenth grade"},
            ],
        }
        row = shape_school_row(raw)
        self.assertEqual(row["school_name"], "Example High")
        self.assertEqual(row["lea_id"], "031901")
        self.assertEqual(row["school_type"], "High School")
        self.assertIn("Ninth grade", row["grade_levels"])

    def test_present_list_schools(self) -> None:
        raw = {
            "ok": True,
            "items": [
                {
                    "schoolId": 1,
                    "nameOfInstitution": "Alpha",
                    "localEducationAgencyReference": {"localEducationAgencyId": 31901},
                },
                {
                    "schoolId": 2,
                    "nameOfInstitution": "Beta",
                    "localEducationAgencyReference": {"localEducationAgencyId": 31901},
                },
            ],
        }
        presented = present_operation_result("list_schools", raw)
        self.assertTrue(presented["reader_friendly"])
        self.assertEqual(presented["report_intent"], "schools_directory")
        self.assertEqual(presented["row_count"], 2)
        self.assertIn("school_name", presented["columns"])
        self.assertEqual(presented["rows"][0]["school_name"], "Alpha")
        self.assertIn("2 school", presented["summary"])

    def test_present_health(self) -> None:
        raw = {
            "ok": True,
            "connection_id": "district-main",
            "health": "ok",
            "district_lea_id": "31901",
            "resource_count": 445,
            "auth_ok": True,
        }
        presented = present_operation_result("connection_health", raw)
        self.assertEqual(presented["rows"][0]["lea_id"], "031901")
        self.assertIn("health=ok", presented["summary"])


if __name__ == "__main__":
    unittest.main()
