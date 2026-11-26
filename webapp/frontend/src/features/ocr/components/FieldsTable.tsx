import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { ArrowDown, Eye, Pencil, RotateCcw, Search, Sparkles } from "lucide-react";
import { confidenceTier, formatConfidence, formatUnit, formatValue } from "../format";
import type { FlatField } from "../fields";
import type { SuggestedFix } from "../types";
import { TONE_BADGE_CLASSES, confidenceTone, type Tone } from "./tone";

type FieldFilter = "all" | "low" | "suggested" | "edited" | "required";

const FILTER_LABELS: Array<{ key: FieldFilter; label: string }> = [
  { key: "all", label: "Tümü" },
  { key: "low", label: "Düşük Güven" },
  { key: "suggested", label: "Önerili" },
  { key: "edited", label: "Düzenlenen" },
  { key: "required", label: "Zorunlu" },
];

const TIER_LABEL = {
  critical: "Kritik",
  low: "Düşük",
  ok: "Orta",
  high: "Yüksek",
} as const;

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const tier = confidenceTier(confidence);
  const tone: Tone = confidenceTone(confidence);
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
        TONE_BADGE_CLASSES[tone],
      )}
      aria-label={`Güven ${formatConfidence(confidence)} · ${TIER_LABEL[tier]}`}
    >
      <span
        className={clsx(
          "h-1.5 w-1.5 rounded-full",
          tone === "danger" && "bg-[var(--danger)]",
          tone === "warning" && "bg-[var(--warning)]",
          tone === "info" && "bg-[var(--primary)]",
          tone === "success" && "bg-[var(--success)]",
          tone === "neutral" && "bg-[var(--text-faint)]",
        )}
        aria-hidden="true"
      />
      <span className="numeric">{formatConfidence(confidence)}</span>
      <span className="hidden sm:inline">{TIER_LABEL[tier]}</span>
    </span>
  );
}

export interface FieldsTableProps {
  fields: FlatField[];
  selected: Set<string>;
  edits: Record<string, string>;
  suggestedFixes?: SuggestedFix[];
  lowThreshold?: number;
  onToggle: (key: string, checked: boolean) => void;
  onEdit: (key: string, value: string | null) => void;
  onPreviewPage?: (page: number) => void;
}

