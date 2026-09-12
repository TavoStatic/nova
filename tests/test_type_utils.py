"""Unit tests for services.type_utils."""

from __future__ import annotations

import unittest

from services.type_utils import (
    _as_bool,
    _as_bool_or_none,
    _as_dict,
    _as_float,
    _as_int,
    _as_list,
    _text,
)


class TestTypeUtils(unittest.TestCase):
    def test_as_dict(self):
        self.assertEqual(_as_dict({"a": 1}), {"a": 1})
        self.assertEqual(_as_dict(None), {})
        self.assertEqual(_as_dict([1, 2, 3]), {})
        self.assertEqual(_as_dict("string"), {})

    def test_as_list(self):
        self.assertEqual(_as_list([1, 2]), [1, 2])
        self.assertEqual(_as_list(None), [])
        self.assertEqual(_as_list({"a": 1}), [])
        self.assertEqual(_as_list("string"), [])

    def test_as_int(self):
        self.assertEqual(_as_int(42), 42)
        self.assertEqual(_as_int("123"), 123)
        self.assertEqual(_as_int("invalid"), 0)
        self.assertEqual(_as_int(None, default=10), 10)
        self.assertEqual(_as_int("bad", default=-1), -1)

    def test_as_float(self):
        self.assertEqual(_as_float(3.14), 3.14)
        self.assertEqual(_as_float("2.718"), 2.718)
        self.assertEqual(_as_float("invalid"), 0.0)
        self.assertEqual(_as_float(None, default=1.5), 1.5)

    def test_as_bool(self):
        self.assertTrue(_as_bool(True))
        self.assertFalse(_as_bool(False))
        self.assertTrue(_as_bool("true"))
        self.assertTrue(_as_bool("YES"))
        self.assertTrue(_as_bool("1"))
        self.assertFalse(_as_bool("false"))
        self.assertFalse(_as_bool("0"))
        self.assertFalse(_as_bool(None))
        self.assertTrue(_as_bool(None, default=True))
        self.assertFalse(_as_bool("random"))

    def test_as_bool_or_none(self):
        self.assertTrue(_as_bool_or_none(True))
        self.assertFalse(_as_bool_or_none(False))
        self.assertIsNone(_as_bool_or_none(None))
        self.assertTrue(_as_bool_or_none("active"))
        self.assertFalse(_as_bool_or_none("off"))
        self.assertIsNone(_as_bool_or_none("unknown_value"))

    def test_text(self):
        self.assertEqual(_text("  hello  "), "hello")
        self.assertEqual(_text("hello world", limit=5), "hello")
        self.assertEqual(_text(None), "")
        self.assertEqual(_text(None, default="fallback"), "fallback")
        self.assertEqual(_text("", default="default_text"), "default_text")
        self.assertEqual(_text(12345, limit=3), "123")


if __name__ == "__main__":
    unittest.main()
