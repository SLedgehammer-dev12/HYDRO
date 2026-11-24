import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyInputs } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";
import { HelpDialog } from "../layout/HelpDialog";
import { TopBar } from "../layout/TopBar";
import { GuidedTourOverlay } from "./GuidedTourOverlay";
import { OnboardingWelcomeCard } from "./OnboardingWelcomeCard";

describe("Opt-in Onboarding Welcome Card & 5-step Guided Demo Tour", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState({
      tab: "dashboard",
      backend: "online",
      sessionApiReady: true,
      sessionId: null,
      projectId: null,
      onboardingDismissed: false,
      tourActive: false,
      tourStep: 0,
      tourSampleProjectId: null,
      toasts: [],
    });
  });

  it("dismisses welcome card without interrupting when user chooses 'Şimdi değil'", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <OnboardingWelcomeCard />
      </QueryClientProvider>,
    );

    expect(screen.getByText(/HYDRO'ya hoş geldiniz/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Şimdi değil/i }));

    expect(useAppStore.getState().onboardingDismissed).toBe(true);
    expect(useAppStore.getState().tourActive).toBe(false);

    rerender(
      <QueryClientProvider client={qc}>
        {!useAppStore.getState().onboardingDismissed ? <OnboardingWelcomeCard /> : null}
      </QueryClientProvider>,
    );
    expect(screen.queryByText(/HYDRO'ya hoş geldiniz/i)).not.toBeInTheDocument();
  });

  it("generates a sample project on user opt-in, steps 1/5 -> 5/5, and cleans up sample project on finish", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });

      if (url.endsWith("/api/projects/generate-sample")) {
        return new Response(
          JSON.stringify({
            project: {
              id: "proj-demo-99",
              name: "Demo Boru Hattı (Rehber)",
              code: "DEMO-TUR",
              status: "active",
            },
            sections: [
              {
                id: "sess-demo-1",
                name: "Demo Kesit 01",
                status: "active",
                revision: 1,
              },
            ],
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/sessions/sess-demo-1") && !url.endsWith("/results")) {
        return new Response(
          JSON.stringify({
            id: "sess-demo-1",
            name: "Demo Kesit 01",
            status: "active",
            revision: 1,
            inputs: createEmptyInputs(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/projects/proj-demo-99")) {
        return new Response(null, { status: 204 });
      }

      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Harness() {
      const onboardingDismissed = useAppStore((s) => s.onboardingDismissed);
      const tourActive = useAppStore((s) => s.tourActive);
      return (
        <div>
          {!onboardingDismissed && !tourActive ? <OnboardingWelcomeCard /> : null}
          <GuidedTourOverlay />
        </div>
      );
    }

    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Rehberli Demo Turunu Başlat/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /1 \/ 5 · Proje & Kesit Seçimi/i })).toBeInTheDocument();
    });
    expect(useAppStore.getState().tourSampleProjectId).toBe("proj-demo-99");
    expect(useAppStore.getState().tab).toBe("projects");

    fireEvent.click(screen.getByRole("button", { name: /İleri \(2\/5\)/i }));
    expect(useAppStore.getState().tab).toBe("geometry");

    fireEvent.click(screen.getByRole("button", { name: /İleri \(3\/5\)/i }));
    expect(useAppStore.getState().tab).toBe("ocr");

    fireEvent.click(screen.getByRole("button", { name: /İleri \(4\/5\)/i }));
    expect(useAppStore.getState().tab).toBe("air");

    fireEvent.click(screen.getByRole("button", { name: /İleri \(5\/5\)/i }));
    expect(useAppStore.getState().tab).toBe("reports");

    fireEvent.click(screen.getByRole("button", { name: /Örnek projeyi temizle ve bitir/i }));
    await waitFor(() => {
      expect(calls.some((c) => c.method === "DELETE" && c.url.includes("/api/projects/proj-demo-99"))).toBe(true);
    });
    expect(useAppStore.getState().tourActive).toBe(false);
    expect(useAppStore.getState().tab).toBe("projects");
  });

  it("falls back cleanly without setting anchor-name when viewport is narrow (<1024px)", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: !query.includes("1024px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      useAppStore.setState({ tourActive: true, tourStep: 0 });
      const { container } = render(
        <QueryClientProvider client={qc}>
          <div>
            <button type="button" data-tour="nav-projects">
              Projeler
            </button>
            <GuidedTourOverlay />
          </div>
        </QueryClientProvider>,
      );

      const navBtn = container.querySelector('[data-tour="nav-projects"]') as HTMLElement;
      const dialog = container.querySelector("dialog.hydro-tour-popover") as HTMLDialogElement;
      expect(dialog).toHaveAttribute("data-anchor", "fallback");
      expect(navBtn.style.getPropertyValue("anchor-name")).toBe("");
      expect(navBtn.classList.contains("tour-highlight-target")).toBe(false);
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it("cleans up newly created sample project if loading its first section fails", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });

      if (url.endsWith("/api/projects/generate-sample")) {
        return new Response(
          JSON.stringify({
            reused: false,
            project: {
              id: "proj-demo-99",
              name: "Demo Boru Hattı (Rehber)",
              code: "DEMO-TUR",
              status: "active",
            },
            sections: [{ id: "sess-demo-1", name: "Demo Kesit 01", status: "active", revision: 1 }],
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/sessions/sess-demo-1")) {
        return new Response(JSON.stringify({ message: "boom" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/projects/proj-demo-99") && method === "DELETE") {
        return new Response(null, { status: 204 });
      }

      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <OnboardingWelcomeCard />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Rehberli Demo Turunu Başlat/i }));

    await waitFor(() => {
      expect(calls.some((c) => c.method === "DELETE" && c.url.includes("/api/projects/proj-demo-99"))).toBe(true);
    });
    expect(useAppStore.getState().tourActive).toBe(true);
    expect(useAppStore.getState().tourSampleProjectId).toBeNull();
  });

  it("starts demo tour with sample project when launched from HelpDialog", async () => {
    const origShowModal = HTMLDialogElement.prototype.showModal;
    const origClose = HTMLDialogElement.prototype.close;
    HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute("open", "");
    };
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
      this.removeAttribute("open");
    };

    const calls: Array<{ url: string; method: string }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });

      if (url.endsWith("/api/projects/generate-sample")) {
        return new Response(
          JSON.stringify({
            reused: true,
            project: { id: "proj-demo-77", name: "Demo", code: "DEMO-TUR", status: "active" },
            sections: [{ id: "sess-demo-77", name: "Kesit 1", status: "active", revision: 1 }],
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/sessions/sess-demo-77") && !url.endsWith("/results")) {
        return new Response(
          JSON.stringify({
            id: "sess-demo-77",
            name: "Kesit 1",
            status: "active",
            revision: 1,
            inputs: createEmptyInputs(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const onClose = vi.fn();
      render(
        <QueryClientProvider client={qc}>
          <HelpDialog open onClose={onClose} />
        </QueryClientProvider>,
      );

      fireEvent.click(screen.getByRole("button", { name: /Rehberli Demo Turunu Başlat/i }));

      await waitFor(() => {
        expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/api/projects/generate-sample"))).toBe(true);
      });
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(useAppStore.getState().tourActive).toBe(true);
      expect(useAppStore.getState().tourSampleProjectId).toBe("proj-demo-77");
    } finally {
      HTMLDialogElement.prototype.showModal = origShowModal;
      HTMLDialogElement.prototype.close = origClose;
    }
  });

  it("shows DEMO badge in TopBar for demo projects", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    useAppStore.setState({
      projectId: "proj-demo-1",
      projectCode: "DEMO-TUR",
      tourSampleProjectId: "proj-demo-1",
    });

    render(
      <QueryClientProvider client={qc}>
        <TopBar onOpenHelp={vi.fn()} />
      </QueryClientProvider>,
    );

    const badge = screen.getByTestId("topbar-demo-badge");
    expect(badge).toHaveTextContent("DEMO");
  });
});
