import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { createDefaultInputs } from "../../lib/mock";
import type { TimeSeriesRecordItem, TimeSeriesSummary } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { OperationsPanel } from "./OperationsPanel";

vi.mock("../../components/charts/LazyCharts", () => ({
  TimeSeriesChart: ({ records }: { records: Array<unknown> }) => (
    <div data-testid="mock-ts-chart">points={records.length}</div>
  ),
}));

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function makeSummary(overrides: Partial<TimeSeriesSummary> = {}): TimeSeriesSummary {
  return {
    record_count: 25,
    duration_hours: 24.0,
    balanced: true,
    thermal_duration_ok: true,
    temp_diff_c: 0.2,
    reason: null,
    average_temperature_last_4h_c: 15.2,
    previous_4h_avg_c: 15.0,
    average_temperature_c: 15.05,
    first_timestamp: "2026-11-14T08:00:00Z",
    last_timestamp: "2026-11-15T08:00:00Z",
    max_gap_hours: 1.0,
    recording_duration_ok: true,
    recording_interval_ok: true,
    recording_passed: true,
    initial_pressure_bar: 85.0,
    final_pressure_bar: 84.76,
    pressure_change_pa_bar: 0.24,
    min_pressure_bar: 84.76,
    max_pressure_bar: 85.0,
    initial_temperature_c: 15.0,
    final_temperature_c: 15.2,
    temperature_change_dt_c: -0.2,
    min_temperature_c: 15.0,
    max_temperature_c: 15.2,
    initial_volume_m3: 100.0,
    final_volume_m3: 101.2,
    volume_delta_m3: 1.2,
    decision: {
      status: "BASARILI",
      title: "Termal Denge",
      summary: "Sure = 24.0 saat; son 4 saat ile onceki 4 saat arasindaki sicaklik farki = 0.200 °C.",
      rule: "sure >= 24 h ve |dT_4h| <= 0.5 °C",
      margin: 0.3,
    },
    recording_decision: {
      status: "BASARILI",
      title: "24 Saatlik Test Kaydi (15.1)",
      summary: "25 okuma, toplam sure = 24.00 saat, en uzun okuma araligi = 1.00 sa (60 dk).",
      rule: "sure >= 24 h ve maks okuma araligi <= 2 h (Sartname 15.1)",
      margin: 0.0,
    },
    ...overrides,
  };
}

const SAMPLE_ITEMS: TimeSeriesRecordItem[] = [
  {
    id: "ts-1",
    timestamp: "2026-11-14T08:00:00Z",
    pressure_bar: 85.0,
    temperature_c: 15.0,
    volume_m3: 100.0,
    notes: "İlk okuma",
    source: "manual",
  },
  {
    id: "ts-2",
    timestamp: "2026-11-15T08:00:00Z",
    pressure_bar: 84.76,
    temperature_c: 15.2,
    volume_m3: 101.2,
    notes: "Son okuma",
    source: "form_018",
  },
];

