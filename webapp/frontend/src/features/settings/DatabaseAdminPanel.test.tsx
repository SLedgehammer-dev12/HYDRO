import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useProjects, useSaveSession } from "../../hooks/queries";
import { getAdminToken, setAdminToken } from "../../lib/api";
import { DEMO_META } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";
import { DatabaseAdminPanel } from "./DatabaseAdminPanel";

describe("Slice 2: Docker Admin Token UI (F4) & Offline Fallback Hardening (F3)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    useAppStore.setState({
      backend: "online",
      sessionApiReady: true,
      toasts: [],
      dirty: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("F4: saves admin token to sessionStorage and sends X-Hydro-Admin-Token on /system/* requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      const hdrs = new Headers(init?.headers);
      if (url.endsWith("/meta")) {
        return new Response(
          JSON.stringify({
            ...DEMO_META,
            features: {
              ...DEMO_META.features,
              admin_token_configured: true,
              is_loopback_host: false,
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/system/db-stats")) {
        if (hdrs.get("X-Hydro-Admin-Token") !== "docker-secret-42") {
          return new Response(
            JSON.stringify({
              code: "admin_token_required",
              message: "Veritabani yonetim islemleri icin gecerli X-Hydro-Admin-Token gereklidir.",
            }),
            { status: 403, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(
          JSON.stringify({
            dialect: "sqlite",
            is_sqlite: true,
            schema_migration: "0003",
            integrity_status: "ok",
            journal_mode: "wal",
            db_size_bytes: 4096,
            wal_size_bytes: 0,
            workspace_count: 1,
            storage: {
              uploads_bytes: 0,
              uploads_files: 0,
              exports_bytes: 0,
              exports_files: 0,
              backups_bytes: 0,
              backups_count: 0,
            },
            table_counts: { projects: 2, sessions: 4, section_forms: 16 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <DatabaseAdminPanel />
      </QueryClientProvider>,
    );

    const tokenInput = await screen.findByPlaceholderText(/X-Hydro-Admin-Token/i);
    fireEvent.change(tokenInput, { target: { value: "docker-secret-42" } });
    fireEvent.click(screen.getByRole("button", { name: /Anahtarı Kaydet/i }));

    expect(getAdminToken()).toBe("docker-secret-42");
    await waitFor(() => {
      expect(screen.getByText(/Bütünlük OK/i)).toBeTruthy();
    });
    expect(fetchSpy).toHaveBeenCalled();
    setAdminToken("");
    expect(getAdminToken()).toBe("");
  });

  it("F3: transient read failure does not flip global backend to demo, and offline save warns + tracks pendingServerSync", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result: projHook } = renderHook(() => useProjects(), { wrapper });
    await waitFor(() => {
      expect(projHook.current.isFetched).toBe(true);
    });
    // Global backend must remain "online" after a single transient query error
    expect(useAppStore.getState().backend).toBe("online");

    // When genuinely in demo/offline mode, saving pushes a warning toast and sets pendingServerSync
    useAppStore.setState({ backend: "demo", toasts: [], dirty: true, pendingServerSync: false });
    const { result: saveHook } = renderHook(() => useSaveSession(), { wrapper });
    await saveHook.current.mutateAsync();

    const st = useAppStore.getState();
    expect(st.pendingServerSync).toBe(true);
    expect(st.toasts.some((t) => t.tone === "warning")).toBe(true);
    expect(st.toasts.some((t) => t.tone === "success")).toBe(false);
  });
});
