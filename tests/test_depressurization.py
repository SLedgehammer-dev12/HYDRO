from __future__ import annotations

import unittest

from hidrostatik_test.domain.depressurization import (
    MIN_HOLD_MINUTES,
    DepressurizationStage,
    DepressurizationInputs,
    evaluate_depressurization,
)
from hidrostatik_test.domain.hydrotest_core import ValidationError


class DepressurizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stages = (
            DepressurizationStage(
                stage_label="1. Kademe",
                start_pressure_bar=80.0,
                end_pressure_bar=50.0,
                hold_minutes=15.0,
            ),
            DepressurizationStage(
                stage_label="2. Kademe",
                start_pressure_bar=50.0,
                end_pressure_bar=20.0,
                hold_minutes=15.0,
            ),
            DepressurizationStage(
                stage_label="3. Kademe",
                start_pressure_bar=20.0,
                end_pressure_bar=0.0,
                hold_minutes=15.0,
            ),
        )
        self.inputs = DepressurizationInputs(
            stages=self.stages,
            initial_pressure_bar=80.0,
        )

    def test_valid_depressurization_passes(self) -> None:
        result = evaluate_depressurization(self.inputs)
        self.assertEqual(result.total_stages, 3)
        self.assertTrue(result.gradual_reduction)
        self.assertTrue(result.all_holds_sufficient)
        self.assertTrue(result.full_depressurization)
        self.assertTrue(result.passed)

    def test_non_gradual_first_stage_start_below_initial_fails(self) -> None:
        stages = (
            DepressurizationStage(
                stage_label="1. Kademe",
                start_pressure_bar=60.0,
                end_pressure_bar=50.0,
                hold_minutes=15.0,
            ),
        )
        inputs = DepressurizationInputs(stages=stages, initial_pressure_bar=80.0)
        result = evaluate_depressurization(inputs)
        self.assertFalse(result.gradual_reduction)
        self.assertFalse(result.passed)

    def test_non_gradual_pressure_increase_fails(self) -> None:
        stages = (
            DepressurizationStage(
                stage_label="1. Kademe",
                start_pressure_bar=80.0,
                end_pressure_bar=85.0,
                hold_minutes=15.0,
            ),
        )
        inputs = DepressurizationInputs(stages=stages, initial_pressure_bar=80.0)
        result = evaluate_depressurization(inputs)
        self.assertFalse(result.gradual_reduction)
        self.assertFalse(result.passed)

    def test_insufficient_hold_time_fails(self) -> None:
        stages = (
            DepressurizationStage(
                stage_label="1. Kademe",
                start_pressure_bar=80.0,
                end_pressure_bar=50.0,
                hold_minutes=1.0,
            ),
            DepressurizationStage(
                stage_label="2. Kademe",
                start_pressure_bar=50.0,
                end_pressure_bar=0.0,
                hold_minutes=15.0,
            ),
        )
        inputs = DepressurizationInputs(stages=stages, initial_pressure_bar=80.0)
        result = evaluate_depressurization(inputs)
        self.assertFalse(result.all_holds_sufficient)
        self.assertFalse(result.passed)

    def test_incomplete_depressurization_fails(self) -> None:
        stages = (
            DepressurizationStage(
                stage_label="1. Kademe",
                start_pressure_bar=80.0,
                end_pressure_bar=50.0,
                hold_minutes=15.0,
            ),
        )
        inputs = DepressurizationInputs(stages=stages, initial_pressure_bar=80.0)
        result = evaluate_depressurization(inputs)
        self.assertFalse(result.full_depressurization)
        self.assertFalse(result.passed)

    def test_single_stage_to_zero_with_sufficient_hold_passes(self) -> None:
        stages = (
            DepressurizationStage(
                stage_label="Tek Kademe",
                start_pressure_bar=80.0,
                end_pressure_bar=0.0,
                hold_minutes=10.0,
            ),
        )
        inputs = DepressurizationInputs(stages=stages, initial_pressure_bar=80.0)
        result = evaluate_depressurization(inputs)
        self.assertTrue(result.gradual_reduction)
        self.assertTrue(result.all_holds_sufficient)
        self.assertTrue(result.full_depressurization)
        self.assertTrue(result.passed)

    def test_initial_pressure_zero_raises(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationInputs(
                stages=(
                    DepressurizationStage(
                        stage_label="1. Kademe",
                        start_pressure_bar=0.0,
                        end_pressure_bar=0.0,
                        hold_minutes=5.0,
                    ),
                ),
                initial_pressure_bar=0.0,
            )

    def test_empty_stages_raises(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationInputs(stages=(), initial_pressure_bar=80.0)

    def test_negative_start_pressure_in_stage_raises(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationStage(
                stage_label="Hatali",
                start_pressure_bar=-1.0,
                end_pressure_bar=0.0,
                hold_minutes=5.0,
            )

    def test_negative_end_pressure_in_stage_raises(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationStage(
                stage_label="Hatali",
                start_pressure_bar=0.0,
                end_pressure_bar=-1.0,
                hold_minutes=5.0,
            )

    def test_negative_hold_time_raises(self) -> None:
        with self.assertRaises(ValidationError):
            DepressurizationStage(
                stage_label="Hatali",
                start_pressure_bar=80.0,
                end_pressure_bar=0.0,
                hold_minutes=-1.0,
            )
