import { ArrowRight, CheckCircle2, FolderOpen, Loader2 } from "lucide-react";
import type { Project, SessionListItem } from "../../../lib/types";
import type { FlatField } from "../fields";
import { formatNumber } from "../format";

export interface ApplyToSessionPanelProps {
  fields: FlatField[];
  selectedFields: Set<string>;
  approvedKeys: Set<string>;
  lowThreshold: number;
  criticalThreshold: number;
  allSelected: boolean;
  pendingLowConfidence: FlatField[];
  editedCount: number;
  resultDemo: boolean;
  applyMode: "existing" | "new";
  applyProjectId: string;
  applySessionId: string;
  newApplyProjectName: string;
  newApplySectionNo: string;
  overwriteExisting: boolean;
  projects: Project[];
  targetSessions: SessionListItem[];
  actionError: string | null;
  approveDisabledReason: string | null;
  approving: boolean;
  canApplyToSession: boolean;
  applying: boolean;
  appliedSessionId: string | null;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onChangeApplyMode: (mode: "existing" | "new") => void;
  onChangeApplyProjectId: (projectId: string) => void;
  onChangeApplySessionId: (sessionId: string) => void;
  onChangeNewProjectName: (name: string) => void;
  onChangeNewSectionNo: (sectionNo: string) => void;
  onChangeOverwriteExisting: (overwrite: boolean) => void;
  onApproveSelected: () => void;
  onApplyToSession: () => void;
  onOpenGeometry: () => void;
}

