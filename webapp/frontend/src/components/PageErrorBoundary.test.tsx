import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PageErrorBoundary } from "./PageErrorBoundary";

function ThrowingChild({ error }: { error: Error }): null {
  throw error;
}

describe("PageErrorBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Tekrar dene without reload CTA on regular runtime errors", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <PageErrorBoundary title="Sayfa hatası">
        <ThrowingChild error={new Error("Hesap hatası")} />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("Sayfa hatası")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tekrar dene/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sayfayı yenile/i })).not.toBeInTheDocument();
  });

  it("offers hard page reload when dynamic chunk loading fails", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <PageErrorBoundary title="Sayfa hatası">
        <ThrowingChild error={new TypeError("Failed to fetch dynamically imported module")} />
      </PageErrorBoundary>,
    );

    expect(screen.getByRole("button", { name: /Sayfayı yenile/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tekrar dene/i })).not.toBeInTheDocument();
  });
});
