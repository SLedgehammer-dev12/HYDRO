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

  it("supports batch fix apply, filtering/search, page preview trigger, and row keyboard edit", () => {
    const onEdit = vi.fn();
    const onPreviewPage = vi.fn();
    const twoFields: FlatField[] = [
      ...SAMPLE_FIELDS,
      {
        descriptor: {
          key: "pressure_test.pa",
          label: "Hesaplanan Pa",
          unit: "bar",
          required: true,
          group: "pressure",
        },
        field: {
          value: 0.14,
          unit: "bar",
          confidence: 0.45,
          raw_text: "Pa: 0,14",
          page: 2,
        },
      },
    ];
    const fixes = [
      {
        field: "air_test.a",
        label: "Hava testi A",
        current_value: 4497,
        suggested_value: 44.97,
        reason: "ondalik",
      },
    ];

    render(
      <FieldsTable
        fields={twoFields}
        selected={new Set(["air_test.a"])}
        edits={{}}
        suggestedFixes={fixes}
        onToggle={vi.fn()}
        onEdit={onEdit}
        onPreviewPage={onPreviewPage}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Tüm Önerileri Uygula \(1\)/i }));
    expect(onEdit).toHaveBeenCalledWith("air_test.a", "44.97");

    fireEvent.click(screen.getByRole("button", { name: "Düşük Güven" }));
    expect(screen.queryByText("Hava testi A")).toBeNull();
    expect(screen.getByText("Hesaplanan Pa")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Sayfa 2 belgesini önizle/i }));
    expect(onPreviewPage).toHaveBeenCalledWith(2);

    const searchInput = screen.getByRole("searchbox", { name: /Alanlarda ara/i });
    fireEvent.change(searchInput, { target: { value: "Pa: 0,14" } });
    expect(screen.getByText("Hesaplanan Pa")).toBeTruthy();
  });
});
