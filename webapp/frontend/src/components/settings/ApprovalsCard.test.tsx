import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { ApprovalsCard } from "./ApprovalsCard";
import type { ApprovalRequestItem, AuthMeResponse } from "../../lib/types";

const AUTH_ME: AuthMeResponse = {
  auth_mode: "oidc",
  enforced_auth: true,
  authenticated: true,
  user: {
    sub: "sup-1",
    email: "sup@botas.local",
    name: "Supervisor One",
    role: "supervisor",
  },
};

const ITEMS: ApprovalRequestItem[] = [
  {
    id: "app-1",
    action: "session_finalize",
    target_id: "sess-101",
    status: "pending",
    requested_by: "operator:op-1",
    requested_role: "operator",
    approved_by: null,
    approved_role: null,
    reason: "Saha kontrolleri tamamlandi",
    decision_note: "",
    created_at: "2026-11-24T20:00:00Z",
    decided_at: null,
    consumed_at: null,
  },
  {
    id: "app-2",
    action: "db_restore",
    target_id: "hydro_backup.db",
    status: "consumed",
    requested_by: "admin:adm-1",
    requested_role: "admin",
    approved_by: "admin:adm-2",
    approved_role: "admin",
    reason: "Kurtarma tatbikati",
    decision_note: "Onaylandi",
    created_at: "2026-11-24T19:00:00Z",
    decided_at: "2026-11-24T19:05:00Z",
    consumed_at: "2026-11-24T19:06:00Z",
  },
];

describe("ApprovalsCard (R4)", () => {
  it("submits approval request, handles approve/reject, and passes axe check", async () => {
    const onCreate = vi.fn();
    const onDecide = vi.fn();

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <ApprovalsCard authMe={AUTH_ME} approvals={ITEMS} onCreate={onCreate} onDecide={onDecide} />
      </QueryClientProvider>,
    );

    expect(screen.getByText(/OIDC etkin/i)).toBeTruthy();
    expect(screen.getByText(/1 bekliyor/i)).toBeTruthy();
    expect(screen.getByText("sess-101")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /sess-101 talebini onayla/i }));
    expect(onDecide).toHaveBeenCalledWith("app-1", "approved");

    fireEvent.click(screen.getByRole("button", { name: /sess-101 talebini reddet/i }));
    expect(onDecide).toHaveBeenCalledWith("app-1", "rejected");

    const targetInput = screen.getByPlaceholderText(/Oturum ID veya yedek dosya adı/i);
    fireEvent.change(targetInput, { target: { value: "sess-202" } });
    fireEvent.click(screen.getByRole("button", { name: /Talep Oluştur/i }));
    expect(onCreate).toHaveBeenCalledWith({
      action: "session_finalize",
      target_id: "sess-202",
      reason: "",
    });

    const results = await axe.run(container, {
      rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
    });
    const severe = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(severe).toEqual([]);
  });
});
