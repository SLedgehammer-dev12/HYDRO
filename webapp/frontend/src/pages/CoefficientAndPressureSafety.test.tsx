import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { RightPanel } from "../components/layout/RightPanel";
import { createDefaultInputs } from "../lib/mock";
import { useAppStore } from "../store/useAppStore";
import { CoefficientsPage } from "./CoefficientsPage";
import { PressurePage } from "./PressurePage";

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("Slice 5 UI safety, B=0, 0 C notice, and Tilk/Tson derivation", () => {
  beforeEach(() => {
    const inputs = createDefaultInputs();
    inputs.water_backend = "table_v1";
    inputs.pressure.temperature_c = 2;
    inputs.pressure.b_micro_per_c = 0;
    inputs.helper.water_beta_micro_per_c = -10;
    useAppStore.setState({
      backend: "demo",
      sessionId: null,
      inputs,
      results: {
        source: "demo",
        backendCompare: {
          temperature_c: 2,
          pressure_bar: 80,
          items: [
            {
              backend: { key: "table_v1", label: "IAPWS-IF97 Region 1", distribution_ready: true },
              a_micro_per_bar: 46.1,
              beta_micro_per_c: -10,
              density_kg_per_m3: 1003.4,
              error: null,
            },
            {
              backend: { key: "coolprop", label: "IAPWS-95", distribution_ready: true },
              a_micro_per_bar: null,
              beta_micro_per_c: null,
              density_kg_per_m3: null,
              error: "Kütüphane hazır değil",
            },
          ],
        },
      },
      dirty: false,
    });
  });

  it("CoefficientsPage treats B=0 as filled, surfaces 0-4 C anomaly notice, comparison error and switches water_backend cleanly", async () => {
    const user = userEvent.setup();
    renderWithQuery(<CoefficientsPage />);

    expect(screen.getByText("0–4 °C yoğunluk anomalisi / negatif β veya B")).toBeInTheDocument();
    expect(screen.getByText(/Hata: Kütüphane hazır değil/)).toBeInTheDocument();
    // B=0 is present so at least B badge shows manuel (not empty/eksik)
    expect(screen.getAllByText(/manuel/i).length).toBeGreaterThan(0);

    const select = screen.getByLabelText("Su özelliği backend'i");
    await user.selectOptions(select, "table_v1_bicubic");
    expect(useAppStore.getState().inputs.water_backend).toBe("table_v1_bicubic");
    expect(useAppStore.getState().inputs.modes.pressure_a_reference).toBe("");
  });

  it("PressurePage clears derived delta_t_c when Tilk or Tson is cleared and RightPanel accepts 0 values", async () => {
    const user = userEvent.setup();
    const zeroInputs = createDefaultInputs();
    zeroInputs.air.actual_added_water_m3 = 0;
    zeroInputs.pressure.delta_t_c = 0;
    zeroInputs.pressure.actual_pressure_change_bar = 0;
    zeroInputs.pressure.t_initial_c = 22;
    zeroInputs.pressure.t_final_c = 20;
    zeroInputs.pressure.derive_delta_t = true;
    useAppStore.setState({ inputs: zeroInputs });

    const { unmount } = renderWithQuery(<RightPanel />);
    expect(screen.queryByText(/Hava: fiili ilave su \(Vpa\) girilmedi/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Basınç: ΔT girilmedi/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Basınç: Pa girilmedi/)).not.toBeInTheDocument();
    unmount();

    renderWithQuery(<PressurePage />);
    const tilkInput = screen.getByLabelText(/Başlangıç sıcaklığı Tilk/);
    await user.clear(tilkInput);
    expect(useAppStore.getState().inputs.pressure.delta_t_c).toBeNull();

    // Switching to direct ΔT mode hides Tilk/Tson fields to prevent ignored-input mismatch
    await user.click(screen.getByRole("button", { name: "ΔT doğrudan gir" }));
    expect(screen.queryByLabelText(/Başlangıç sıcaklığı Tilk/)).not.toBeInTheDocument();

    // Enabling Pilk - Pson derivation computes Pa = Pilk - Pson with signed direction feedback
    await user.click(screen.getByRole("button", { name: "Pilk − Pson ile türet" }));
    await user.type(screen.getByLabelText(/Başlangıç basıncı Pilk/), "82");
    await user.type(screen.getByLabelText(/Bitiş basıncı Pson/), "76,05");
    expect(useAppStore.getState().inputs.pressure.actual_pressure_change_bar).toBe(5.95);
    expect(screen.getByText(/Basınç düşüşü \(\+5,95 bar\)/)).toBeInTheDocument();
  });
});
