import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "../components/layout/TopBar";
import { GuidedTourOverlay } from "../components/onboarding/GuidedTourOverlay";
import { OnboardingWelcomeCard } from "../components/onboarding/OnboardingWelcomeCard";
import { DashboardPage } from "../pages/DashboardPage";
import { useAppStore } from "../store/useAppStore";

const stylesCss = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function parseThemeTokens(css: string, selector: string): Record<string, string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`));
  if (!match) return {};
  const tokens: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const varMatch = line.match(/^\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/);
    if (varMatch) tokens[varMatch[1]] = varMatch[2];
  }
  return tokens;
}

function relativeLuminance(hex: string): number {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  const toLinear = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

function contrastRatio(fgHex: string, bgHex: string): number {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  const [bright, dark] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (bright + 0.05) / (dark + 0.05);
}

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

  it("enforces WCAG AA contrast ratios for dark & light theme CSS tokens and reduced-motion rules (R22)", () => {
    expect(stylesCss).toContain("@media (prefers-reduced-motion: reduce)");

    const themes = [
      { name: "dark", tokens: parseThemeTokens(stylesCss, ":root") },
      { name: "light", tokens: parseThemeTokens(stylesCss, '[data-theme="light"]') },
    ];

    const requiredPairs: Array<[string, string, number]> = [
      ["--text", "--surface", 4.5],
      ["--text", "--canvas", 4.5],
      ["--text-soft", "--surface", 4.5],
      ["--text-muted", "--surface", 4.5],
      ["--primary-ink", "--primary", 4.5],
      ["--primary", "--surface", 4.5],
      ["--danger", "--surface", 4.5],
      ["--warning", "--surface", 4.5],
      ["--success", "--surface", 4.5],
    ];

    for (const theme of themes) {
      for (const [fg, bg, minRatio] of requiredPairs) {
        const fgHex = theme.tokens[fg];
        const bgHex = theme.tokens[bg];
        expect(fgHex, `${theme.name} missing ${fg}`).toMatch(/^#[0-9a-fA-F]{6}$/);
        expect(bgHex, `${theme.name} missing ${bg}`).toMatch(/^#[0-9a-fA-F]{6}$/);
        const ratio = contrastRatio(fgHex, bgHex);
        expect(
          ratio,
          `${theme.name} contrast ${fg} (${fgHex}) on ${bg} (${bgHex}) = ${ratio.toFixed(2)} < ${minRatio}`,
        ).toBeGreaterThanOrEqual(minRatio);
      }
    }
  });
});
