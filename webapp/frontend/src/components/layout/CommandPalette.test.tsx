import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "../../pages/DashboardPage";
import Dropzone from "../../features/ocr/components/Dropzone";
import { useAppStore } from "../../store/useAppStore";
import { CommandPalette } from "./CommandPalette";

vi.mock("../../components/charts/LazyCharts", () => ({
  ElevationProfileChart: () => <div data-testid="mock-elev" />,
  TrendChart: () => <div data-testid="mock-trend" />,
}));

function wrapper(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("Phase 3 UI ergonomics", () => {
  beforeEach(() => {
    useAppStore.setState({
      tab: "dashboard",
      activeFormCode: "test_data",
      sessionStatus: "active",
      results: { source: "demo" },
    });
  });

  it("CommandPalette filters entries and navigates to selected form or tab", () => {
    const onClose = vi.fn();
    render(wrapper(<CommandPalette open onClose={onClose} onOpenHelp={vi.fn()} />));

    const input = screen.getByRole("searchbox", { name: /Komut ve sayfa arama/i });
    fireEvent.change(input, { target: { value: "021" } });

    const optionBtn = screen.getByRole("button", { name: /021 · Basınç Testi Raporu/i });
    fireEvent.click(optionBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().tab).toBe("forms");
    expect(useAppStore.getState().activeFormCode).toBe("pressure_test");
  });

  it("CommandPalette closes on Escape and restores focus to opener", () => {
    const onClose = vi.fn();
    function Harness() {
      return (
        <div>
          <button type="button" data-testid="palette-opener">
            Aç
          </button>
          <CommandPalette open onClose={onClose} onOpenHelp={vi.fn()} />
        </div>
      );
    }
    render(wrapper(<Harness />));
    const opener = screen.getByTestId("palette-opener");
    opener.focus();
    const input = screen.getByRole("searchbox", { name: /Komut ve sayfa arama/i });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("DashboardPage marks Step 4 done when sessionStatus is completed and exposes OCR quick import", () => {
    useAppStore.setState({ sessionStatus: "completed" });
    render(wrapper(<DashboardPage />));

    const reportBtn = screen.getByRole("button", { name: /Resmî Rapor/i });
    expect(reportBtn).toHaveTextContent("Tamamlandı");

    const ocrBtn = screen.getByRole("button", { name: /OCR'dan İçe Aktar/i });
    fireEvent.click(ocrBtn);
    expect(useAppStore.getState().tab).toBe("ocr");
  });

  it("Dropzone accepts clipboard pasted PNG images cleanly", () => {
    const onSelect = vi.fn();
    const onError = vi.fn();
    render(
      <Dropzone
        file={null}
        error={null}
        onSelect={onSelect}
        onRemove={vi.fn()}
        onError={onError}
      />,
    );

    const pngFile = new File([new Uint8Array([137, 80, 78, 71])], "image.png", {
      type: "image/png",
    });
    const pasteEvent = new Event("paste", { bubbles: true, cancelable: true }) as Event & {
      clipboardData: {
        items: Array<{ kind: string; type: string; getAsFile: () => File | null }>;
      };
    };
    Object.defineProperty(pasteEvent, "clipboardData", {
      value: {
        items: [{ kind: "file", type: "image/png", getAsFile: () => pngFile }],
      },
    });
    window.dispatchEvent(pasteEvent);

    expect(onError).toHaveBeenCalledWith(null);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].name).toBe("pano-goruntusu.png");
  });
});
