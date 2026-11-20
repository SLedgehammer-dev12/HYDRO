import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectImportModal } from "../../features/projects/SampleAndImportModals";
import { useSaveSession } from "../../hooks/queries";
import { ApiError, api } from "../../lib/api";
import { createDefaultInputs } from "../../lib/mock";
import type { Project, Session } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { RevisionConflictModal } from "./RevisionConflictModal";

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    ...render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>),
  };
}

function makeServerSession(revision: number, lengthM: number, tempC = 19): Session {
  const inputs = createDefaultInputs();
  inputs.geometry.length_m = lengthM;
  inputs.air.temperature_c = tempC;
  return {
    id: "sess-409",
    project_id: "proj-1",
    name: `Sunucu Kesit rev.${revision}`,
    status: "active",
    revision,
    inputs: inputs as unknown as Record<string, unknown>,
    wizard_state: null,
    result_summary: {},
    created_at: "2026-11-20T07:00:00Z",
    updated_at: "2026-11-20T08:15:00Z",
    deleted_at: null,
  };
}

function SaveTriggerHarness() {
  const saveSession = useSaveSession();
  return (
    <>
      <button type="button" onClick={() => saveSession.mutate()}>
        Oturumu Kaydet Test
      </button>
      <RevisionConflictModal />
    </>
  );
}

beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute("open", "");
    };
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute("open");
      this.dispatchEvent(new Event("close"));
    };
  }
});

