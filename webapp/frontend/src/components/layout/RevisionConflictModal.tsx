import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, GitCompareArrows, RefreshCw } from "lucide-react";
import { hydrateSessionResults } from "../../hooks/queries";
import { api, apiErrorMessage } from "../../lib/api";
import { dateTime, nowIso } from "../../lib/format";
import { toApiInputs } from "../../lib/normalize";
import {
  applyDiffResolutions,
  buildDiffFromServerEntries,
  computeSessionDiff,
  extractRevisionConflict,
  type SessionDiffItem,
} from "../../lib/sessionDiff";
import { useAppStore } from "../../store/useAppStore";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Dialog";
import { InlineNotice } from "../ui/State";

export function RevisionConflictModal() {
  const conflict = useAppStore((s) => s.revisionConflict);
  const setRevisionConflict = useAppStore((s) => s.setRevisionConflict);
  const applySessionInputs = useAppStore((s) => s.applySessionInputs);
  const setSessionMeta = useAppStore((s) => s.setSessionMeta);
  const markSaved = useAppStore((s) => s.markSaved);
  const pushToast = useAppStore((s) => s.pushToast);
  const projectId = useAppStore((s) => s.projectId);

  const queryClient = useQueryClient();
  const safeBtnRef = useRef<HTMLButtonElement>(null);
  const lastSessionIdRef = useRef<string | null>(null);
  const captionId = useId();

  const [busy, setBusy] = useState(false);
  const [choices, setChoices] = useState<Record<string, "local" | "server">>({});

  const diffItems = useMemo<SessionDiffItem[]>(() => {
    if (!conflict) return [];
    if (conflict.sourceAction === "snapshot_upload") {
      if (conflict.serverDiff.length > 0) {
        return buildDiffFromServerEntries(conflict.serverDiff);
      }
    }
    const localDiff = computeSessionDiff(
      {
        name: conflict.localName,
        status: conflict.localStatus,
        inputs: conflict.localInputs,
      },
      conflict.serverSession,
    );
    if (localDiff.length > 0) return localDiff;
    if (conflict.serverDiff.length > 0) {
      return buildDiffFromServerEntries(conflict.serverDiff);
    }
    return [];
  }, [conflict]);

  const conflictKey = conflict
    ? `${conflict.sessionId}:${conflict.serverSession.revision}:${conflict.detectedAt}`
    : "";

  useEffect(() => {
    if (!conflictKey || !conflict) {
      lastSessionIdRef.current = null;
      return;
    }
    const sameSessionRefresh =
      Boolean(conflict.refreshWarning) && lastSessionIdRef.current === conflict.sessionId;
    lastSessionIdRef.current = conflict.sessionId;

    setChoices((prev) => {
      const nextChoices: Record<string, "local" | "server"> = {};
      for (const item of diffItems) {
        nextChoices[item.path] = sameSessionRefresh ? (prev[item.path] ?? "local") : "local";
      }
      return nextChoices;
    });
    const frame = requestAnimationFrame(() => safeBtnRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [conflictKey, conflict, diffItems]);

  if (!conflict) return null;

  const canSelectPerField = conflict.sourceAction !== "snapshot_upload";
  const localChoiceCount = diffItems.filter(
    (item) => (choices[item.path] ?? "local") === "local",
  ).length;
  const serverChoiceCount = diffItems.length - localChoiceCount;
  const allServerSelected = diffItems.length > 0 && localChoiceCount === 0;
  const allLocalSelected = diffItems.length > 0 && serverChoiceCount === 0;

  function setAllChoices(target: "local" | "server") {
    const next: Record<string, "local" | "server"> = {};
    for (const item of diffItems) {
      next[item.path] = target;
    }
    setChoices(next);
  }

  function setRowChoice(path: string, value: "local" | "server") {
    setChoices((prev) => ({ ...prev, [path]: value }));
  }

  function loadServerVersion() {
    if (!conflict) return;
    const srv = conflict.serverSession;
    applySessionInputs(srv.inputs);
    setSessionMeta({
      id: srv.id,
      name: srv.name,
      status: srv.status,
      revision: srv.revision,
    });
    markSaved(srv.revision);
    setRevisionConflict(null);
    queryClient.setQueryData(["session", srv.id], srv);
    void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
    void hydrateSessionResults(srv.id);
    pushToast(
      "info",
      "Sunucu sürümü yüklendi",
      `${srv.name} · Revizyon ${srv.revision} çalışma alanına uygulandı.`,
    );
  }

  async function resolveWithServerRevision() {
    if (!conflict || busy) return;
    setBusy(true);

    try {
      const serverRev = conflict.serverSession.revision;

      if (conflict.sourceAction === "snapshot_upload" && conflict.pendingSnapshot) {
        const updated = await api.snapshotUpload(
          conflict.sessionId,
          conflict.pendingSnapshot.snapshot,
          serverRev,
          conflict.pendingSnapshot.mode,
        );
        applySessionInputs(updated.inputs);
        setSessionMeta({
          id: updated.id,
          name: updated.name,
          status: updated.status,
          revision: updated.revision,
        });
        markSaved(updated.revision);
        setRevisionConflict(null);
        queryClient.setQueryData(["session", updated.id], updated);
        void queryClient.invalidateQueries({ queryKey: ["sessions"] });
        void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
        pushToast(
          "success",
          "Snapshot güncellenen revizyon üzerine uygulandı",
          `Revizyon ${updated.revision} · ${updated.mapping?.converted ?? 0} alan dönüştürüldü.`,
        );
        return;
      }

      if (
        conflict.sourceAction === "save_result" &&
        conflict.pendingResult &&
        diffItems.length === 0
      ) {
        const savedResult = await api.saveResult(
          conflict.sessionId,
          {
            test_type: conflict.pendingResult.testType,
            payload: conflict.pendingResult.payload,
          },
          serverRev,
        );
        const srv = conflict.serverSession;
        applySessionInputs(srv.inputs);
        setSessionMeta({
          id: srv.id,
          name: srv.name,
          status: srv.status,
          revision: savedResult.session_revision || srv.revision,
        });
        markSaved(savedResult.session_revision || srv.revision);
        setRevisionConflict(null);
        void queryClient.invalidateQueries({ queryKey: ["session-forms", srv.id] });
        void queryClient.invalidateQueries({ queryKey: ["sessions"] });
        void queryClient.invalidateQueries({ queryKey: ["session", srv.id] });
        pushToast(
          "success",
          "Test sonucu güncel revizyona kaydedildi",
          `${srv.name} · Revizyon ${savedResult.session_revision || srv.revision}`,
        );
        return;
      }

      const merged = applyDiffResolutions(
        {
          name: conflict.localName,
          status: conflict.localStatus,
          inputs: conflict.localInputs,
        },
        conflict.serverSession,
        choices,
      );
      const realProjectId =
        projectId && !projectId.startsWith("demo-")
          ? projectId
          : conflict.serverSession.project_id;

      const updated = await api.updateSession(
        conflict.sessionId,
        {
          name: merged.name,
          status: merged.status,
          project_id: realProjectId,
          inputs: toApiInputs(merged.inputs),
        },
        serverRev,
      );

      applySessionInputs(updated.inputs);
      setSessionMeta({
        id: updated.id,
        name: updated.name,
        status: updated.status,
        revision: updated.revision,
      });
      markSaved(updated.revision);
      queryClient.setQueryData(["session", updated.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });

      if (conflict.sourceAction === "save_result" && conflict.pendingResult) {
        if (allLocalSelected) {
          await api.saveResult(
            updated.id,
            {
              test_type: conflict.pendingResult.testType,
              payload: conflict.pendingResult.payload,
            },
            updated.revision,
          );
          void queryClient.invalidateQueries({ queryKey: ["session-forms", updated.id] });
          setRevisionConflict(null);
          pushToast(
            "success",
            "Çakışma çözüldü ve test sonucu kaydedildi",
            `Revizyon ${updated.revision} · ${new Date().toLocaleTimeString("tr-TR")}`,
          );
        } else {
          setRevisionConflict(null);
          pushToast(
            "warning",
            "Birleştirilmiş girdiler kaydedildi",
            "Sunucu alanları da korunduğu için ilgili test sonucunu güncel girdilerle yeniden hesaplatın.",
          );
        }
        return;
      }

      setRevisionConflict(null);
      pushToast(
        "success",
        allLocalSelected || diffItems.length === 0
          ? "Yerel değişiklikler üzerine kaydedildi"
          : "Değişiklikler birleştirilip kaydedildi",
        `Revizyon ${updated.revision} · ${localChoiceCount} yerel, ${serverChoiceCount} sunucu alanı uygulandı.`,
      );
    } catch (error) {
      const newer = extractRevisionConflict(error);
      if (newer) {
        setRevisionConflict({
          ...conflict,
          serverSession: newer.serverSession,
          serverDiff: newer.serverDiff,
          detectedAt: nowIso(),
          refreshWarning: `Sunucuda daha yeni bir revizyon (rev.${newer.currentRevision}) tespit edildi; fark tablosu güncellendi.`,
        });
        return;
      }
      pushToast("error", "Çakışma çözülemedi", apiErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const actionContextLabel =
    conflict.sourceAction === "snapshot_upload"
      ? "Snapshot yükleme sırasında revizyon uyuşmazlığı oluştu."
      : conflict.sourceAction === "save_result"
        ? "Test sonucu kaydedilirken sunucuda daha yeni bir kesit revizyonu bulundu."
        : "Oturum kaydedilirken sunucuda daha yeni bir kesit revizyonu bulundu.";

  const primaryLabel =
    conflict.sourceAction === "snapshot_upload"
      ? `Snapshot'ı rev.${conflict.serverSession.revision} üzerine uygula`
      : diffItems.length === 0 && conflict.sourceAction === "save_result"
        ? `Sonucu rev.${conflict.serverSession.revision} ile kaydet`
        : allLocalSelected || diffItems.length === 0
          ? `Yerel değişiklikleri rev.${conflict.serverSession.revision} üzerine yaz`
          : `Seçilenleri birleştir (${localChoiceCount} yerel · ${serverChoiceCount} sunucu)`;

  return (
    <Modal
      open
      dismissible={!busy}
      onClose={() => {
        if (!busy) setRevisionConflict(null);
      }}
      className="modal-dialog-wide"
      title="Revizyon çakışması (HTTP 409)"
      description={actionContextLabel}
      footer={
        <>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => setRevisionConflict(null)}
          >
            Kapat
          </Button>
          <Button
            ref={safeBtnRef}
            variant={allServerSelected ? "primary" : "ghost"}
            icon={<RefreshCw size={14} />}
            disabled={busy}
            onClick={loadServerVersion}
          >
            Sunucu sürümünü yükle
          </Button>
          {!allServerSelected ? (
            <Button
              variant="primary"
              icon={<Check size={14} />}
              loading={busy}
              onClick={() => void resolveWithServerRevision()}
            >
              {primaryLabel}
            </Button>
          ) : null}
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <GitCompareArrows size={15} className="text-[var(--warning)]" aria-hidden />
            <span className="font-semibold text-[var(--text)]">
              {conflict.serverSession.name}
            </span>
            <Badge tone="warning">Yerel rev.{conflict.localRevision}</Badge>
            <Badge tone="info">Sunucu rev.{conflict.serverSession.revision}</Badge>
          </div>
          <span className="text-[11px] text-[var(--text-faint)]">
            Sunucu güncellemesi: {dateTime(conflict.serverSession.updated_at)}
          </span>
        </div>

        {conflict.refreshWarning ? (
          <InlineNotice tone="warning" title="Yeni sunucu revizyonu" icon={AlertTriangle}>
            {conflict.refreshWarning}
          </InlineNotice>
        ) : null}

        {canSelectPerField && diffItems.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px]">
            <span className="text-[var(--text-muted)]">
              Toplam <strong>{diffItems.length}</strong> alan farklı: her satır için tutulacak
              sürümü seçebilirsiniz.
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setAllChoices("server")}>
                Tümünü Sunucu yap
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setAllChoices("local")}>
                Tümünü Yerel yap
              </Button>
            </div>
          </div>
        ) : null}

        {diffItems.length === 0 ? (
          <InlineNotice tone="info" title="Alan içeriği birebir aynı">
            Sunucu revizyonu artmış ancak form/mühendislik girdilerinde değer farkı saptanmadı.
            Doğrudan güncel revizyon üzerine yazabilir veya sunucu sürümünü yükleyebilirsiniz.
          </InlineNotice>
        ) : (
          <div
            role="region"
            aria-labelledby={captionId}
            className="table-wrap table-sticky diff-table-wrap scroll-thin max-h-[340px] overflow-auto"
          >
            <table className="data compact">
              <caption id={captionId}>
                Sunucu (rev.{conflict.serverSession.revision}) ile yerel (rev.{conflict.localRevision})
                arasındaki değişen alanlar ({diffItems.length})
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="sticky-col">
                    Alan
                  </th>
                  <th scope="col">Sunucu (rev.{conflict.serverSession.revision})</th>
                  <th scope="col">Yerel (rev.{conflict.localRevision})</th>
                  {canSelectPerField ? <th scope="col">Tutulacak Sürüm</th> : null}
                </tr>
              </thead>
              <tbody>
                {diffItems.map((item) => {
                  const selectedChoice = choices[item.path] ?? "local";
                  return (
                    <tr key={item.path}>
                      <th scope="row" className="sticky-col font-medium text-[var(--text)]">
                        <span className="block">{item.label}</span>
                        <span className="block text-[10px] font-normal text-[var(--text-faint)]">
                          {item.group}
                        </span>
                      </th>
                      <td
                        data-label={`Sunucu (rev.${conflict.serverSession.revision})`}
                        className="font-mono text-[11.5px]"
                      >
                        {item.serverDisplay}
                      </td>
                      <td
                        data-label={`Yerel (rev.${conflict.localRevision})`}
                        className="font-mono text-[11.5px] text-[var(--primary-strong)]"
                      >
                        {item.localDisplay}
                      </td>
                      {canSelectPerField ? (
                        <td data-label="Tutulacak Sürüm">
                          <div
                            className="seg-control"
                            role="group"
                            aria-label={`${item.label} sürüm seçimi`}
                          >
                            <button
                              type="button"
                              className="seg-btn"
                              aria-pressed={selectedChoice === "server"}
                              disabled={busy}
                              onClick={() => setRowChoice(item.path, "server")}
                            >
                              Sunucu
                            </button>
                            <button
                              type="button"
                              className="seg-btn"
                              aria-pressed={selectedChoice === "local"}
                              disabled={busy}
                              onClick={() => setRowChoice(item.path, "local")}
                            >
                              Yerel
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}
