import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSessionForms } from "../../hooks/queries";
import { api } from "../../lib/api";
import { createDefaultInputs } from "../../lib/mock";
import type {
  SectionFormRecord,
  SessionFormsResponse,
  TimeSeriesRecordItem,
  TimeSeriesSummary,
} from "../../lib/types";
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

function makeFormsPayload(formStatus: SectionFormRecord["status"]): SessionFormsResponse {
  return {
    session_id: "sess-1",
    project_id: "proj-1",
    section_no: "K-01",
    session_name: "K-01",
    merged_header: {},
    calculations: {},
    summary: {
      required_total: 11,
      filled_required: formStatus === "empty" ? 0 : 1,
      missing_required: formStatus === "empty" ? 11 : 10,
      missing_titles: [],
      supplementary_filled: 0,
      failed_forms: [],
      warning_forms: [],
      passed_forms_count: formStatus === "passed" ? 1 : 0,
      warning_forms_count: 0,
      complete: false,
    },
    forms: [
      {
        id: "f-018",
        form_code: "leak_stabilization",
        botas_code: "BOT-FRM-İNB-001-018",
        form_title: "Dengeleme İçin Kaçak Test Raporu",
        required: true,
        order: 4,
        status: formStatus,
        analysis_id: null,
        source_filename: "",
        pages: [1],
        form_date: "2026-11-14",
        extracted_data: { rows: [] },
        warnings: [],
        revision: formStatus === "empty" ? 1 : 2,
        filled_at: null,
        updated_at: null,
      },
    ],
    missing_required_forms: [],
    checkpoints: [],
  };
}

function SessionFormsProbe() {
  const query = useSessionForms("sess-1");
  const status = query.data?.forms[0]?.status ?? "loading";
  return <div data-testid="forms-status-probe">{status}</div>;
}

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

  it("renders Section 12 & 15 summary, enforces strict UTC add timestamp, supports arrow-key tabs", async () => {
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

    fireEvent.change(screen.getByLabelText(/Zaman \(UTC\)/), {
      target: { value: "2026-11-15T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/Basınç \(bar\)/), { target: { value: "84,7" } });
    fireEvent.change(screen.getByLabelText(/Sıcaklık \(°C\)/), { target: { value: "15,25" } });
    await user.click(submitBtn);
    await waitFor(() =>
      expect(addSpy).toHaveBeenCalledWith(
        "sess-1",
        expect.objectContaining({ timestamp: "2026-11-15T09:00:00.000Z" }),
      ),
    );

    const firstTab = screen.getByRole("tab", { name: /Termal & 24s/ });
    firstTab.focus();
    fireEvent.keyDown(firstTab, { key: "ArrowRight" });
    const secondTab = screen.getByRole("tab", { name: /Basınçlandırma \(14\.1–14\.2\)/ });
    expect(secondTab).toHaveAttribute("aria-selected", "true");
  });

  it("imports bulk paste rows, invalidates session-forms cache on sync, and warns on dirty form", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "timeSeries").mockResolvedValue({
      items: SAMPLE_ITEMS,
      total: 2,
      limit: 1000,
      offset: 0,
    });
    vi.spyOn(api, "timeSeriesSummary").mockResolvedValue(makeSummary());
    vi.spyOn(api, "sessionForms")
      .mockResolvedValueOnce(makeFormsPayload("empty"))
      .mockResolvedValueOnce(makeFormsPayload("passed"));
    const batchSpy = vi.spyOn(api, "batchTimeSeries").mockResolvedValue({
      inserted: 1,
      total: 1,
      items: [SAMPLE_ITEMS[0]],
      summary: makeSummary(),
    });
    const syncSpy = vi.spyOn(api, "syncTimeSeriesForm").mockResolvedValue({
      direction: "to_form",
      form_code: "leak_stabilization",
      synced_count: 2,
      skipped_rows: 0,
      summary: makeSummary(),
    });

    renderWithQuery(
      <>
        <SessionFormsProbe />
        <OperationsPanel formDirty />
      </>,
    );
    await screen.findByText(/Termal Denge \(Bölüm 12\)/);
    await waitFor(() => expect(screen.getByTestId("forms-status-probe")).toHaveTextContent("empty"));

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

    // Writing to form while formDirty prompts confirmation before calling API
    await user.click(screen.getByRole("button", { name: /Form 018'e yaz/ }));
    expect(syncSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/Formda kaydedilmemiş değişiklikler var/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Evet, form satırlarını güncelle/ }));
    await waitFor(() =>
      expect(syncSpy).toHaveBeenCalledWith(
        "sess-1",
        expect.objectContaining({ form_code: "leak_stabilization", direction: "to_form" }),
      ),
    );
    // Proves ["session-forms", "sess-1"] cache was invalidated & refetched
    await waitFor(() =>
      expect(screen.getByTestId("forms-status-probe")).toHaveTextContent("passed"),
    );
  });

  it("evaluates ad-hoc records upon offline-to-online recovery and supports clear-all flow", async () => {
    const user = userEvent.setup();
    useAppStore.setState({ backend: "demo", sessionId: null });
    const thermalSpy = vi.spyOn(api, "thermalBalance").mockResolvedValue(makeSummary());

    const view = renderWithQuery(<OperationsPanel />);
    fireEvent.change(screen.getByLabelText(/Basınç \(bar\)/), { target: { value: "85" } });
    fireEvent.change(screen.getByLabelText(/Sıcaklık \(°C\)/), { target: { value: "15" } });
    await user.click(screen.getByRole("button", { name: /Okuma ekle/i }));
    expect(thermalSpy).not.toHaveBeenCalled();

    // Recover online connectivity -> ad-hoc evaluation triggers automatically
    useAppStore.setState({ backend: "online" });
    view.rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <OperationsPanel />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(thermalSpy).toHaveBeenCalledTimes(1));

    // Inline two-step clear confirmation
    await user.click(screen.getByRole("button", { name: /Tümünü temizle/ }));
    await user.click(screen.getByRole("button", { name: /Tümünü silmeyi onayla/ }));
    expect(screen.getByText("Yerel okumalar temizlendi.")).toBeInTheDocument();
  });

  it("virtualizes 10,000 time-series rows with bounded DOM nodes and fast render (R9)", async () => {
    const startMs = Date.parse("2026-11-01T00:00:00Z");
    const bulkItems: TimeSeriesRecordItem[] = Array.from({ length: 10000 }, (_, i) => ({
      id: `bulk-${i}`,
      timestamp: new Date(startMs + i * 60_000).toISOString(),
      pressure_bar: 85.0 - (i % 10) * 0.01,
      temperature_c: 15.0 + (i % 5) * 0.1,
      volume_m3: 100.0,
      notes: `Okuma ${i}`,
      source: "batch",
    }));

    vi.spyOn(api, "timeSeries").mockResolvedValue({
      items: bulkItems,
      total: bulkItems.length,
      limit: 10000,
      offset: 0,
    });
    vi.spyOn(api, "timeSeriesSummary").mockResolvedValue(makeSummary({ record_count: bulkItems.length }));

    const t0 = performance.now();
    const { container } = renderWithQuery(<OperationsPanel />);
    await screen.findByText(/\(10000\)/);
    const elapsedMs = performance.now() - t0;

    const dataRows = container.querySelectorAll("tbody tr:not([data-virtual-spacer])");
    expect(dataRows.length).toBeGreaterThan(0);
    expect(dataRows.length).toBeLessThanOrEqual(40);
    expect(container.querySelector('tr[data-virtual-spacer="bottom"]')).not.toBeNull();
    expect(elapsedMs).toBeLessThan(1500);
  });
});
