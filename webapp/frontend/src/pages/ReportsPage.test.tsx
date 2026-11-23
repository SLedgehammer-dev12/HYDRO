import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_META } from "../lib/mock";
import { useAppStore } from "../store/useAppStore";
import { ReportsPage } from "./ReportsPage";

describe("ReportsPage include_raw_ocr export option (F2, F14)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState({
      backend: "online",
      sessionApiReady: true,
      sessionId: "sess-rep-1",
      sessionName: "Hizan Kesit 01",
      revision: 2,
      exports: [],
      toasts: [],
    });
  });

  it("passes include_raw_ocr=true when the OCR appendix checkbox is checked", async () => {
    const requestedUrls: string[] = [];
    const origCreateObjectURL = URL.createObjectURL;
    const origRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:mock-report");
    URL.revokeObjectURL = vi.fn();

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      requestedUrls.push(url);
      if (url.endsWith("/api/meta")) {
        return new Response(JSON.stringify(DEMO_META), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/sessions?")) {
        return new Response(JSON.stringify({ items: [], total: 0, limit: 200, offset: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/sessions/sess-rep-1/export")) {
        return new Response(new Blob(["mock-xlsx-bytes"], { type: "application/octet-stream" }), {
          status: 200,
          headers: {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": 'attachment; filename="rapor.xlsx"',
          },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={qc}>
          <ReportsPage />
        </QueryClientProvider>,
      );

      const checkbox = await screen.findByLabelText(/Ham OCR özetini rapora ekle/i);
      expect((checkbox as HTMLInputElement).checked).toBe(false);
      fireEvent.click(checkbox);
      expect((checkbox as HTMLInputElement).checked).toBe(true);

      const excelBtn = screen.getByRole("button", { name: /Excel/i });
      fireEvent.click(excelBtn);

      await waitFor(() => {
        expect(
          requestedUrls.some((u) =>
            u.includes("/api/sessions/sess-rep-1/export?format=xlsx&include_raw_ocr=true"),
          ),
        ).toBe(true);
      });
    } finally {
      URL.createObjectURL = origCreateObjectURL;
      URL.revokeObjectURL = origRevokeObjectURL;
    }
  });
});
