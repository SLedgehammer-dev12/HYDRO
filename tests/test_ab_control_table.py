from __future__ import annotations

import csv
import json
import tempfile
import unittest
from math import isclose
from pathlib import Path

from hidrostatik_test.data import (
    DEFAULT_CONTROL_TABLE_CSV_PATH,
    DEFAULT_CONTROL_TABLE_METADATA_PATH,
    ABControlTableError,
    count_repaired_ab_control_points,
    describe_ab_control_table_range,
    lookup_ab_control_point,
)
from hidrostatik_test.data.ab_control_table import (
    ABControlTableValidationError,
    _load_ab_control_repair_grid,
    clear_ab_control_table_cache,
    find_ab_control_table_issues,
    load_ab_control_table,
)

_CSV_COLUMNS = ("temp_c", "pressure_bar", "a_micro_per_bar", "b_micro_per_c")


def _write_temp_table(
    directory: str,
    rows: list[tuple[float, float, float, float]],
    *,
    temperature_points: tuple[float, ...] = (1.0, 2.0),
    pressure_points: tuple[float, ...] = (30.0, 31.0),
) -> tuple[Path, Path]:
    root = Path(directory)
    csv_path = root / "table.csv"
    metadata_path = root / "table.meta.json"
    metadata = {
        "schema_version": 1,
        "table_key": "test_table",
        "interpolation_method": "bilinear",
        "temperature_axis": {
            "key": "temp_c",
            "unit": "degC",
            "minimum": temperature_points[0],
            "maximum": temperature_points[-1],
            "step": 1.0,
            "count": len(temperature_points),
        },
        "pressure_axis": {
            "key": "pressure_bar",
            "unit": "bar",
            "minimum": pressure_points[0],
            "maximum": pressure_points[-1],
            "step": 1.0,
            "count": len(pressure_points),
        },
        "csv_columns": list(_CSV_COLUMNS),
        "a_unit": "10^-6 / bar",
        "b_unit": "10^-6 / degC",
        "source_name": "test",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "row_count": len(rows),
        "notes": [],
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_COLUMNS)
        writer.writerows(rows)
    return csv_path, metadata_path


