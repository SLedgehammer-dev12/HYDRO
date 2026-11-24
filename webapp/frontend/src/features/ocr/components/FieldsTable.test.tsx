import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FieldsTable from "./FieldsTable";
import type { FlatField } from "../fields";

const SAMPLE_FIELDS: FlatField[] = [
  {
    descriptor: {
      key: "air_test.a",
      label: "Hava testi A",
      unit: "10^-6/bar",
      required: false,
      group: "air",
    },
    field: {
      value: 4497,
      unit: "10^-6/bar",
      confidence: 0.78,
      raw_text: "A: 4497",
      page: 1,
    },
  },
];

describe("FieldsTable OCR-4 suggested fixes", () => {
  it("renders inline decimal-fix banner and applies suggestion on click", () => {
    const onEdit = vi.fn();
    const fixes = [
      {
        field: "air_test.a",
        label: "Hava testi A",
        current_value: 4497,
        suggested_value: 44.97,
        reason: "A katsayisi icin beklenen aralik 25-75 (10^-6/bar); ondalik nokta kaybi olabilir.",
      },
    ];

    const { rerender } = render(
      <FieldsTable
        fields={SAMPLE_FIELDS}
        selected={new Set(["air_test.a"])}
        edits={{}}
        suggestedFixes={fixes}
        onToggle={vi.fn()}
        onEdit={onEdit}
      />,
    );

    expect(screen.getByText(/Olası OCR ondalık hatası tespit edildi \(1 alan\)/i)).toBeTruthy();
    const btn = screen.getByRole("button", { name: /Hava testi A için 44\.97 önerisini uygula/i });
    fireEvent.click(btn);
    expect(onEdit).toHaveBeenCalledWith("air_test.a", "44.97");

    rerender(
      <FieldsTable
        fields={SAMPLE_FIELDS}
        selected={new Set(["air_test.a"])}
        edits={{ "air_test.a": "44.97" }}
        suggestedFixes={fixes}
        onToggle={vi.fn()}
        onEdit={onEdit}
      />,
    );
    expect(screen.queryByRole("button", { name: /44\.97 önerisini uygula/i })).toBeNull();
  });
});
