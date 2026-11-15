import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Braces, Info, SlidersHorizontal } from "lucide-react";
import { formatDateTime, shortId } from "../format";
import { DEFAULT_ALIASES, FIELD_CATALOG } from "../fields";
import type { MappingProfile } from "../types";

interface DraftRow {
  aliases: string;
  unit: string;
  required: boolean;
}

function buildDraft(profile: MappingProfile | null): Record<string, DraftRow> {
  const rows: Record<string, DraftRow> = {};
  for (const descriptor of FIELD_CATALOG) {
    const rule = profile?.mapping?.fields?.[descriptor.key];
    rows[descriptor.key] = {
      aliases: (rule?.aliases ?? DEFAULT_ALIASES[descriptor.key] ?? [descriptor.label]).join(", "),
      unit: rule?.unit ?? descriptor.unit,
      required: rule?.required ?? descriptor.required,
    };
  }
  for (const [key, rule] of Object.entries(profile?.mapping?.fields ?? {})) {
    if (!(key in rows)) {
      rows[key] = {
        aliases: (rule.aliases ?? []).join(", "),
        unit: rule.unit ?? "",
        required: rule.required ?? false,
      };
    }
  }
  return rows;
}

function buildMappingJson(
  profile: MappingProfile | null,
  rows: Record<string, DraftRow>,
): string {
  const fields = Object.fromEntries(
    Object.entries(rows)
      .filter(([, row]) => row.aliases.trim().length > 0 || row.unit.trim().length > 0)
      .map(([key, row]) => [
        key,
        {
          aliases: row.aliases
            .split(",")
            .map((alias) => alias.trim())
            .filter((alias) => alias.length > 0),
          unit: row.unit.trim(),
          required: row.required,
        },
      ]),
  );
  return JSON.stringify(
    {
      schema_version: profile?.mapping?.schema_version ?? 1,
      sections: profile?.mapping?.sections ?? [],
      fields,
      table_hints: profile?.mapping?.table_hints ?? {},
    },
    null,
    2,
  );
}

export interface MappingPanelProps {
  profiles: MappingProfile[];
  selectedProfileId: string | null;
  onSelectProfile: (id: string | null) => void;
  profile: MappingProfile | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  demo: boolean;
}

