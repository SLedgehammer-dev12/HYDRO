from __future__ import annotations

import unittest

from hidrostatik_test.domain.coefficient_manager import (
    CoefficientManager,
    CoefficientState,
)


class CoefficientStateTests(unittest.TestCase):
    def test_is_usable_returns_true_for_computed(self) -> None:
        self.assertTrue(CoefficientState.COMPUTED.is_usable())

    def test_is_usable_returns_true_for_reference(self) -> None:
        self.assertTrue(CoefficientState.REFERENCE.is_usable())

    def test_is_usable_returns_true_for_manual(self) -> None:
        self.assertTrue(CoefficientState.MANUAL.is_usable())

    def test_is_usable_returns_false_for_empty(self) -> None:
        self.assertFalse(CoefficientState.EMPTY.is_usable())

    def test_is_usable_returns_false_for_stale(self) -> None:
        self.assertFalse(CoefficientState.STALE.is_usable())

    def test_is_auto_updateable_returns_true_for_computed(self) -> None:
        self.assertTrue(CoefficientState.COMPUTED.is_auto_updateable())

    def test_is_auto_updateable_returns_true_for_reference(self) -> None:
        self.assertTrue(CoefficientState.REFERENCE.is_auto_updateable())

    def test_is_auto_updateable_returns_false_for_empty(self) -> None:
        self.assertFalse(CoefficientState.EMPTY.is_auto_updateable())

    def test_is_auto_updateable_returns_false_for_manual(self) -> None:
        self.assertFalse(CoefficientState.MANUAL.is_auto_updateable())

    def test_is_auto_updateable_returns_false_for_stale(self) -> None:
        self.assertFalse(CoefficientState.STALE.is_auto_updateable())


class CoefficientManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = CoefficientManager()

    def test_initial_state_is_empty_for_all_keys(self) -> None:
        for key in self.manager.keys():
            self.assertEqual(self.manager.get(key), CoefficientState.EMPTY)

    def test_get_raises_key_error_for_unknown_key(self) -> None:
        with self.assertRaises(KeyError):
            self.manager.get("nonexistent")

    def test_set_and_get_roundtrip(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.assertEqual(self.manager.get("air_a"), CoefficientState.COMPUTED)

    def test_keys_returns_expected_tuple(self) -> None:
        self.assertEqual(self.manager.keys(), ("air_a", "pressure_a", "pressure_b"))

    def test_is_ready_returns_true_when_state_is_usable(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.assertTrue(self.manager.is_ready("air_a"))

    def test_is_ready_returns_false_when_empty(self) -> None:
        self.assertFalse(self.manager.is_ready("air_a"))

    def test_is_ready_returns_false_for_stale(self) -> None:
        self.manager.set("air_a", CoefficientState.STALE)
        self.assertFalse(self.manager.is_ready("air_a"))

    def test_mark_dependencies_changed_sets_stale_on_computed(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.manager.mark_dependencies_changed(("air_a",))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.STALE)

    def test_mark_dependencies_changed_sets_stale_on_reference(self) -> None:
        self.manager.set("air_a", CoefficientState.REFERENCE)
        self.manager.mark_dependencies_changed(("air_a",))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.STALE)

    def test_mark_dependencies_changed_ignores_empty(self) -> None:
        self.manager.mark_dependencies_changed(("air_a",))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.EMPTY)

    def test_mark_dependencies_changed_ignores_manual(self) -> None:
        self.manager.set("air_a", CoefficientState.MANUAL)
        self.manager.mark_dependencies_changed(("air_a",))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.MANUAL)

    def test_mark_dependencies_changed_ignores_stale(self) -> None:
        self.manager.set("air_a", CoefficientState.STALE)
        self.manager.mark_dependencies_changed(("air_a",))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.STALE)

    def test_mark_dependencies_changed_handles_multiple_keys(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.manager.set("pressure_a", CoefficientState.COMPUTED)
        self.manager.set("pressure_b", CoefficientState.MANUAL)
        self.manager.mark_dependencies_changed(("air_a", "pressure_a", "pressure_b"))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.STALE)
        self.assertEqual(self.manager.get("pressure_a"), CoefficientState.STALE)
        self.assertEqual(self.manager.get("pressure_b"), CoefficientState.MANUAL)

    def test_reset_without_args_clears_all_keys(self) -> None:
        for key in self.manager.keys():
            self.manager.set(key, CoefficientState.COMPUTED)
        self.manager.reset()
        for key in self.manager.keys():
            self.assertEqual(self.manager.get(key), CoefficientState.EMPTY)

    def test_reset_with_specific_keys_only(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.manager.set("pressure_a", CoefficientState.COMPUTED)
        self.manager.set("pressure_b", CoefficientState.COMPUTED)
        self.manager.reset(keys=("air_a", "pressure_b"))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.EMPTY)
        self.assertEqual(self.manager.get("pressure_a"), CoefficientState.COMPUTED)
        self.assertEqual(self.manager.get("pressure_b"), CoefficientState.EMPTY)

    def test_reset_ignores_unknown_keys(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.manager.reset(keys=("air_a", "nonexistent"))
        self.assertEqual(self.manager.get("air_a"), CoefficientState.EMPTY)

    def test_as_dict_returns_string_values(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        expected = {
            "air_a": "computed",
            "pressure_a": "empty",
            "pressure_b": "empty",
        }
        self.assertEqual(self.manager.as_dict(), expected)

    def test_from_dict_restores_valid_states(self) -> None:
        data = {
            "air_a": "computed",
            "pressure_a": "reference",
            "pressure_b": "manual",
        }
        manager = CoefficientManager.from_dict(data)
        self.assertEqual(manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertEqual(manager.get("pressure_a"), CoefficientState.REFERENCE)
        self.assertEqual(manager.get("pressure_b"), CoefficientState.MANUAL)

    def test_from_dict_handles_invalid_value_as_empty(self) -> None:
        data = {"air_a": "invalid_state"}
        manager = CoefficientManager.from_dict(data)
        self.assertEqual(manager.get("air_a"), CoefficientState.EMPTY)

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"air_a": "computed", "unknown_key": "manual"}
        manager = CoefficientManager.from_dict(data)
        self.assertEqual(manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertEqual(manager.keys(), ("air_a", "pressure_a", "pressure_b"))

    def test_as_dict_from_dict_roundtrip(self) -> None:
        self.manager.set("air_a", CoefficientState.COMPUTED)
        self.manager.set("pressure_b", CoefficientState.STALE)
        serialized = self.manager.as_dict()
        restored = CoefficientManager.from_dict(serialized)
        for key in self.manager.keys():
            self.assertEqual(restored.get(key), self.manager.get(key))


if __name__ == "__main__":
    unittest.main()