export default function ApplyToSessionPanel({
  fields,
  selectedFields,
  approvedKeys,
  lowThreshold,
  criticalThreshold,
  allSelected,
  pendingLowConfidence,
  editedCount,
  resultDemo,
  applyMode,
  applyProjectId,
  applySessionId,
  newApplyProjectName,
  newApplySectionNo,
  overwriteExisting,
  projects,
  targetSessions,
  actionError,
  approveDisabledReason,
  approving,
  canApplyToSession,
  applying,
  appliedSessionId,
  onSelectAll,
  onClearSelection,
  onChangeApplyMode,
  onChangeApplyProjectId,
  onChangeApplySessionId,
  onChangeNewProjectName,
  onChangeNewSectionNo,
  onChangeOverwriteExisting,
  onApproveSelected,
  onApplyToSession,
  onOpenGeometry,
}: ApplyToSessionPanelProps) {
  return (
    <section className="panel p-5" aria-labelledby="ocr-approval-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ocr-approval-title" className="text-[18px] font-bold text-[var(--text)]">
          Alan onayı ve kesite aktarım
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="numeric rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] text-[var(--text-soft)]">
            {selectedFields.size}/{fields.length} seçili
          </span>
          <span className="numeric rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] px-2.5 py-1 text-[10px] text-[var(--success)]">
            {approvedKeys.size} onaylı
          </span>
        </div>
      </div>
      <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-[var(--text-muted)]">
        Onay, raporun ham değerini değiştirmez; onaylı değerler seçtiğiniz proje/test bölümüne
        aktarılır ve mühendislik hesapları otomatik tetiklenir. Düşük güvenli alanlar (&lt;{" "}
        {formatNumber(lowThreshold, 2)}) açıkça işaretlenmeden toplu onay verilemez. Kritik güven
        eşiği &lt; {formatNumber(criticalThreshold, 2)}.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onSelectAll}
          disabled={allSelected || fields.length === 0}
          className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Tümünü seç
        </button>
        <button
          type="button"
          onClick={onClearSelection}
          disabled={selectedFields.size === 0}
          className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-soft)] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Seçimi temizle
        </button>
        {pendingLowConfidence.length > 0 ? (
          <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] text-[var(--warning)]">
            {pendingLowConfidence.length} düşük güvenli alan onay bekliyor:{" "}
            {pendingLowConfidence
              .slice(0, 3)
              .map((item) => item.descriptor.label)
              .join(", ")}
            {pendingLowConfidence.length > 3 ? "…" : ""}
          </span>
        ) : (
          <span className="rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] px-2.5 py-1 text-[10px] text-[var(--success)]">
            düşük güvenli alan seçimi tamam
          </span>
        )}
        {editedCount > 0 ? (
          <span className="rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] text-[var(--text-soft)]">
            {editedCount} elle düzeltme
          </span>
        ) : null}
      </div>

      {!resultDemo ? (
        <div className="mt-4 space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5 text-xs">
          <div className="flex flex-wrap items-center gap-4">
            <label className="inline-flex cursor-pointer items-center gap-2 font-medium text-[var(--text)]">
              <input
                type="radio"
                name="ocr-single-apply-mode"
                checked={applyMode === "existing"}
                disabled={projects.length === 0}
                onChange={() => onChangeApplyMode("existing")}
              />
              Kayıtlı proje / test bölümüne uygula
            </label>
            <label className="inline-flex cursor-pointer items-center gap-2 font-medium text-[var(--text)]">
              <input
                type="radio"
                name="ocr-single-apply-mode"
                checked={applyMode === "new"}
                onChange={() => onChangeApplyMode("new")}
              />
              Yeni proje ve test bölümü oluştur
            </label>
          </div>

          {applyMode === "existing" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
                Hedef proje
                <select
                  value={applyProjectId}
                  onChange={(e) => onChangeApplyProjectId(e.target.value)}
                  className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-xs text-[var(--text)]"
                >
                  {projects.map((proj) => (
                    <option key={proj.id} value={proj.id}>
                      {proj.code ? `[${proj.code}] ` : ""}
                      {proj.name} ({proj.section_count} bölüm)
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
                Hedef test bölümü
                <select
                  value={applySessionId}
                  onChange={(e) => onChangeApplySessionId(e.target.value)}
                  className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-xs text-[var(--text)]"
                >
                  {targetSessions.map((sess) => (
                    <option key={sess.id} value={sess.id}>
                      {sess.name}
                    </option>
                  ))}
                  <option value="__NEW__">+ Bu projede yeni test bölümü oluştur</option>
                </select>
              </label>
              {applySessionId === "__NEW__" ? (
                <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)] sm:col-span-2">
                  Yeni bölüm numarası
                  <input
                    type="text"
                    value={newApplySectionNo}
                    onChange={(e) => onChangeNewSectionNo(e.target.value)}
                    placeholder="Ör: BÖLÜM 1"
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-xs text-[var(--text)]"
                  />
                </label>
              ) : null}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
                Yeni proje adı
                <input
                  type="text"
                  value={newApplyProjectName}
                  onChange={(e) => onChangeNewProjectName(e.target.value)}
                  placeholder="Ör: HİZAN İLÇESİ DGBH YAPIM İŞİ PROJESİ"
                  className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-xs text-[var(--text)]"
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px] font-medium text-[var(--text-soft)]">
                Yeni bölüm numarası
                <input
                  type="text"
                  value={newApplySectionNo}
                  onChange={(e) => onChangeNewSectionNo(e.target.value)}
                  placeholder="Ör: BÖLÜM 1"
                  className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 text-xs text-[var(--text)]"
                />
              </label>
            </div>
          )}

          <label className="inline-flex cursor-pointer items-center gap-2 text-[11px] text-[var(--text-soft)]">
            <input
              type="checkbox"
              checked={overwriteExisting}
              onChange={(e) => onChangeOverwriteExisting(e.target.checked)}
            />
            Kesitte zaten dolu olan alanların üzerine yaz
          </label>
        </div>
      ) : null}

      {actionError ? (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-2 text-[11px] text-[var(--danger)]"
        >
          {actionError}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={Boolean(approveDisabledReason) || approving}
          title={approveDisabledReason ?? "Seçili alanları onayla"}
          onClick={onApproveSelected}
          className="btn btn-secondary inline-flex min-h-10 items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
        >
          {approving ? (
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <CheckCircle2 size={14} aria-hidden="true" />
          )}
          Seçilenleri onayla ({selectedFields.size})
        </button>
        <button
          type="button"
          disabled={!canApplyToSession}
          title={
            resultDemo
              ? "Demo analiz sunucuya uygulanamaz."
              : approvedKeys.size === 0
                ? "Önce en az bir alanı onaylayın."
                : "Onaylı alanları seçili test bölümüne aktar ve hesapla"
          }
          onClick={onApplyToSession}
          className="btn btn-primary inline-flex min-h-10 items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
        >
          {applying ? (
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <ArrowRight size={14} aria-hidden="true" />
          )}
          Oturuma uygula ({approvedKeys.size} onaylı)
        </button>
        {appliedSessionId ? (
          <button
            type="button"
            onClick={onOpenGeometry}
            className="btn btn-secondary inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold"
          >
            <FolderOpen size={14} aria-hidden="true" />
            Kesit ve Hesapları Aç
          </button>
        ) : null}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-faint)]">
        Denetim izi: onaylayan kullanıcı, zaman damgası, alan bazlı değer ve ham OCR metni kaydedilir.
        Uygulama adımında kesit hesaplamaları ve 11 zorunlu form slotu otomatik güncellenir.
      </p>
    </section>
  );
}