export default function MappingPanel({
  profiles,
  selectedProfileId,
  onSelectProfile,
  profile,
  loading,
  error,
  onRetry,
  demo,
}: MappingPanelProps) {
  const baseDraft = useMemo(() => buildDraft(profile), [profile]);
  const [draft, setDraft] = useState<Record<string, DraftRow>>(() => buildDraft(profile));
  const [jsonOpen, setJsonOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    setDraft(baseDraft);
  }, [baseDraft]);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(baseDraft), [draft, baseDraft]);

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return FIELD_CATALOG.filter((descriptor) => {
      if (!normalized) return true;
      const haystack = `${descriptor.label} ${descriptor.key}`.toLowerCase();
      return haystack.includes(normalized);
    });
  }, [query]);

  const updateRow = (key: string, patch: Partial<DraftRow>) => {
    setDraft((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  };

  return (
    <section className="panel p-5" aria-labelledby="ocr-mapping-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal size={18} className="text-[var(--primary)]" aria-hidden="true" />
            <h2 id="ocr-mapping-title" className="text-base font-semibold text-[var(--text)]">
              Rapor formatı eşleme
            </h2>
            <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--warning)]">
              Format yarın geliyor
            </span>
            {demo ? (
              <span className="rounded-full border border-[var(--border)] bg-[var(--surface-3)] px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-[var(--text-soft)]">
                yerel taslak
              </span>
            ) : null}
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--text-muted)]">
            Kanonik alanlar sabittir; form etiketleri, birimler ve zorunluluk profil bazında
            yapılandırılır. Gerçek form geldiğinde alias listeleri güncellenecek ve kuru çalıştırma
            ile kalibre edilecek.
          </p>
        </div>
        <div className="flex flex-col gap-1 sm:min-w-[280px]">
          <label
            htmlFor="ocr-mapping-profile"
            className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-faint)]"
          >
            Eşleme profili
          </label>
          <select
            id="ocr-mapping-profile"
            value={selectedProfileId ?? ""}
            onChange={(event) => onSelectProfile(event.target.value || null)}
            disabled={loading || profiles.length === 0}
            className="min-h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-50"
            aria-describedby="ocr-mapping-profile-hint"
          >
            <option value="">Varsayılan etiket sözlüğü</option>
            {profiles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
                {item.is_default ? " (varsayılan)" : ""}
              </option>
            ))}
          </select>
          <p id="ocr-mapping-profile-hint" className="text-[10px] text-[var(--text-faint)]">
            Seçilen profil, analiz isteğinde <span className="numeric">mapping_profile_id</span>{" "}
            olarak gönderilir.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="mt-5 text-xs text-[var(--text-muted)]" role="status">
          Eşleme profilleri yükleniyor…
        </p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-xs text-[var(--warning)]"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-[var(--warning-border)] px-2.5 py-1 font-medium text-[var(--warning)] hover:bg-[var(--warning-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
          >
            Yeniden dene
          </button>
        </div>
      ) : null}

      {!loading && !profile ? (
        <div className="mt-5 rounded-xl border border-dashed border-[var(--border)] px-4 py-8 text-center">
          <p className="text-sm font-medium text-[var(--text-soft)]">Eşleme profili seçilmedi.</p>
          <p className="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-[var(--text-faint)]">
            Analiz, backend'in varsayılan etiket sözlüğünü kullanır. Form formatı geldiğinde yeni
            bir profil oluşturup alias'ları buradan düzenleyin.
          </p>
        </div>
      ) : null}

      {profile ? (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] text-[var(--text-muted)]">
            <span className="rounded border border-[var(--border)] bg-[var(--surface-3)] px-2 py-0.5">
              Kimlik: <span className="numeric text-[var(--text-soft)]">{shortId(profile.id)}</span>
            </span>
            <span className="rounded border border-[var(--border)] bg-[var(--surface-3)] px-2 py-0.5">
              Format anahtarı: <span className="numeric text-[var(--text-soft)]">{profile.format_key}</span>
            </span>
            <span className="rounded border border-[var(--border)] bg-[var(--surface-3)] px-2 py-0.5">
              Mod: <span className="numeric text-[var(--text-soft)]">{profile.mode ?? "—"}</span>
            </span>
            <span className="rounded border border-[var(--border)] bg-[var(--surface-3)] px-2 py-0.5">
              Güncellendi: {formatDateTime(profile.updated_at)}
            </span>
            {profile.is_default ? (
              <span className="rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] px-2 py-0.5 font-semibold text-[var(--success)]">
                varsayılan
              </span>
            ) : null}
          </div>

          {profile.mapping?.sections && profile.mapping.sections.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
              {profile.mapping.sections.map((section) => (
                <span
                  key={section.name}
                  className="rounded border border-[var(--border)] bg-[var(--surface-3)] px-2 py-1 text-[var(--text-soft)]"
                >
                  Bölüm <span className="numeric text-[var(--primary)]">{section.name}</span>:{" "}
                  {section.heading_aliases.join(" · ")}
                </span>
              ))}
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <span className="sr-only">Alan ara</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Alan ara (etiket veya anahtar)"
                className="min-h-9 w-64 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs text-[var(--text)] placeholder:text-[var(--text-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
              />
            </label>
            <p className="text-[10px] text-[var(--text-faint)]">
              Alias'ları virgülle ayırın. Değişiklikler yalnızca bu ekranda tutulur.
            </p>
          </div>

          <div className="mt-3 max-h-[420px] overflow-auto rounded-lg border hairline">
            <table className="w-full min-w-[760px] border-collapse text-left text-xs">
              <caption className="sr-only">
                Kanonik alan eşlemesi: alan, etiket alias'ları, birim ve zorunluluk.
              </caption>
              <thead className="sticky top-0 z-10 bg-[var(--surface-2)]">
                <tr className="text-[10px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
                  <th scope="col" className="min-w-[210px] px-3 py-2 font-medium">
                    Kanonik alan
                  </th>
                  <th scope="col" className="min-w-[320px] px-3 py-2 font-medium">
                    Etiket alias'ları
                  </th>
                  <th scope="col" className="w-28 px-3 py-2 font-medium">
                    Birim
                  </th>
                  <th scope="col" className="w-24 px-3 py-2 font-medium">
                    Zorunlu
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((descriptor) => {
                  const row = draft[descriptor.key];
                  if (!row) return null;
                  return (
                    <tr key={descriptor.key} className="border-t hairline align-middle">
                      <td className="px-3 py-2">
                        <p className="font-medium text-[var(--text)]">{descriptor.label}</p>
                        <p className="numeric mt-0.5 text-[10px] text-[var(--text-faint)]">
                          {descriptor.key}
                        </p>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={row.aliases}
                          onChange={(event) =>
                            updateRow(descriptor.key, { aliases: event.target.value })
                          }
                          aria-label={`${descriptor.label} etiket alias'ları`}
                          className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-xs text-[var(--text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={row.unit}
                          onChange={(event) =>
                            updateRow(descriptor.key, { unit: event.target.value })
                          }
                          aria-label={`${descriptor.label} birimi`}
                          className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-xs text-[var(--text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={row.required}
                          onChange={(event) =>
                            updateRow(descriptor.key, { required: event.target.checked })
                          }
                          aria-label={`${descriptor.label} zorunlu alan`}
                          className="h-4 w-4 accent-[var(--primary)]"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {jsonOpen ? (
            <div className="mt-3">
              <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-faint)]">
                <Braces size={12} aria-hidden="true" /> Eşleme JSON önizlemesi
              </p>
              <pre className="numeric mt-2 max-h-64 overflow-auto rounded-lg border hairline bg-[var(--surface-2)] p-3 text-[11px] leading-relaxed text-[var(--text-soft)]">
                {buildMappingJson(profile, draft)}
              </pre>
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setDraft(baseDraft)}
              disabled={!dirty}
              className="inline-flex min-h-10 items-center rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-soft)] transition hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Değişiklikleri sıfırla
            </button>
            <button
              type="button"
              onClick={() => setJsonOpen((value) => !value)}
              aria-expanded={jsonOpen}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-soft)] transition hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
            >
              <Braces size={13} aria-hidden="true" />
              {jsonOpen ? "JSON'u kapat" : "JSON önizle"}
            </button>
            <button
              type="button"
              disabled
              title="Kaydetme, yarınki format doğrulamasından sonra etkinleşecek."
              className="inline-flex min-h-10 items-center rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-muted)] opacity-50"
            >
              Profili kaydet
            </button>
            <button
              type="button"
              disabled
              title="Kuru çalıştırma, gerçek form metni geldiğinde eşleşen/eşleşmeyen alanları gösterir."
              className="inline-flex min-h-10 items-center rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-muted)] opacity-50"
            >
              Kuru çalıştırma
            </button>
            {dirty ? (
              <span className="rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10px] font-semibold text-[var(--warning)]">
                yerel taslak · kaydedilmedi
              </span>
            ) : null}
          </div>
        </>
      ) : null}

      <p className="mt-4 flex items-start gap-2 border-t hairline pt-3 text-[10px] leading-relaxed text-[var(--text-faint)]">
        <Info size={13} className="mt-0.5 shrink-0 text-[var(--primary)]" aria-hidden="true" />
        <span>
          Profil sürümlenir (<span className="numeric">updated_at</span>); her analiz kullandığı
          profil kimliğini saklar. Format değişince eski analizler eski profille okunur, yeni
          analizler için yeni profil açılır.
        </span>
      </p>
    </section>
  );
}
