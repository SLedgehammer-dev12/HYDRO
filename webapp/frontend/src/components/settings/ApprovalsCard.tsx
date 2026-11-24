import { useState, type FormEvent } from "react";
import { Check, Plus, ShieldCheck, X } from "lucide-react";
import { SectionCard } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { InlineNotice } from "../ui/State";
import {
  useApprovals,
  useAuthMe,
  useCreateApproval,
  useDecideApproval,
} from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import type { ApprovalAction, ApprovalRequestItem, AuthMeResponse } from "../../lib/types";

const ACTION_LABELS: Record<ApprovalAction, string> = {
  session_finalize: "Oturum Nihai Onay",
  db_restore: "Veritabanı Geri Yükleme",
};

const STATUS_BADGE: Record<
  ApprovalRequestItem["status"],
  { label: string; tone: "pending" | "pass" | "fail" | "info" }
> = {
  pending: { label: "Bekliyor", tone: "pending" },
  approved: { label: "Onaylı", tone: "pass" },
  rejected: { label: "Reddedildi", tone: "fail" },
  consumed: { label: "Kullanıldı", tone: "info" },
};

export interface ApprovalsCardProps {
  authMe?: AuthMeResponse;
  approvals?: ApprovalRequestItem[];
  onCreate?: (payload: { action: ApprovalAction; target_id: string; reason: string }) => void;
  onDecide?: (approvalId: string, decision: "approved" | "rejected") => void;
  busy?: boolean;
}

export function ApprovalsCard({
  authMe: authMeProp,
  approvals: approvalsProp,
  onCreate,
  onDecide,
  busy: busyProp,
}: ApprovalsCardProps) {
  const backend = useAppStore((state) => state.backend);
  const sessionId = useAppStore((state) => state.sessionId);
  const authMeQuery = useAuthMe();
  const approvalsQuery = useApprovals();
  const createMut = useCreateApproval();
  const decideMut = useDecideApproval();

  const authMe = authMeProp ?? authMeQuery.data;
  const approvals = approvalsProp ?? approvalsQuery.data ?? [];
  const busy = busyProp ?? (createMut.isPending || decideMut.isPending);

  const [action, setAction] = useState<ApprovalAction>("session_finalize");
  const [targetId, setTargetId] = useState(sessionId || "");
  const [reason, setReason] = useState("");

  const pendingCount = approvals.filter((item) => item.status === "pending").length;
  const isOnlineOrInjected =
    backend === "online" || approvalsProp !== undefined || onCreate !== undefined;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = targetId.trim();
    if (!trimmed) return;
    if (onCreate) {
      onCreate({ action, target_id: trimmed, reason: reason.trim() });
    } else {
      createMut.mutate({ action, target_id: trimmed, reason: reason.trim() });
    }
    setReason("");
  }

  function handleDecide(id: string, decision: "approved" | "rejected") {
    if (onDecide) {
      onDecide(id, decision);
    } else {
      decideMut.mutate({ approvalId: id, decision });
    }
  }

  return (
    <SectionCard
      title="İki Kişi Onayları ve Yetkilendirme"
      description="Oturum nihai işaretleme ve veritabanı geri yükleme için ikinci personel onayı."
      icon={ShieldCheck}
      action={
        <div className="flex items-center gap-1.5">
          <Badge tone={authMe?.enforced_auth ? "pass" : "info"}>
            {authMe?.enforced_auth ? "OIDC etkin" : "Yerel kip"}
          </Badge>
          {pendingCount > 0 ? <Badge tone="pending">{pendingCount} bekliyor</Badge> : null}
        </div>
      }
    >
      {authMe?.enforced_auth && authMe.user ? (
        <InlineNotice tone="info" title="Aktif OIDC Oturumu">
          <strong>{authMe.user.name || authMe.user.sub}</strong> ({authMe.user.role})
          {authMe.user.email ? ` · ${authMe.user.email}` : ""}
        </InlineNotice>
      ) : (
        <InlineNotice tone="info" title="İki Kişi Onayı Kuralı">
          Talebi oluşturan kullanıcı kendi talebini onaylayamaz; farklı bir yetkili
          (supervisor/admin) onayı gerekir.
        </InlineNotice>
      )}

      <form onSubmit={handleSubmit} className="mt-3 grid gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
          <span>İşlem</span>
          <select
            value={action}
            onChange={(event) => setAction(event.target.value as ApprovalAction)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs text-[var(--text)]"
          >
            <option value="session_finalize">Oturum Nihai Onay</option>
            <option value="db_restore">Veritabanı Geri Yükleme</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
          <span>Hedef Kimliği / Dosya</span>
          <input
            type="text"
            value={targetId}
            onChange={(event) => setTargetId(event.target.value)}
            placeholder="Oturum ID veya yedek dosya adı"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs text-[var(--text)]"
          />
        </label>

        <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
          <span>Gerekçe</span>
          <input
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Kısa açıklama (opsiyonel)"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs text-[var(--text)]"
          />
        </label>

        <div className="flex items-end">
          <Button
            type="submit"
            size="sm"
            variant="primary"
            icon={<Plus size={13} />}
            disabled={!isOnlineOrInjected || !targetId.trim() || busy}
            className="w-full"
          >
            Talep Oluştur
          </Button>
        </div>
      </form>

      {approvals.length === 0 ? (
        <p className="mt-3 text-[11px] text-[var(--text-faint)]">Henüz onay talebi yok.</p>
      ) : (
        <div className="table-wrap scroll-thin mt-3">
          <table className="data">
            <caption className="sr-only">İki kişi onay talepleri listesi</caption>
            <thead>
              <tr>
                <th scope="col">İşlem</th>
                <th scope="col">Hedef</th>
                <th scope="col">Talep Eden</th>
                <th scope="col">Onaylayan</th>
                <th scope="col">Durum</th>
                <th scope="col" className="text-right">
                  Karar
                </th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((item) => {
                const badge = STATUS_BADGE[item.status] ?? {
                  label: item.status,
                  tone: "info" as const,
                };
                return (
                  <tr key={item.id}>
                    <td className="font-medium text-[var(--text)]">
                      {ACTION_LABELS[item.action] ?? item.action}
                    </td>
                    <td className="numeric text-[11px]">{item.target_id}</td>
                    <td className="text-[11px] text-[var(--text-muted)]">{item.requested_by}</td>
                    <td className="text-[11px] text-[var(--text-muted)]">
                      {item.approved_by ?? "—"}
                    </td>
                    <td>
                      <Badge tone={badge.tone}>{badge.label}</Badge>
                    </td>
                    <td className="text-right">
                      {item.status === "pending" ? (
                        <div className="inline-flex items-center gap-1">
                          <Button
                            size="sm"
                            variant="default"
                            icon={<Check size={12} />}
                            disabled={busy}
                            onClick={() => handleDecide(item.id, "approved")}
                            aria-label={`${item.target_id} talebini onayla`}
                          >
                            Onayla
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            icon={<X size={12} />}
                            disabled={busy}
                            onClick={() => handleDecide(item.id, "rejected")}
                            aria-label={`${item.target_id} talebini reddet`}
                          >
                            Reddet
                          </Button>
                        </div>
                      ) : (
                        <span className="text-[10.5px] text-[var(--text-faint)]">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