describe("RevisionConflictModal & Desktop JSON Snapshot Import", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const localInputs = createDefaultInputs();
    localInputs.geometry.length_m = 16_000;
    localInputs.air.temperature_c = 24;
    useAppStore.setState({
      backend: "online",
      sessionApiReady: true,
      sessionId: "sess-409",
      sessionName: "Yerel Kesit",
      sessionStatus: "active",
      revision: 1,
      dirty: true,
      projectId: "proj-1",
      inputs: localInputs,
      revisionConflict: null,
      toasts: [],
    });
  });

  it("opens RevisionConflictModal on 409 save error and can load server version cleanly", async () => {
    const user = userEvent.setup();
    const serverSess = makeServerSession(3, 14_200, 19);

    vi.spyOn(api, "updateSession").mockRejectedValueOnce(
      new ApiError(409, "revision_conflict", "Çakışma", {
        expected_revision: 1,
        current_revision: 3,
        current: serverSess,
        diff: [],
      }),
    );

    renderWithQuery(<SaveTriggerHarness />);
    await user.click(screen.getByRole("button", { name: "Oturumu Kaydet Test" }));

    expect(await screen.findByText("Revizyon çakışması (HTTP 409)")).toBeInTheDocument();
    expect(screen.getByText("Hat uzunluğu L (m)")).toBeInTheDocument();
    expect(screen.getByText("Hava testi su sıcaklığı (°C)")).toBeInTheDocument();

    const safeBtn = screen.getByRole("button", { name: "Sunucu sürümünü yükle" });
    await waitFor(() => expect(safeBtn).toHaveFocus());

    await user.click(safeBtn);
    expect(useAppStore.getState().revisionConflict).toBeNull();
    expect(useAppStore.getState().revision).toBe(3);
    expect(useAppStore.getState().dirty).toBe(false);
    expect(useAppStore.getState().inputs.geometry.length_m).toBe(14_200);
    expect(useAppStore.getState().inputs.air.temperature_c).toBe(19);
  });

  it("supports per-row selection merge and refreshes on sequential 409 before succeeding", async () => {
    const user = userEvent.setup();
    const srvRev3 = makeServerSession(3, 14_000, 19);
    const srvRev4 = makeServerSession(4, 14_000, 17);
    const savedRev5 = makeServerSession(5, 16_000, 17);
    savedRev5.name = "Sunucu Kesit rev.4";

    useAppStore.getState().setRevisionConflict({
      sessionId: "sess-409",
      localRevision: 1,
      localName: "Sunucu Kesit rev.3",
      localStatus: "active",
      localProjectId: "proj-1",
      localInputs: useAppStore.getState().inputs,
      serverSession: srvRev3,
      serverDiff: [],
      sourceAction: "save_session",
      detectedAt: "2026-11-20T08:16:00Z",
    });

    const updateSpy = vi
      .spyOn(api, "updateSession")
      .mockRejectedValueOnce(
        new ApiError(409, "revision_conflict", "Yeni çakışma", {
          expected_revision: 3,
          current_revision: 4,
          current: srvRev4,
          diff: [],
        }),
      )
      .mockResolvedValueOnce(savedRev5);

    renderWithQuery(<RevisionConflictModal />);

    // Keep server air temperature (Sunucu) while keeping local length_m (Yerel)
    const airTempGroup = screen.getByRole("group", {
      name: /Hava testi su sıcaklığı.*sürüm seçimi/i,
    });
    const serverTempBtn = airTempGroup.querySelector("button:first-child") as HTMLButtonElement;
    await user.click(serverTempBtn);

    const mergeBtn = screen.getByRole("button", { name: /Seçilenleri birleştir/ });
    await user.click(mergeBtn);

    expect(
      await screen.findByText(/Sunucuda daha yeni bir revizyon \(rev\.4\) tespit edildi/),
    ).toBeInTheDocument();

    // Preserved user's server choice for air temperature, local length, plus new name diff from rev.4
    const mergeAgainBtn = screen.getByRole("button", {
      name: /Seçilenleri birleştir \(2 yerel · 1 sunucu\)/,
    });
    await user.click(mergeAgainBtn);

    await waitFor(() => expect(useAppStore.getState().revisionConflict).toBeNull());
    expect(updateSpy).toHaveBeenCalledTimes(2);
    expect(updateSpy.mock.calls[1][2]).toBe(4);
    const secondPayloadInputs = updateSpy.mock.calls[1][1].inputs as Record<string, Record<string, unknown>>;
    expect(secondPayloadInputs.geometry.length_m).toBe(16_000);
    expect(secondPayloadInputs.air.temperature_c).toBe(17);
    expect(useAppStore.getState().revision).toBe(5);
    expect(useAppStore.getState().dirty).toBe(false);
  });

  it("imports desktop JSON snapshot via ProjectImportModal with project_id and mapping notes", async () => {
    const user = userEvent.setup();
    const project: Project = {
      id: "proj-real-1",
      code: "PRJ-01",
      name: "Ana Hat Projesi",
      client: null,
      description: null,
      section_count: 1,
      created_at: "2026-11-20T07:00:00Z",
      updated_at: "2026-11-20T07:00:00Z",
    };
    const importedSession = makeServerSession(1, 5000, 20);
    importedSession.id = "sess-new-json";
    importedSession.project_id = project.id;
    importedSession.name = "JSON Kesit";

    const importSpy = vi.spyOn(api, "importSnapshot").mockResolvedValueOnce({
      session: importedSession,
      mapping: {
        converted: 6,
        skipped: ["field.pig_speed_m_per_s"],
        invalid_fields: [],
        warnings: ["Su backend etiketi varsayılana çekildi."],
      },
    });
    const onSessionImported = vi.fn();

    renderWithQuery(
      <ProjectImportModal
        open
        onClose={vi.fn()}
        projects={[project]}
        selectedProjectId={project.id}
        onSessionImported={onSessionImported}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Masaüstü JSON Snapshot/ }));
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const jsonFile = new File(
      [JSON.stringify({ schema_version: 1, geometry: { length_m: "5000" } })],
      "desktop_snapshot.json",
      { type: "application/json" },
    );
    await user.upload(fileInput, jsonFile);
    await user.click(screen.getByRole("button", { name: "İçe Aktar" }));

    expect(await screen.findByText(/Kesit oluşturuldu: JSON Kesit/)).toBeInTheDocument();
    expect(screen.getByText(/field\.pig_speed_m_per_s/)).toBeInTheDocument();
    expect(importSpy).toHaveBeenCalledWith({
      name: undefined,
      project_id: "proj-real-1",
      snapshot: { schema_version: 1, geometry: { length_m: "5000" } },
    });

    await user.click(screen.getByRole("button", { name: "Tamam / Oturuma geç" }));
    expect(onSessionImported).toHaveBeenCalledWith(importedSession);
  });

  it("handles snapshot_upload conflict strictly from serverDiff without leaking local edits", async () => {
    const user = userEvent.setup();
    const srvRev3 = makeServerSession(3, 14_000, 19);

    // Unrelated local edits must NOT appear for snapshot_upload
    useAppStore.getState().setRevisionConflict({
      sessionId: "sess-409",
      localRevision: 1,
      localName: "Farkli Yerel",
      localStatus: "active",
      localProjectId: "proj-1",
      localInputs: useAppStore.getState().inputs,
      serverSession: srvRev3,
      serverDiff: [{ path: "geometry.length_m", incoming: 21_000, server: 14_000 }],
      sourceAction: "snapshot_upload",
      detectedAt: "2026-11-20T08:20:00Z",
      pendingSnapshot: { snapshot: { schema_version: 1, geometry: { length_m: "21000" } }, mode: "merge" },
    });

    const snapSpy = vi.spyOn(api, "snapshotUpload").mockResolvedValueOnce({
      ...srvRev3,
      revision: 4,
      mapping: { converted: 1, skipped: [], invalid_fields: [], warnings: [] },
    });
    vi.spyOn(api, "results").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    renderWithQuery(<RevisionConflictModal />);
    expect(screen.getByText("Hat uzunluğu L (m)")).toBeInTheDocument();
    expect(screen.queryByText("Hava testi su sıcaklığı (°C)")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Snapshot'ı rev\.3 üzerine uygula/ }));
    await waitFor(() => expect(useAppStore.getState().revisionConflict).toBeNull());
    expect(snapSpy).toHaveBeenCalledWith(
      "sess-409",
      { schema_version: 1, geometry: { length_m: "21000" } },
      3,
      "merge",
    );
  });

  it("promotes save_result merge state cleanly when secondary saveResult hits 409", async () => {
    const user = userEvent.setup();
    const srvRev3 = makeServerSession(3, 14_000, 19);
    const srvRev4 = makeServerSession(4, 16_000, 24);
    srvRev4.name = "Sunucu Kesit rev.3";
    const srvRev5 = makeServerSession(5, 16_000, 24);
    srvRev5.name = "Sunucu Kesit rev.3";

    useAppStore.getState().setRevisionConflict({
      sessionId: "sess-409",
      localRevision: 1,
      localName: "Sunucu Kesit rev.3",
      localStatus: "active",
      localProjectId: "proj-1",
      localInputs: useAppStore.getState().inputs,
      serverSession: srvRev3,
      serverDiff: [],
      sourceAction: "save_result",
      detectedAt: "2026-11-20T08:25:00Z",
      pendingResult: { testType: "air", payload: { ok: true } },
    });

    vi.spyOn(api, "updateSession").mockResolvedValueOnce(srvRev4);
    vi.spyOn(api, "results").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    const saveResultSpy = vi
      .spyOn(api, "saveResult")
      .mockRejectedValueOnce(
        new ApiError(409, "revision_conflict", "Çakışma", {
          expected_revision: 4,
          current_revision: 5,
          current: srvRev5,
          diff: [],
        }),
      )
      .mockResolvedValueOnce({
        id: "res-1",
        test_type: "air",
        decision: { status: "BASARILI", title: "Uygun", summary: "Tamam", rule: "NGTL" },
        session_revision: 5,
      });

    renderWithQuery(<RevisionConflictModal />);
    await user.click(screen.getByRole("button", { name: /Yerel değişiklikleri rev\.3 üzerine yaz/ }));

    expect(
      await screen.findByText(/Sunucuda daha yeni bir revizyon \(rev\.5\) tespit edildi/),
    ).toBeInTheDocument();
    expect(useAppStore.getState().revisionConflict?.localRevision).toBe(4);
    expect(useAppStore.getState().revisionConflict?.serverSession.revision).toBe(5);

    await user.click(screen.getByRole("button", { name: /Sonucu rev\.5 ile kaydet/ }));
    await waitFor(() => expect(useAppStore.getState().revisionConflict).toBeNull());
    expect(saveResultSpy).toHaveBeenCalledTimes(2);
    expect(saveResultSpy.mock.calls[1][2]).toBe(5);
  });

  it("clears projectId when importing standalone desktop JSON without a project", async () => {
    const user = userEvent.setup();
    const standalone = makeServerSession(1, 3000, 15);
    standalone.id = "sess-standalone";
    standalone.project_id = null;
    standalone.name = "Bağımsız Kesit";

    vi.spyOn(api, "importSnapshot").mockResolvedValueOnce({
      session: standalone,
      mapping: { converted: 3, skipped: [], invalid_fields: [], warnings: [] },
    });
    vi.spyOn(api, "results").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    renderWithQuery(
      <ProjectImportModal
        open
        onClose={vi.fn()}
        projects={[]}
        selectedProjectId={null}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Masaüstü JSON Snapshot/ }));
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const jsonFile = new File(
      [JSON.stringify({ schema_version: 1, geometry: { length_m: "3000" } })],
      "standalone.json",
      { type: "application/json" },
    );
    await user.upload(fileInput, jsonFile);
    await user.click(screen.getByRole("button", { name: "İçe Aktar" }));

    await waitFor(() => expect(useAppStore.getState().sessionId).toBe("sess-standalone"));
    expect(useAppStore.getState().projectId).toBeNull();
  });
});