export default function FieldsTable({
  fields,
  selected,
  edits,
  suggestedFixes = [],
  lowThreshold = 0.6,
  onToggle,
  onEdit,
  onPreviewPage,
}: FieldsTableProps) {
  const fixesByField = useMemo(
    () => new Map(suggestedFixes.map((fix) => [fix.field, fix])),
    [suggestedFixes],
  );
  const pendingFixes = useMemo(
    () =>
      suggestedFixes.filter((fix) => !Object.prototype.hasOwnProperty.call(edits, fix.field)),
    [suggestedFixes, edits],
  );
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [filter, setFilter] = useState<FieldFilter>("all");
  const [search, setSearch] = useState("");
  const editInputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});

  useEffect(() => {
    if (editingKey) {
      editInputRef.current?.focus();
    }
  }, [editingKey]);

  const filteredFields = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("tr-TR");
    return fields.filter((item) => {
      const key = item.descriptor.key;
      const edited = Object.prototype.hasOwnProperty.call(edits, key);
      const hasPendingFix = fixesByField.has(key) && !edited;
      if (filter === "low" && item.field.confidence >= lowThreshold) return false;
      if (filter === "suggested" && !hasPendingFix) return false;
      if (filter === "edited" && !edited) return false;
      if (filter === "required" && !item.descriptor.required) return false;
      if (!query) return true;
      return (
        item.descriptor.label.toLocaleLowerCase("tr-TR").includes(query) ||
        key.toLocaleLowerCase("tr-TR").includes(query) ||
        (item.field.raw_text ?? "").toLocaleLowerCase("tr-TR").includes(query)
      );
    });
  }, [fields, edits, fixesByField, filter, search, lowThreshold]);

  const lowPendingCount = useMemo(
    () => fields.filter((item) => item.field.confidence < lowThreshold && !selected.has(item.descriptor.key)).length,
    [fields, selected, lowThreshold],
  );

  const jumpToNextLowConfidence = () => {
    const target = fields.find(
      (item) => item.field.confidence < lowThreshold && !selected.has(item.descriptor.key),
    );
    if (!target) return;
    setFilter("all");
    setSearch("");
    window.setTimeout(() => {
      const row = rowRefs.current[target.descriptor.key];
      row?.scrollIntoView?.({ block: "center", behavior: "smooth" });
      row?.focus();
    }, 0);
  };

  const applyAllPendingFixes = () => {
    for (const fix of pendingFixes) {
      onEdit(fix.field, String(fix.suggested_value));
    }
  };

  const beginEdit = (item: FlatField) => {
    setEditingKey(item.descriptor.key);
    setDraft(edits[item.descriptor.key] ?? String(item.field.value ?? ""));
  };

  const commitEdit = (key: string) => {
    onEdit(key, draft.trim() === "" ? "" : draft);
    setEditingKey(null);
  };

  if (fields.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <p className="text-sm font-medium text-[var(--text-soft)]">Raporda tanınabilir alan bulunamadı.</p>
        <p className="mt-1 text-xs text-[var(--text-faint)]">
          Daha yüksek çözünürlüklü tarama deneyin veya eşleme profilindeki etiketleri kontrol edin.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b hairline px-4 py-3">
        <p className="text-xs text-[var(--text-muted)]">
          {filteredFields.length}/{fields.length} alan gösteriliyor · onay için satırları seçin
        </p>
        <p className="flex flex-wrap items-center gap-3 text-[10px] text-[var(--text-faint)]">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[var(--danger)]" aria-hidden="true" /> &lt; %40 kritik
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[var(--warning)]" aria-hidden="true" /> &lt; %60 düşük
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[var(--success)]" aria-hidden="true" /> ≥ %85 yüksek
          </span>
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-b hairline bg-[var(--surface-2)] px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Alan filtreleri">
          {FILTER_LABELS.map((item) => {
            const active = filter === item.key;
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(item.key)}
                className={clsx(
                  "rounded-full border px-2.5 py-1 text-[10.5px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]",
                  active
                    ? "border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--primary)]"
                    : "border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]",
                )}
              >
                {item.label}
              </button>
            );
          })}
          {lowPendingCount > 0 ? (
            <button
              type="button"
              onClick={jumpToNextLowConfidence}
              className="ml-1 inline-flex items-center gap-1 rounded-full border border-[var(--warning-border)] bg-[var(--warning-bg)] px-2.5 py-1 text-[10.5px] font-medium text-[var(--warning)] transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
            >
              <ArrowDown size={11} aria-hidden="true" />
              Sonraki Düşük Güven ({lowPendingCount})
            </button>
          ) : null}
        </div>
        <label className="relative flex min-w-[200px] items-center">
          <Search
            size={13}
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 text-[var(--text-faint)]"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Alan veya ham metin ara..."
            aria-label="Alanlarda ara"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-1)] py-1 pl-8 pr-2.5 text-[11px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
          />
        </label>
      </div>

      {pendingFixes.length > 0 ? (
        <div
          role="note"
          className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--warning-border)] bg-[var(--warning-bg)] px-4 py-2 text-[11px] text-[var(--warning)]"
        >
          <span className="flex items-center gap-2">
            <Sparkles size={13} aria-hidden="true" className="shrink-0" />
            <span>
              Olası OCR ondalık hatası tespit edildi ({pendingFixes.length} alan) — önerileri tek tıkla
              uygulayıp onaylayabilirsiniz.
            </span>
          </span>
          <button
            type="button"
            onClick={applyAllPendingFixes}
            className="rounded-md border border-[var(--warning-border)] bg-[var(--surface-1)] px-2.5 py-1 text-[10.5px] font-semibold text-[var(--warning)] transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
          >
            Tüm Önerileri Uygula ({pendingFixes.length})
          </button>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Rapordan okunan alanlar: alan adı, değer, birim, güven, ham metin ve sayfa. Onay
            kutusuyla alan seçilir.
          </caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
              <th scope="col" className="w-10 px-4 py-2 font-medium">
                Onay
              </th>
              <th scope="col" className="min-w-[190px] px-3 py-2 font-medium">
                Alan
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Değer
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Birim
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Güven
              </th>
              <th scope="col" className="min-w-[180px] px-3 py-2 font-medium">
                Ham metin
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Sayfa
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredFields.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-xs text-[var(--text-faint)]">
                  Seçili filtre veya arama terimiyle eşleşen alan bulunamadı.
                </td>
              </tr>
            ) : null}
            {filteredFields.map((item) => {
              const key = item.descriptor.key;
              const tier = confidenceTier(item.field.confidence);
              const edited = Object.prototype.hasOwnProperty.call(edits, key);
              const editing = editingKey === key;
              const fix = fixesByField.get(key);
              const displayed = edited
                ? edits[key]
                : formatValue(item.field.value, key, item.field.unit);
              const unitLabel = formatUnit(item.field.unit);
              return (
                <tr
                  key={key}
                  ref={(node) => {
                    rowRefs.current[key] = node;
                  }}
                  tabIndex={0}
                  onKeyDown={(event) => {
                    const target = event.target;
                    if (
                      target instanceof HTMLElement &&
                      ["INPUT", "BUTTON", "TEXTAREA", "SELECT", "A"].includes(target.tagName)
                    ) {
                      return;
                    }
                    if (event.key === "Enter" || event.key === "e" || event.key === "E") {
                      event.preventDefault();
                      beginEdit(item);
                    } else if (event.key === " ") {
                      event.preventDefault();
                      onToggle(key, !selected.has(key));
                    }
                  }}
                  className={clsx(
                    "border-t hairline align-top transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--focus)]",
                    tier === "critical" && "bg-[var(--danger-bg)]",
                    tier === "low" && "bg-[var(--warning-bg)]",
                    "hover:bg-[var(--surface-raised)]",
                  )}
                >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-[var(--primary)]"
                      checked={selected.has(key)}
                      onChange={(event) => onToggle(key, event.target.checked)}
                      aria-label={`${item.descriptor.label} alanını onaya dahil et`}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium text-[var(--text)]">{item.descriptor.label}</span>
                      {item.descriptor.required ? (
                        <span className="rounded border border-[var(--border)] px-1 py-0.5 text-[9px] uppercase tracking-wide text-[var(--text-muted)]">
                          zorunlu
                        </span>
                      ) : null}
                      {edited ? (
                        <span className="rounded border border-[var(--warning-border)] bg-[var(--warning-bg)] px-1 py-0.5 text-[9px] uppercase tracking-wide text-[var(--warning)]">
                          elle
                        </span>
                      ) : null}
                    </div>
                    <p className="numeric mt-1 text-[10px] text-[var(--text-faint)]">{key}</p>
                  </td>
                  <td className="px-3 py-2.5">
                    {editing ? (
                      <input
                        ref={editInputRef}
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        onBlur={() => commitEdit(key)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            commitEdit(key);
                          }
                          if (event.key === "Escape") {
                            event.preventDefault();
                            setEditingKey(null);
                          }
                        }}
                        aria-label={`${item.descriptor.label} için düzeltilmiş değer`}
                        className="numeric w-full min-w-[110px] rounded-md border border-[var(--warning-border)] bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                      />
                    ) : (
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={clsx(
                              "numeric font-medium",
                              edited ? "text-[var(--warning)]" : "text-[var(--text)]",
                              tier === "critical" && !edited && "text-[var(--danger)]",
                              tier === "low" && !edited && "text-[var(--warning)]",
                            )}
                          >
                            {displayed === "" ? "—" : displayed}
                          </span>
                          <button
                            type="button"
                            onClick={() => beginEdit(item)}
                            className="rounded p-1 text-[var(--text-faint)] transition hover:bg-[var(--surface-raised)] hover:text-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                            aria-label={`${item.descriptor.label} değerini düzelt`}
                            title="Değeri düzelt"
                          >
                            <Pencil size={12} aria-hidden="true" />
                          </button>
                          {edited ? (
                            <button
                              type="button"
                              onClick={() => onEdit(key, null)}
                              className="rounded p-1 text-[var(--warning)] transition hover:bg-[var(--surface-raised)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                              aria-label={`${item.descriptor.label} elle düzeltmesini geri al`}
                              title="Elle düzeltmeyi geri al"
                            >
                              <RotateCcw size={12} aria-hidden="true" />
                            </button>
                          ) : null}
                        </div>
                        {!edited && fix ? (
                          <button
                            type="button"
                            onClick={() => onEdit(key, String(fix.suggested_value))}
                            title={fix.reason}
                            aria-label={`${item.descriptor.label} için ${fix.suggested_value} önerisini uygula`}
                            className="mt-1 inline-flex items-center gap-1 rounded border border-[var(--warning-border)] bg-[var(--warning-bg)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--warning)] transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                          >
                            <Sparkles size={10} aria-hidden="true" />
                            <span>Öneri: {fix.suggested_value} · Uygula</span>
                          </button>
                        ) : null}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-soft)]">{unitLabel || "—"}</td>
                  <td className="px-3 py-2.5">
                    <ConfidenceBadge confidence={item.field.confidence} />
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className="numeric block max-w-[220px] truncate text-[11px] text-[var(--text-muted)]"
                      title={item.field.raw_text || "Ham metin yok"}
                    >
                      {item.field.raw_text || "—"}
                    </span>
                  </td>
                  <td className="numeric px-3 py-2.5 text-right text-[var(--text-muted)]">
                    {item.field.page != null && onPreviewPage ? (
                      <button
                        type="button"
                        onClick={() => onPreviewPage(item.field.page!)}
                        aria-label={`Sayfa ${item.field.page} belgesini önizle`}
                        title={`Sayfa ${item.field.page} görselini aç`}
                        className="inline-flex items-center gap-1 rounded border border-[var(--border)] bg-[var(--surface-1)] px-2 py-0.5 text-[11px] font-medium text-[var(--primary)] transition hover:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
                      >
                        <Eye size={11} aria-hidden="true" />
                        {item.field.page}
                      </button>
                    ) : (
                      item.field.page ?? "—"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="border-t hairline px-4 py-2.5 text-[10px] leading-relaxed text-[var(--text-faint)]">
        Elle düzeltme onay sayılmaz; ham OCR değeri denetim izi için saklanır. Düşük güvenli
        alanlar açıkça işaretlenmeden toplu onay verilemez.
      </p>
    </div>
  );
}
