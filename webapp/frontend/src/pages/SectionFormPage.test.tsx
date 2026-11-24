import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import type { SectionFormRecord, SessionFormsResponse } from "../lib/types";
import { clearFormDraft, saveFormDraft } from "../features/forms/formDraftStorage";
import { useAppStore } from "../store/useAppStore";
import { SectionFormPage } from "./SectionFormPage";

const mockUpdateSessionForm = vi.fn();
const mockSessionForms = vi.fn();

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      sessionForms: (...args: unknown[]) => mockSessionForms(...args),
      updateSessionForm: (...args: unknown[]) => mockUpdateSessionForm(...args),
      sessionResults: vi.fn().mockResolvedValue({ items: [] }),
    },
  };
});

function makeFormsPayload(revision: number, notes: string): SessionFormsResponse {
  const cleaningForm: SectionFormRecord = {
    id: "form-cleaning-1",
    form_code: "cleaning",
    botas_code: "BOT-FRM-İNB-001-016",
    form_title: "Temizlik Raporu",
    required: true,
    order: 2,
    status: "filled",
    analysis_id: null,
    source_filename: "",
    pages: [1],
    form_date: "2026-11-23",
    extracted_data: { notes },
    findings: [],
    warnings: [],
    revision,
    filled_at: "2026-11-23T08:00:00Z",
    updated_at: "2026-11-23T08:00:00Z",
  };
  return {
    session_id: "sess-1",
    project_id: "proj-1",
    section_no: "BÖLÜM 1",
    session_name: "Kesit 1",
    summary: {
      required_total: 11,
      filled_required: 1,
      missing_required: 10,
      missing_titles: [],
      supplementary_filled: 0,
      failed_forms: [],
      complete: false,
    },
    merged_header: {},
    calculations: {},
    forms: [cleaningForm],
    missing_required_forms: [],
    checkpoints: [],
  };
}

describe("SectionFormPage optimistic concurrency (F1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearFormDraft("sess-1", "cleaning");
    useAppStore.setState({
      backend: "online",
      sessionId: "sess-1",
      sessionName: "Kesit 1",
      projectName: "Test Proje",
      activeFormCode: "cleaning",
    });
  });

  it("sends current revision via If-Match and handles 409 revision_conflict with force-overwrite", async () => {
    const initialPayload = makeFormsPayload(2, "Yerel başlangıç notu");
    const serverUpdatedForm = makeFormsPayload(3, "Sunucudaki yeni not").forms[0];

    mockSessionForms.mockResolvedValue(initialPayload);
    mockUpdateSessionForm
      .mockRejectedValueOnce(
        new ApiError(409, "revision_conflict", "Form başka bir sekmede güncellendi.", {
          expected_revision: 2,
          current_revision: 3,
          current: serverUpdatedForm,
        }),
      )
      .mockResolvedValueOnce({
        form: { ...serverUpdatedForm, revision: 4 },
        session: {
          id: "sess-1",
          name: "Kesit 1",
          status: "draft",
          revision: 5,
          project_id: "proj-1",
          inputs: {},
          created_at: "2026-11-23T08:00:00Z",
          updated_at: "2026-11-23T08:05:00Z",
        },
        forms_payload: makeFormsPayload(4, "Benim üzerine yazdığım not"),
      });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <SectionFormPage />
      </QueryClientProvider>,
    );

    await screen.findByDisplayValue("2026-11-23");
    const saveBtn = await screen.findByRole("button", { name: /Kaydet & Kontrol Et/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateSessionForm).toHaveBeenCalledTimes(1);
    });
    // Expect revision 2 passed as 4th argument (ifMatch)
    expect(mockUpdateSessionForm.mock.calls[0][3]).toBe(2);

    // 409 conflict banner appears with both recovery buttons
    expect(await screen.findByText(/başka bir sekme veya kullanıcı/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Sunucudaki Güncel Formu Yükle/i })).toBeTruthy();
    const overwriteBtn = screen.getByRole("button", { name: /Değişikliklerimle Üzerine Yaz/i });

    fireEvent.click(overwriteBtn);
    await waitFor(() => {
      expect(mockUpdateSessionForm).toHaveBeenCalledTimes(2);
    });
    // Force overwrite sends server's current_revision (3)
    expect(mockUpdateSessionForm.mock.calls[1][3]).toBe(3);
  });

  it("restores matching local draft on mount and clears it when discarded (R7)", async () => {
    mockSessionForms.mockResolvedValue(makeFormsPayload(2, "Sunucu notu"));
    saveFormDraft("sess-1", "cleaning", {
      formDate: "2026-11-24",
      extractedData: { notes: "Yerel taslak notu" },
      baseRevision: 2,
      savedAt: "2026-11-24T12:00:00Z",
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <SectionFormPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Yerel taslak geri yüklendi/i)).toBeTruthy();
    expect(screen.getByDisplayValue("2026-11-24")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Taslağı temizle/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Yerel taslak geri yüklendi/i)).toBeNull();
    });
    expect(screen.getByDisplayValue("2026-11-23")).toBeTruthy();
  });
});
