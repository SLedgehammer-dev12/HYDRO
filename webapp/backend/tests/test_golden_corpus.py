"""Deterministic golden corpus tests for 020/022 evaluations (R10) & OCR F1 (OCR-11)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from app.services.dossier import evaluate_section_calculations

from hidrostatik_test.services.report_ocr import parse_report

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
CASES_020_022 = json.loads((GOLDEN_DIR / "cases_020_022.json").read_text(encoding="utf-8"))
OCR_CORPUS = json.loads((GOLDEN_DIR / "ocr_corpus.json").read_text(encoding="utf-8"))


def _lookup_report_field(report_dict: dict[str, Any], path: str) -> Any:
    cur: Any = report_dict
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    if isinstance(cur, dict) and "value" in cur:
        return cur["value"]
    return cur


def _values_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, (int, float)):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        return math.isclose(float(actual), float(expected), rel_tol=1e-3, abs_tol=1e-4)
    if isinstance(expected, str):
        return isinstance(actual, str) and expected.strip().casefold() in actual.strip().casefold()
    return actual == expected


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES_020_022, ids=[c["name"] for c in CASES_020_022])
def test_golden_020_022_evaluations(case: dict[str, Any]) -> None:
    result = evaluate_section_calculations(
        case["merged_header"],
        case["forms"],
        segments=case.get("segments"),
    )
    for section_key in ("air", "pressure"):
        expected_section = case["expected"][section_key]
        actual_section = result[section_key]
        for field_key, expected_val in expected_section.items():
            actual_val = actual_section.get(field_key)
            assert _values_match(actual_val, expected_val), (
                f"{case['name']} {section_key}.{field_key}: expected {expected_val!r}, got {actual_val!r}"
            )


@pytest.mark.golden
@pytest.mark.ocr
def test_ocr_regression_corpus_f1_threshold() -> None:
    tp = 0
    fp = 0
    fn = 0
    mismatches: list[str] = []

    for case in OCR_CORPUS:
        report_dict = parse_report(case["text"]).to_dict()
        for field_path, expected_val in case["expected"].items():
            actual_val = _lookup_report_field(report_dict, field_path)
            if actual_val is None:
                fn += 1
                mismatches.append(
                    f"{case['name']}:{field_path} missing (expected {expected_val!r})"
                )
            elif _values_match(actual_val, expected_val):
                tp += 1
            else:
                fp += 1
                fn += 1
                mismatches.append(
                    f"{case['name']}:{field_path} expected {expected_val!r}, got {actual_val!r}"
                )

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    assert f1 >= 0.95, (
        f"OCR corpus F1={f1:.4f} (P={precision:.4f}, R={recall:.4f}) below 0.95; "
        f"mismatches={mismatches}"
    )
