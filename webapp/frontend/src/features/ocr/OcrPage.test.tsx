import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_META } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";
import { TopBar } from "../../components/layout/TopBar";
import OcrPage from "./OcrPage";

const mockAnalyzeOcr = vi.fn();
const mockWaitForAnalysis = vi.fn();
const mockCancelOcrAnalysis = vi.fn();
const mockRetryOcrAnalysis = vi.fn();
const mockListAnalyses = vi.fn();

vi.mock("./ocrApi", async () => {
  const actual = await vi.importActual<typeof import("./ocrApi")>("./ocrApi");
  return {
    ...actual,
    getOcrStatus: vi.fn().mockResolvedValue({
      available: true,
      engine: "vision",
      status: "Hazır",
      limits: { max_file_size_bytes: 50 * 1024 * 1024 },
    }),
    listAnalyses: (...args: unknown[]) => mockListAnalyses(...args),
    getOcrQueue: vi.fn().mockResolvedValue({
      worker_mode: "inline",
      counts: { queued: 1, running: 0, succeeded: 2, failed: 1, cancelled: 0 },
      oldest_queued_age_s: 3.0,
      dead_letter_count: 1,
      dead_letter: [],
    }),
    listMappingProfiles: vi.fn().mockResolvedValue({ items: [] }),
    analyzeOcr: (...args: unknown[]) => mockAnalyzeOcr(...args),
    waitForAnalysis: (...args: unknown[]) => mockWaitForAnalysis(...args),
    cancelOcrAnalysis: (...args: unknown[]) => mockCancelOcrAnalysis(...args),
    retryOcrAnalysis: (...args: unknown[]) => mockRetryOcrAnalysis(...args),
  };
});

vi.mock("../../hooks/queries", async () => {
  const actual = await vi.importActual<typeof import("../../hooks/queries")>(
    "../../hooks/queries",
  );
  return {
    ...actual,
    useMeta: () => ({
      data: {
        ...DEMO_META,
        limits: { ...DEMO_META.limits, ocr_timeout_s: 1200 },
      },
    }),
    useProjects: () => ({ data: [] }),
    useSessions: () => ({ data: [] }),
  };
});

describe("OcrPage unmount cleanup (F10) and dynamic server timeout (F11)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListAnalyses.mockResolvedValue({ items: [], total: 0 });
    useAppStore.setState({ backend: "online", sessionId: null, activeOcrJob: null, tab: "ocr" });
  });

  it("passes (ocr_timeout_s + 30)s to waitForAnalysis and aborts polling on unmount without cancelling server job", async () => {
    let capturedSignal: AbortSignal | undefined;
    let capturedTimeoutMs: number | undefined;

    mockAnalyzeOcr.mockResolvedValue({
      analysis_id: "job-123",
      status: "queued",
      reused: false,
    });
    mockWaitForAnalysis.mockImplementation(
      (_id: string, opts: { signal?: AbortSignal; timeoutMs?: number }) => {
        capturedSignal = opts?.signal;
        capturedTimeoutMs = opts?.timeoutMs;
        return new Promise(() => {
          /* keep pending until unmount */
        });
      },
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { unmount } = render(
      <QueryClientProvider client={qc}>
        <OcrPage />
      </QueryClientProvider>,
    );

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const samplePdf = new File(["%PDF-1.4 sample"], "rapor.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [samplePdf] } });

    const analyzeBtn = await screen.findByRole("button", { name: /^Analiz Et$/i });
    fireEvent.click(analyzeBtn);

    await waitFor(() => {
      expect(mockWaitForAnalysis).toHaveBeenCalledTimes(1);
    });
    // (1200 + 30) * 1000 = 1_230_000 ms
    expect(capturedTimeoutMs).toBe(1_230_000);
    expect(capturedSignal?.aborted).toBe(false);

    unmount();

    expect(capturedSignal?.aborted).toBe(true);
    expect(mockCancelOcrAnalysis).not.toHaveBeenCalled();
    expect(useAppStore.getState().activeOcrJob?.id).toBe("job-123");
  });

  it("displays background OCR indicator in TopBar outside OCR tab and cancels job on dismiss", async () => {
    mockCancelOcrAnalysis.mockResolvedValue({ id: "job-456", status: "cancelled" });
    useAppStore.setState({
      tab: "projects",
      activeOcrJob: { id: "job-456", fileName: "form.pdf", stage: "Analiz ediliyor" },
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <TopBar onOpenHelp={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("topbar-ocr-indicator")).toBeInTheDocument();
    expect(screen.getByText(/OCR çalışıyor/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Arka plan OCR analizini iptal et/i }));

    await waitFor(() => {
      expect(mockCancelOcrAnalysis).toHaveBeenCalledWith("job-456");
    });
    expect(useAppStore.getState().activeOcrJob).toBeNull();
  });

  it("renders Tekrar Dene button for failed history items and retries via POST retry", async () => {
    mockListAnalyses.mockResolvedValue({
      items: [
        {
          id: "failed-ana-999",
          status: "failed",
          source: "ocr",
          confidence: 0,
          page_count: 1,
          blocking_count: 0,
          warnings_count: 0,
          created_at: "2026-11-26T10:00:00Z",
        },
      ],
      total: 1,
    });
    mockRetryOcrAnalysis.mockResolvedValue({
      analysis_id: "failed-ana-999",
      status: "queued",
      reused: false,
    });
    mockWaitForAnalysis.mockResolvedValue({
      id: "failed-ana-999",
      status: "succeeded",
      source: "ocr",
      page_count: 1,
      character_count: 100,
      confidence: 0.94,
      report: { warnings: [] },
      discrepancies: [],
      issues: [],
      warnings: [],
      pages: [],
      approved: false,
      applied: false,
      suggested_fixes: [],
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <OcrPage />
      </QueryClientProvider>,
    );

    const retryBtn = await screen.findByRole("button", { name: /Tekrar Dene/i });
    expect(await screen.findByTestId("ocr-queue-badge")).toHaveTextContent(
      "Kuyruk: 1 · Başarısız: 1",
    );
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(mockRetryOcrAnalysis).toHaveBeenCalledWith(
        "failed-ana-999",
        expect.any(AbortSignal),
      );
      expect(mockWaitForAnalysis).toHaveBeenCalledWith(
        "failed-ana-999",
        expect.objectContaining({ timeoutMs: 1_230_000 }),
      );
    });
  });
});
