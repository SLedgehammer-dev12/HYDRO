import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "../components/layout/TopBar";
import { GuidedTourOverlay } from "../components/onboarding/GuidedTourOverlay";
import { OnboardingWelcomeCard } from "../components/onboarding/OnboardingWelcomeCard";
import { DashboardPage } from "../pages/DashboardPage";
import { useAppStore } from "../store/useAppStore";

async function expectNoSeriousA11yViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false },
    },
  });
  const severe = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    severe.map((v) => `${v.id} (${v.impact}): ${v.help}`),
    `Expected zero critical/serious axe violations`,
  ).toEqual([]);
}

describe("Accessibility (R8): critical components and focus management", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState({
      tab: "dashboard",
      backend: "demo",
      sessionApiReady: false,
      onboardingDismissed: false,
      tourActive: false,
      tourStep: 0,
      tourSampleProjectId: null,
      toasts: [],
    });
  });

  it("TopBar has zero critical/serious axe violations", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <TopBar onOpenHelp={vi.fn()} />
      </QueryClientProvider>,
    );
    await expectNoSeriousA11yViolations(container);
  });

  it("OnboardingWelcomeCard has zero critical/serious axe violations", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <OnboardingWelcomeCard />
      </QueryClientProvider>,
    );
    await expectNoSeriousA11yViolations(container);
  });

  it("DashboardPage has zero critical/serious axe violations", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <DashboardPage />
      </QueryClientProvider>,
    );
    await expectNoSeriousA11yViolations(container);
  });

  it("GuidedTourOverlay passes axe and returns focus to trigger on Escape", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Harness() {
      const tourActive = useAppStore((s) => s.tourActive);
      const startTour = useAppStore((s) => s.startTour);
      return (
        <div>
          <button type="button" onClick={() => startTour(null)}>
            Turu Başlat
          </button>
          {tourActive ? <GuidedTourOverlay /> : null}
        </div>
      );
    }

    const { container } = render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    const trigger = screen.getByRole("button", { name: "Turu Başlat" });
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    fireEvent.click(trigger);
    expect(useAppStore.getState().tourActive).toBe(true);
    await expectNoSeriousA11yViolations(container);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(useAppStore.getState().tourActive).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });
});