class ABControlTableTests(unittest.TestCase):
    def test_range_description_matches_imported_excel_grid(self) -> None:
        self.assertEqual(describe_ab_control_table_range(), "T=1-25 degC ve P=30-120 bar")

    def test_exact_grid_node_matches_imported_workbook_value(self) -> None:
        point = lookup_ab_control_point(temp_c=10.0, pressure_bar=30.0)

        self.assertTrue(isclose(point.a_micro_per_bar, 46.99, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, 60.316, rel_tol=1e-12))
        self.assertIn("exact grid", point.source_note)

    def test_midpoint_uses_bilinear_interpolation(self) -> None:
        point = lookup_ab_control_point(temp_c=1.5, pressure_bar=30.5)

        expected_a = (49.54 + 49.205 + 49.53 + 49.195) / 4.0
        expected_b = (-84.373 - 66.032 - 84.0311 - 65.704) / 4.0
        self.assertTrue(isclose(point.a_micro_per_bar, expected_a, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, expected_b, rel_tol=1e-12))
        self.assertIn("bilinear interpolation", point.source_note)

    def test_out_of_range_lookup_raises_error(self) -> None:
        with self.assertRaises(ABControlTableError):
            lookup_ab_control_point(temp_c=26.0, pressure_bar=30.0)

    def test_default_load_keeps_permissive_behaviour(self) -> None:
        grid = load_ab_control_table()

        self.assertEqual(grid.row_count, 2275)
        self.assertEqual(len(grid.temperature_points), 25)
        self.assertEqual(len(grid.pressure_points), 91)

    def test_known_seven_degree_anomaly_is_reported(self) -> None:
        issues = find_ab_control_table_issues()

        raw_point = lookup_ab_control_point(temp_c=7.0, pressure_bar=90.0, repair_anomalies=False)
        self.assertTrue(
            isclose(raw_point.a_micro_per_bar, 45.515, rel_tol=1e-12),
            "Anomali sessizce duzeltilmemeli; ham workbook degeri korunmali",
        )
        self.assertFalse(raw_point.repaired)
        self.assertEqual(raw_point.repair_note, "")

        row_issues = [
            issue for issue in issues if issue.kind == "a_monotonicity" and issue.temp_c == 7.0
        ]
        self.assertTrue(row_issues, "T=7 satirindaki A monotonluk ihlali raporlanmali")
        self.assertTrue(
            any(
                90.0 <= issue.pressure_bar <= 98.0
                for issue in row_issues
                if issue.pressure_bar is not None
            ),
            "Anomali 90-98 bar araliginda gorunmeli",
        )
        self.assertTrue(
            any(
                issue.previous_value is not None and 45.0 < issue.previous_value < 46.0
                for issue in row_issues
            ),
            "Anomali A ~45.5 degerine dususu yakalamali",
        )

        step_issues = [issue for issue in issues if issue.kind == "a_step" and issue.temp_c == 7.0]
        self.assertTrue(step_issues, "T=7 satirindaki ani A sicramasi raporlanmali")
        self.assertTrue(
            any(
                issue.pressure_bar == 81.0
                and issue.value is not None
                and issue.previous_value is not None
                and abs(issue.value - issue.previous_value) > 0.1
                for issue in step_issues
            ),
            "80->81 bar gecisindeki ~0.17 A sicramasi raporlanmali",
        )

        column_issues = [
            issue
            for issue in issues
            if issue.kind == "a_temperature_monotonicity" and issue.pressure_bar is not None
        ]
        self.assertTrue(
            any(82.0 <= issue.pressure_bar <= 98.0 for issue in column_issues),
            "7->8 degC kolon karsilastirmasi anomalinin basinc araligini gostermeli",
        )

    def test_seven_degree_anomaly_is_repaired_at_runtime(self) -> None:
        repaired_point = lookup_ab_control_point(temp_c=7.0, pressure_bar=90.0)

        self.assertTrue(repaired_point.repaired)
        self.assertTrue(isclose(repaired_point.a_micro_per_bar, 47.115047619047616, rel_tol=1e-12))
        self.assertGreater(repaired_point.a_micro_per_bar, 47.0)
        self.assertLess(repaired_point.a_micro_per_bar, 47.2)
        # B must stay the untouched workbook value.
        self.assertTrue(isclose(repaired_point.b_micro_per_c, 32.663, rel_tol=1e-12))
        self.assertIn("onarilmis", repaired_point.source_note)
        self.assertIn("45.515000", repaired_point.source_note)
        self.assertIn("onarilmis", repaired_point.repair_note)
        self.assertIn("45.515000", repaired_point.repair_note)

    def test_repair_count_and_grid_mask_cover_only_the_seven_degree_row(self) -> None:
        clear_ab_control_table_cache()
        self.assertEqual(count_repaired_ab_control_points(), 20)

        grid = load_ab_control_table()
        repair_grid = _load_ab_control_repair_grid(
            DEFAULT_CONTROL_TABLE_CSV_PATH, DEFAULT_CONTROL_TABLE_METADATA_PATH
        )

        repaired_cells = [
            (grid.temperature_points[t_index], grid.pressure_points[p_index])
            for t_index, row in enumerate(repair_grid.repaired_mask)
            for p_index, is_repaired in enumerate(row)
            if is_repaired
        ]
        self.assertEqual(len(repaired_cells), 20)
        self.assertEqual({temp_c for temp_c, _ in repaired_cells}, {7.0})
        self.assertEqual(
            {pressure_bar for _, pressure_bar in repaired_cells},
            {float(pressure) for pressure in range(81, 101)},
        )
        # Healthy A cells and every B cell are untouched.
        for t_index, row in enumerate(repair_grid.repaired_mask):
            for p_index, is_repaired in enumerate(row):
                if is_repaired:
                    continue
                self.assertEqual(
                    repair_grid.a_grid[t_index][p_index],
                    grid.a_grid[t_index][p_index],
                )
        self.assertEqual(repair_grid.a_grid[6][60], 47.115047619047616)

    def test_runtime_repair_keeps_healthy_lookups_unchanged(self) -> None:
        for temp_c, pressure_bar in ((10.0, 50.0), (1.0, 30.0), (1.5, 30.5), (25.0, 120.0)):
            with self.subTest(temp_c=temp_c, pressure_bar=pressure_bar):
                raw = lookup_ab_control_point(
                    temp_c=temp_c, pressure_bar=pressure_bar, repair_anomalies=False
                )
                repaired = lookup_ab_control_point(
                    temp_c=temp_c, pressure_bar=pressure_bar, repair_anomalies=True
                )
                self.assertFalse(repaired.repaired)
                self.assertEqual(raw.a_micro_per_bar, repaired.a_micro_per_bar)
                self.assertEqual(raw.b_micro_per_c, repaired.b_micro_per_c)

    def test_validate_flag_raises_with_attached_issues(self) -> None:
        clear_ab_control_table_cache()

        with self.assertRaises(ABControlTableValidationError) as context:
            load_ab_control_table(validate=True)

        self.assertTrue(any(issue.temp_c == 7.0 for issue in context.exception.issues))
        clear_ab_control_table_cache()

    def test_quality_check_accepts_clean_small_table(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 49.48, -83.5),
            (2.0, 30.0, 49.00, -70.0),
            (2.0, 31.0, 48.98, -69.5),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(directory, rows)

            self.assertEqual(find_ab_control_table_issues(csv_path, metadata_path), [])
            grid = load_ab_control_table(
                csv_path=csv_path, metadata_path=metadata_path, validate=True
            )
            self.assertEqual(grid.row_count, 4)

    def test_missing_grid_node_is_reported(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 49.48, -83.5),
            (2.0, 30.0, 49.00, -70.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(directory, rows)

            issues = find_ab_control_table_issues(csv_path, metadata_path)

        missing = [issue for issue in issues if issue.kind == "missing_point"]
        self.assertEqual(len(missing), 1)
        self.assertEqual((missing[0].temp_c, missing[0].pressure_bar), (2.0, 31.0))

    def test_duplicate_grid_node_is_reported(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 49.48, -83.5),
            (2.0, 30.0, 49.00, -70.0),
            (2.0, 31.0, 48.98, -69.5),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(directory, rows)

            issues = find_ab_control_table_issues(csv_path, metadata_path)

        self.assertTrue(any(issue.kind == "duplicate_point" for issue in issues))

    def test_out_of_range_node_is_reported(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 49.48, -83.5),
            (2.0, 30.0, 49.00, -70.0),
            (2.0, 31.0, 48.98, -69.5),
            (3.0, 30.0, 48.50, -60.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(directory, rows)

            issues = find_ab_control_table_issues(csv_path, metadata_path)

        self.assertTrue(
            any(issue.kind == "out_of_range_point" and issue.temp_c == 3.0 for issue in issues)
        )

    def test_excessive_adjacent_jump_is_reported(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 45.00, -83.5),
            (2.0, 30.0, 49.00, -70.0),
            (2.0, 31.0, 48.98, -69.5),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(directory, rows)

            issues = find_ab_control_table_issues(csv_path, metadata_path)

        step = [issue for issue in issues if issue.kind == "a_step"]
        self.assertEqual(len(step), 1)
        self.assertEqual((step[0].temp_c, step[0].pressure_bar), (1.0, 31.0))

    def test_small_table_anomaly_is_repaired_by_row_interpolation(self) -> None:
        rows = [
            (1.0, 30.0, 49.50, -84.0),
            (1.0, 31.0, 49.46, -83.5),
            (1.0, 32.0, 47.00, -83.0),
            (1.0, 33.0, 49.44, -82.5),
            (1.0, 34.0, 49.40, -82.0),
            (2.0, 30.0, 49.20, -74.0),
            (2.0, 31.0, 49.16, -73.5),
            (2.0, 32.0, 46.70, -73.0),
            (2.0, 33.0, 49.14, -72.5),
            (2.0, 34.0, 49.10, -72.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = _write_temp_table(
                directory,
                rows,
                pressure_points=(30.0, 31.0, 32.0, 33.0, 34.0),
            )

            self.assertEqual(count_repaired_ab_control_points(csv_path, metadata_path), 4)

            raw_point = lookup_ab_control_point(
                1.0, 32.0, csv_path=csv_path, metadata_path=metadata_path, repair_anomalies=False
            )
            repaired_point = lookup_ab_control_point(
                1.0, 32.0, csv_path=csv_path, metadata_path=metadata_path
            )
            repaired_neighbour = lookup_ab_control_point(
                1.0, 34.0, csv_path=csv_path, metadata_path=metadata_path
            )

        self.assertEqual(raw_point.a_micro_per_bar, 47.00)
        self.assertFalse(raw_point.repaired)
        self.assertTrue(repaired_point.repaired)
        self.assertFalse(repaired_neighbour.repaired, "Onarim araligi disindaki komsu ham kalmali")
        self.assertTrue(isclose(repaired_point.a_micro_per_bar, 49.44, rel_tol=1e-12))
        self.assertEqual(repaired_neighbour.a_micro_per_bar, 49.40)
        self.assertEqual(repaired_point.b_micro_per_c, -83.0)
        self.assertIn("onarilmis", repaired_point.repair_note)


if __name__ == "__main__":
    unittest.main()
