import type { BotasFormCode, SessionListItem } from "../../lib/types";
import { useSessionForms } from "../../hooks/queries";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Dialog";
import { InlineNotice } from "../../components/ui/State";

export function SectionFormsModal({
  session,
  onClose,
  onOpenSection,
  onOpenSectionForm,
}: {
  session: SessionListItem | null;
  onClose: () => void;
  onOpenSection: (session: SessionListItem) => void;
  onOpenSectionForm: (session: SessionListItem, formCode: BotasFormCode | string) => void;
}) {
  const formsQuery = useSessionForms(session?.id ?? null);

  return (
    <Modal
      open={Boolean(session)}
      onClose={onClose}
      title={
        formsQuery.data
          ? `${formsQuery.data.section_no} · BOTAŞ Form & Hakediş Takibi`
          : `${session?.name ?? ""} · BOTAŞ Form Takibi`
      }
      description="Hidrostatik testin tamamlanması gereken 11 zorunlu BOTAŞ formu (Ön ve Nihai Kurutma dahil) ve otomatik kontrol noktaları."
      className="max-w-4xl max-h-[85vh] overflow-y-auto"
      footer={
        <>
          {session ? (
            <Button
              variant="primary"
              onClick={() => {
                const target = session;
                onClose();
                onOpenSection(target);
              }}
            >
              Kesiti Çalışma Alanında Aç
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>
            Kapat
          </Button>
        </>
      }
    >
      {formsQuery.isLoading ? (
        <div className="space-y-2 py-4" aria-busy="true" aria-label="Form kayıtları yükleniyor">
          <div className="skeleton h-8 w-2/3" />
          <div className="skeleton h-40 w-full" />
        </div>
      ) : formsQuery.isError ? (
        <InlineNotice tone="danger" title="Formlar yüklenemedi">
          {(formsQuery.error as Error)?.message || "Sunucu hatası oluştu."}
        </InlineNotice>
      ) : formsQuery.data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              tone={
                formsQuery.data.summary.failed_forms.length > 0
                  ? "fail"
                  : formsQuery.data.summary.complete
                    ? "pass"
                    : "warning"
              }
            >
              {formsQuery.data.summary.filled_required} / {formsQuery.data.summary.required_total}{" "}
              Zorunlu Form Dolu
            </Badge>
            <Badge tone="neutral">{formsQuery.data.summary.missing_required} Eksik Form</Badge>
            {formsQuery.data.summary.supplementary_filled > 0 ? (
              <Badge tone="info">{formsQuery.data.summary.supplementary_filled} Ek Rapor</Badge>
            ) : null}
          </div>

          {formsQuery.data.missing_required_forms.length > 0 ? (
            <InlineNotice
              tone="warning"
              title={`Tamamlanması Gereken Eksik Formlar (${formsQuery.data.missing_required_forms.length})`}
            >
              <div className="mt-1 flex flex-wrap gap-1.5">
                {formsQuery.data.missing_required_forms.map((m) => (
                  <span
                    key={m.form_code}
                    className="rounded border border-[var(--border)] bg-[var(--surface-1)] px-2 py-0.5 text-[11px]"
                  >
                    {m.form_title} ({m.botas_code})
                  </span>
                ))}
              </div>
            </InlineNotice>
          ) : (
            <InlineNotice tone="success" title="Tüm Zorunlu BOTAŞ Formları Mevcut">
              11 zorunlu formun tamamı doldurulmuş.
            </InlineNotice>
          )}

          <div
            tabIndex={0}
            role="region"
            aria-label="Kesit BOTAŞ Form Listesi"
            className="table-wrap table-sticky max-h-[340px] overflow-auto scroll-thin"
          >
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">BOTAŞ Kodu</th>
                  <th scope="col">Form Adı</th>
                  <th scope="col">Tip</th>
                  <th scope="col">Durum</th>
                  <th scope="col">Kaynak Doküman / Sayfa</th>
                  <th scope="col">Tarih</th>
                  <th scope="col" className="num">
                    Rev.
                  </th>
                </tr>
              </thead>
              <tbody>
                {formsQuery.data.forms.map((row) => {
                  const tone =
                    row.status === "passed"
                      ? "pass"
                      : row.status === "failed"
                        ? "fail"
                        : row.status === "warning"
                          ? "warning"
                          : row.status === "filled"
                            ? "info"
                            : "neutral";
                  const label =
                    row.status === "passed"
                      ? "Başarılı"
                      : row.status === "failed"
                        ? "Başarısız"
                        : row.status === "warning"
                          ? "İnceleme"
                          : row.status === "filled"
                            ? "Dolu"
                            : "Boş";
                  return (
                    <tr
                      key={row.id}
                      className="cursor-pointer hover:bg-[var(--surface-2)]"
                      title={`${row.form_title} formunu aç`}
                      onClick={() => {
                        if (!session) return;
                        const s = session;
                        onClose();
                        onOpenSectionForm(s, row.form_code);
                      }}
                    >
                      <td className="font-mono text-[10.5px] text-[var(--primary)]">
                        {row.botas_code}
                      </td>
                      <td className="font-medium text-[var(--text)]">{row.form_title}</td>
                      <td>
                        <Badge tone={row.required ? "info" : "neutral"}>
                          {row.required ? "Zorunlu" : "Ek"}
                        </Badge>
                      </td>
                      <td>
                        <Badge tone={tone}>{label}</Badge>
                      </td>
                      <td className="text-[11px] text-[var(--text-soft)]">
                        {row.source_filename ? (
                          <span>
                            {row.source_filename}
                            {row.pages.length > 0 ? ` (s. ${row.pages.join(", ")})` : ""}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="font-mono text-[11px]">{row.form_date || "—"}</td>
                      <td className="num">{row.revision}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--text)]">
              Operasyon Kontrol Noktaları (11 Madde)
            </h3>
            <div className="grid gap-2 md:grid-cols-2">
              {formsQuery.data.checkpoints.map((cp) => {
                const cpTone =
                  cp.status === "passed"
                    ? "pass"
                    : cp.status === "failed"
                      ? "fail"
                      : cp.status === "warning"
                        ? "warning"
                        : "neutral";
                return (
                  <div
                    key={cp.key}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-[11px]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold text-[var(--text)]">{cp.label}</span>
                      <Badge tone={cpTone}>
                        {cp.status === "passed"
                          ? "Uygun"
                          : cp.status === "failed"
                            ? "Uygun Değil"
                            : cp.status === "warning"
                              ? "İnceleme"
                              : "Bekliyor"}
                      </Badge>
                    </div>
                    {cp.message ? (
                      <p className="mt-1 text-[var(--text-soft)]">{cp.message}</p>
                    ) : null}
                    <span className="mt-0.5 block font-mono text-[9.5px] text-[var(--text-faint)]">
                      Madde {cp.ref}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