describe("TimeSeriesPanel and OperationsPanel", () => {
  beforeEach(() => {
    useAppStore.setState({
      backend: "online",
      sessionApiReady: true,
      sessionId: "sess-1",
      inputs: createDefaultInputs(),
      dirty: false,
      toasts: [],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Section 12 & 15 summary, supports arrow-key tabs, and validates/adds a reading", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "timeSeries").mockResolvedValue({
      items: SAMPLE_ITEMS,
      total: 2,
      limit: 1000,
      offset: 0,
    });
    vi.spyOn(api, "timeSeriesSummary").mockResolvedValue(makeSummary());
    const addSpy = vi.spyOn(api, "addTimeSeries").mockResolvedValue({
      record: {
        id: "ts-3",
        timestamp: "2026-11-15T09:00:00Z",
        pressure_bar: 84.7,
        temperature_c: 15.25,
        volume_m3: null,
        notes: "",
        source: "manual",
      },
      summary: makeSummary({ record_count: 26 }),
    });

    renderWithQuery(<OperationsPanel />);

    expect(await screen.findByText(/Termal Denge \(Bölüm 12\)/)).toBeInTheDocument();
    expect(screen.getByText(/24 Saatlik Test Kaydı \(Bölüm 15\.1\)/)).toBeInTheDocument();
    expect(screen.getByTestId("mock-ts-chart")).toHaveTextContent("points=2");

    const region = screen.getByRole("region", {
      name: /24 Saatlik Basınç ve Sıcaklık Zaman Serisi Kayıtları/,
    });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("columnheader", { name: /Zaman \(UTC\)/ })).toBeInTheDocument();

    const submitBtn = screen.getByRole("button", { name: /Okuma ekle/i });
    await user.click(submitBtn);
    expect(screen.getByText("Basınç gerekli.")).toBeInTheDocument();
    expect(addSpy).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Basınç \(bar\)/), { target: { value: "84,7" } });
    fireEvent.change(screen.getByLabelText(/Sıcaklık \(°C\)/), { target: { value: "15,25" } });
    await user.click(submitBtn);
    await waitFor(() => expect(addSpy).toHaveBeenCalledTimes(1));

    const firstTab = screen.getByRole("tab", { name: /Termal & 24s/ });
    firstTab.focus();
    fireEvent.keyDown(firstTab, { key: "ArrowRight" });
    const secondTab = screen.getByRole("tab", { name: /Basınçlandırma \(14\.1–14\.2\)/ });
    expect(secondTab).toHaveAttribute("aria-selected", "true");
  });

  it("imports bulk paste rows, applies Tilk/Tson/Pa to pressure store, and syncs Form 018", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "timeSeries").mockResolvedValue({
      items: SAMPLE_ITEMS,
      total: 2,
      limit: 1000,
      offset: 0,
    });
    vi.spyOn(api, "timeSeriesSummary").mockResolvedValue(makeSummary());
    const batchSpy = vi.spyOn(api, "batchTimeSeries").mockResolvedValue({
      inserted: 1,
      total: 1,
      items: [SAMPLE_ITEMS[0]],
      summary: makeSummary(),
    });
    const syncSpy = vi.spyOn(api, "syncTimeSeriesForm").mockResolvedValue({
      direction: "from_form",
      form_code: "leak_stabilization",
      synced_count: 25,
      skipped_rows: 0,
      summary: makeSummary(),
    });

    renderWithQuery(<OperationsPanel />);
    await screen.findByText(/Termal Denge \(Bölüm 12\)/);

    await user.click(screen.getByRole("button", { name: /Toplu yapıştır/ }));
    fireEvent.change(screen.getByLabelText(/Toplu okuma satırları/), {
      target: { value: "2026-11-14T08:00Z\t85,0\t15,0" },
    });
    await user.click(screen.getByRole("radio", { name: "Mevcut kayıtları değiştir" }));
    await user.click(screen.getByRole("button", { name: "Yapıştırılan satırları içe aktar" }));
    await waitFor(() =>
      expect(batchSpy).toHaveBeenCalledWith(
        "sess-1",
        expect.objectContaining({ mode: "replace", source: "batch" }),
      ),
    );

    await user.click(
      screen.getByRole("button", { name: /Tilk, Tson ve Pa’yı Basınç Testine Aktar/ }),
    );
    const pr = useAppStore.getState().inputs.pressure;
    expect(pr.t_initial_c).toBe(15);
    expect(pr.t_final_c).toBe(15.2);
    expect(pr.delta_t_c).toBe(-0.2);
    expect(pr.actual_pressure_change_bar).toBe(0.24);
    expect(pr.derive_delta_t).toBe(true);

    await user.click(screen.getByRole("button", { name: /Form 018'den çek/ }));
    await waitFor(() =>
      expect(syncSpy).toHaveBeenCalledWith(
        "sess-1",
        expect.objectContaining({ form_code: "leak_stabilization", direction: "from_form" }),
      ),
    );
  });
});
