import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_GRADES, DEMO_META, DEMO_PIPES, createEmptyInputs } from "../lib/mock";
import { useAppStore } from "../store/useAppStore";
import { GeometryPage } from "./GeometryPage";

vi.mock("../components/charts/LazyCharts", () => ({
  ElevationProfileChart: () => <div data-testid="mock-elevation-chart" />,
  UtilizationChart: () => <div data-testid="mock-utilization-chart" />,
}));

vi.mock("../components/geometry/SiteSurveyPanel", () => ({
  SiteSurveyPanel: () => <div data-testid="mock-site-survey" />,
}));

vi.mock("./FieldPage", () => ({
  FieldPage: () => <div data-testid="mock-field-embedded" />,
}));

vi.mock("../hooks/queries", async () => {
  const actual = await vi.importActual<typeof import("../hooks/queries")>("../hooks/queries");
  return {
    ...actual,
    useCatalog: () => ({ pipes: DEMO_PIPES, grades: DEMO_GRADES }),
    useMeta: () => ({ data: DEMO_META }),
  };
});

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("GeometryPage per-segment SMYS and material grade", () => {
  beforeEach(() => {
    const inputs = createEmptyInputs();
    inputs.section_meta.section_no = "K-01";
    inputs.material_grade = "API 5L PSL2 X65 / L450 - SMYS 450 MPa";
    inputs.section_profile.smys_mpa = 450;
    inputs.segments = [
      {
        id: "seg-a",
        nps_label: "NPS 16",
        schedule_label: "Sch 20",
        outside_diameter_mm: 406.4,
        wall_thickness_mm: 8.74,
        length_m: 600,
        start_station_m: 0,
        material_grade: "API 5L PSL2 X65 / L450 - SMYS 450 MPa",
        smys_mpa: 450,
      },
      {
        id: "seg-b",
        nps_label: "NPS 16",
        schedule_label: "Sch 20",
        outside_diameter_mm: 406.4,
        wall_thickness_mm: 8.74,
        length_m: 400,
        start_station_m: 600,
        material_grade: "",
        smys_mpa: null,
      },
    ];
    useAppStore.setState({
      inputs,
      results: { source: "demo", coefficients: {} },
      sessionId: "sess-1",
      dirty: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lets users select per-segment grade, override custom SMYS, and highlights the limiting segment", () => {
    renderWithQuery(<GeometryPage />);

    const gradeSelect2 = screen.getByLabelText("Segment 2 malzeme kalitesi") as HTMLSelectElement;
    expect(gradeSelect2.value).toBe("");

    fireEvent.change(gradeSelect2, {
      target: { value: "API 5L PSL2 X42 / L290 - SMYS 290 MPa" },
    });

    let segments = useAppStore.getState().inputs.segments;
    expect(segments[1].material_grade).toBe("API 5L PSL2 X42 / L290 - SMYS 290 MPa");
    expect(segments[1].smys_mpa).toBe(290);

    // Limiting segment badge appears once segment 2 has lower SMYS than segment 1
    expect(screen.getAllByText("Limit")).toHaveLength(1);
    const seg2Row = gradeSelect2.closest("tr");
    expect(seg2Row?.textContent).toContain("Limit");

    // Custom SMYS override updates segment SMYS & clears mismatched catalog label
    const smysInput2 = screen.getByLabelText("Segment 2 SMYS (MPa)") as HTMLInputElement;
    fireEvent.change(smysInput2, { target: { value: "305" } });
    fireEvent.blur(smysInput2);
    segments = useAppStore.getState().inputs.segments;
    expect(segments[1].smys_mpa).toBe(305);
    expect(segments[1].material_grade).toBe("");

    // Negative SMYS triggers aria-invalid without corrupting store
    fireEvent.change(smysInput2, { target: { value: "-50" } });
    fireEvent.blur(smysInput2);
    expect(smysInput2).toHaveAttribute("aria-invalid", "true");
    expect(useAppStore.getState().inputs.segments[1].smys_mpa).toBe(305);

    // Clearing SMYS resets to hat varsayilani
    fireEvent.change(smysInput2, { target: { value: "" } });
    fireEvent.blur(smysInput2);
    expect(useAppStore.getState().inputs.segments[1].smys_mpa).toBeNull();
  });
});
