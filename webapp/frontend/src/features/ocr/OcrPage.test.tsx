import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_META } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";
import OcrPage from "./OcrPage";

const mockAnalyzeOcr = vi.fn();
const mockWaitForAnalysis = vi.fn();
const mockCancelOcrAnalysis = vi.fn();

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
    listAnalyses: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    listMappingProfiles: vi.fn().mockResolvedValue({ items: [] }),
    analyzeOcr: (...args: unknown[]) => mockAnalyzeOcr(...args),
    waitForAnalysis: (...args: unknown[]) => mockWaitForAnalysis(...args),
    cancelOcrAnalysis: (...args: unknown[]) => mockCancelOcrAnalysis(...args),
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
    useAppStore.setState({ backend: "online", sessionId: null });
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
  });
});
