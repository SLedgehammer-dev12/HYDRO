from __future__ import annotations

import unittest

from hidrostatik_test.config import FIELD_CHECK_DEFINITIONS


class FieldCheckDefinitionsTests(unittest.TestCase):
    def test_is_non_empty_tuple(self) -> None:
        self.assertIsInstance(FIELD_CHECK_DEFINITIONS, tuple)
        self.assertGreater(len(FIELD_CHECK_DEFINITIONS), 0)

    def test_each_entry_is_three_tuple(self) -> None:
        for entry in FIELD_CHECK_DEFINITIONS:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, tuple)
                self.assertEqual(len(entry), 3)

    def test_each_entry_has_string_key_label_reference(self) -> None:
        for entry in FIELD_CHECK_DEFINITIONS:
            with self.subTest(entry=entry):
                key, label, reference = entry
                self.assertIsInstance(key, str)
                self.assertIsInstance(label, str)
                self.assertIsInstance(reference, str)

    def test_keys_are_unique(self) -> None:
        keys = [key for key, _label, _reference in FIELD_CHECK_DEFINITIONS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_first_entry_matches_expected_values(self) -> None:
        key, label, reference = FIELD_CHECK_DEFINITIONS[0]
        self.assertEqual(key, "ambient_temp")
        self.assertIn("hava sicakligi", label)
        self.assertEqual(reference, "10.1")

    def test_last_entry_matches_expected_values(self) -> None:
        key, label, reference = FIELD_CHECK_DEFINITIONS[-1]
        self.assertEqual(key, "depressurize_discharge")
        self.assertIn("Basinc dusurme", label)
        self.assertEqual(reference, "16-17")

    def test_all_references_are_strings(self) -> None:
        for _key, _label, reference in FIELD_CHECK_DEFINITIONS:
            with self.subTest(reference=reference):
                self.assertIsInstance(reference, str)
                self.assertGreater(len(reference), 0)


if __name__ == "__main__":
    unittest.main()
