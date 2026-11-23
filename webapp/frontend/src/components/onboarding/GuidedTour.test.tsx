import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyInputs } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";
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
});
