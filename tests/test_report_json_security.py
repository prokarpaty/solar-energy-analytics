import json
import sys
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

import report_validation as rv


def strict_load(payload):

    rv.validate_json_depth(payload)

    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=rv.reject_duplicate_keys,
        parse_int=rv.parse_json_integer,
        parse_float=rv.parse_json_float,
        parse_constant=rv.reject_constant
    )


class ReportJSONSecurityTests(unittest.TestCase):

    def test_valid_integer(self):
        self.assertEqual(strict_load(b"123"), 123)

    def test_valid_negative_number(self):
        self.assertEqual(strict_load(b"-25.7"), -25.7)

    def test_valid_scientific_notation(self):
        self.assertEqual(strict_load(b"1.25e3"), 1250)

    def test_valid_null(self):
        self.assertIsNone(strict_load(b"null"))

    def test_valid_unicode(self):
        self.assertEqual(
            strict_load('"Україна"'.encode("utf-8")),
            "Україна"
        )

    def test_valid_escaped_backslash(self):
        payload = json.dumps(
            {"text": "test\\path"}
        ).encode()

        self.assertEqual(
            strict_load(payload)["text"],
            "test\\path"
        )

    def test_duplicate_root_keys(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b'{"a":1,"a":2}')

    def test_duplicate_nested_keys(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b'{"a":{"b":1,"b":2}}')

    def test_nan_rejected(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"NaN")

    def test_infinity_rejected(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"Infinity")

    def test_negative_infinity_rejected(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"-Infinity")

    def test_positive_exponent_overflow(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"1e999")

    def test_negative_exponent_overflow(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"-1e999")

    def test_oversized_integer_token(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(
                b"9" * (rv.MAX_INTEGER_TOKEN_LENGTH + 1)
            )

    def test_oversized_float_token(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(
                b"0." + b"1" * rv.MAX_FLOAT_TOKEN_LENGTH
            )

    def test_excessive_positive_magnitude(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"1e16")

    def test_excessive_negative_magnitude(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"-1e16")

    def test_unclosed_object(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b'{"a":1')

    def test_unclosed_string(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b'{"a":"unfinished}')

    def test_unexpected_closing_bracket(self):
        with self.assertRaises(rv.ReportValidationError):
            strict_load(b"]")

    def test_mismatched_brackets(self):
        with self.assertRaises(ValueError):
            strict_load(b"[}")

    def test_excessive_object_members(self):

        payload = json.dumps({
            str(i): i
            for i in range(rv.MAX_OBJECT_MEMBERS + 1)
        }).encode()

        with self.assertRaises(rv.ReportValidationError):
            strict_load(payload)

    def test_object_member_boundary(self):

        payload = json.dumps({
            str(i): i
            for i in range(rv.MAX_OBJECT_MEMBERS)
        }).encode()

        self.assertEqual(
            len(strict_load(payload)),
            rv.MAX_OBJECT_MEMBERS
        )

    def test_excessive_containers(self):

        with patch.object(rv, "MAX_JSON_CONTAINERS", 5):

            with self.assertRaises(rv.ReportValidationError):
                strict_load(b"[{},{},{},{},{}]")

    def test_excessive_separators(self):

        with patch.object(rv, "MAX_JSON_SEPARATORS", 10):

            with self.assertRaises(rv.ReportValidationError):
                strict_load(b"[" + b"0," * 11 + b"0]")

    def test_excessive_nesting(self):

        depth = rv.MAX_JSON_DEPTH + 1

        with self.assertRaises(rv.ReportValidationError):
            strict_load(
                b"[" * depth + b"0" + b"]" * depth
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
