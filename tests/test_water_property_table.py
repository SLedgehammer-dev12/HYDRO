from __future__ import annotations

import tempfile
import unittest
from math import isclose
from pathlib import Path

from hidrostatik_test.data import (
    WaterPropertyTableAxis,
    WaterPropertyTableSpec,
    default_water_property_table_spec,
    load_water_property_table,
)
from hidrostatik_test.domain import (
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
)
from hidrostatik_test.services.water_property_table_builder import (
    generate_water_property_table_rows,
    write_water_property_table,
)


class FakeGridBackend:
    class Info:
        key = "fake-grid"
        label = "Fake Grid"

    info = Info()

    def calculate_water_compressibility_a(self, temp_c: float, pressure_bar: float) -> float:
        return temp_c + (pressure_bar * 100.0)

    def calculate_water_thermal_expansion_beta(self, temp_c: float, pressure_bar: float) -> float:
        return (temp_c * 10.0) + pressure_bar


class WaterPropertyTableBuilderTests(unittest.TestCase):
    def test_small_grid_can_be_generated_and_reloaded(self) -> None:
        spec = WaterPropertyTableSpec(
            schema_version=1,
            table_key="test-grid",
            interpolation_method="bilinear",
            temperature_axis=WaterPropertyTableAxis(
                key="temp_c",
                unit="degC",
                minimum=0.0,
                maximum=1.0,
                step=1.0,
                count=2,
            ),
            pressure_axis=WaterPropertyTableAxis(
                key="pressure_bar",
                unit="bar",
                minimum=1.0,
                maximum=2.0,
                step=1.0,
                count=2,
            ),
            csv_columns=("temp_c", "pressure_bar", "a_micro_per_bar", "water_beta_micro_per_c"),
            a_unit="10^-6 / bar",
            beta_unit="10^-6 / degC",
        )

        rows = generate_water_property_table_rows(spec=spec, backend=FakeGridBackend())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "grid.csv"
            metadata_path = temp_path / "grid.meta.json"
            write_water_property_table(
                rows=rows,
                spec=spec,
                backend=FakeGridBackend(),
                csv_path=csv_path,
                metadata_path=metadata_path,
            )

            grid = load_water_property_table(csv_path=csv_path, metadata_path=metadata_path)

        self.assertEqual(grid.row_count, 4)
        self.assertEqual(grid.source_backend_key, "fake-grid")
        self.assertTrue(isclose(grid.a_grid[0][0], 100.0, rel_tol=1e-12))
        self.assertTrue(isclose(grid.beta_grid[1][1], 12.0, rel_tol=1e-12))


class DefaultWaterPropertyTableTests(unittest.TestCase):
    def test_default_spec_matches_requested_initial_range(self) -> None:
        spec = default_water_property_table_spec()

        self.assertTrue(isclose(spec.temperature_axis.minimum, 0.0, rel_tol=1e-12))
        self.assertTrue(isclose(spec.temperature_axis.maximum, 40.0, rel_tol=1e-12))
        self.assertEqual(spec.temperature_axis.count, 41)
        self.assertTrue(isclose(spec.pressure_axis.minimum, 1.0, rel_tol=1e-12))
        self.assertTrue(isclose(spec.pressure_axis.maximum, 150.0, rel_tol=1e-12))
        self.assertEqual(spec.pressure_axis.count, 150)

    def test_table_backend_matches_exact_grid_nodes(self) -> None:
        a_value = calculate_water_compressibility_a(10.0, 50.0, backend="table_v1")
        beta_value = calculate_water_thermal_expansion_beta(10.0, 50.0, backend="table_v1")

        self.assertTrue(isclose(a_value, calculate_water_compressibility_a(10.0, 50.0), rel_tol=1e-9))
        self.assertTrue(
            isclose(
                beta_value,
                calculate_water_thermal_expansion_beta(10.0, 50.0),
                rel_tol=1e-9,
            )
        )

    def test_table_backend_interpolates_off_grid_close_to_coolprop(self) -> None:
        a_table = calculate_water_compressibility_a(12.5, 73.4, backend="table_v1")
        beta_table = calculate_water_thermal_expansion_beta(12.5, 73.4, backend="table_v1")
        a_direct = calculate_water_compressibility_a(12.5, 73.4, backend="coolprop")
        beta_direct = calculate_water_thermal_expansion_beta(12.5, 73.4, backend="coolprop")

        self.assertTrue(isclose(a_table, a_direct, rel_tol=5e-4))
        self.assertTrue(isclose(beta_table, beta_direct, rel_tol=5e-4))


if __name__ == "__main__":
    unittest.main()
