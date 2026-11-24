import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Pencil, RotateCcw, Sparkles } from "lucide-react";
import { confidenceTier, formatConfidence, formatUnit, formatValue } from "../format";
import type { FlatField } from "../fields";
import type { SuggestedFix } from "../types";
import { TONE_BADGE_CLASSES, confidenceTone, type Tone } from "./tone";

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
  onToggle: (key: string, checked: boolean) => void;
  onEdit: (key: string, value: string | null) => void;
}

export default function FieldsTable({
  fields,
  selected,
  edits,
  suggestedFixes = [],
  onToggle,
  onEdit,
}: FieldsTableProps) {
  const fixesByField = new Map(suggestedFixes.map((fix) => [fix.field, fix]));
  const pendingFixes = suggestedFixes.filter(
    (fix) => !Object.prototype.hasOwnProperty.call(edits, fix.field),
  );
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingKey) {
      editInputRef.current?.focus();
    }
  }, [editingKey]);

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
          {fields.length} alan okundu · onay için satırları seçin
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

      {pendingFixes.length > 0 ? (
        <div
          role="note"
          className="flex items-center gap-2 border-b border-[var(--warning-border)] bg-[var(--warning-bg)] px-4 py-2 text-[11px] text-[var(--warning)]"
        >
          <Sparkles size={13} aria-hidden="true" className="shrink-0" />
          <span>
            Olası OCR ondalık hatası tespit edildi ({pendingFixes.length} alan) — önerileri tek tıkla
            uygulayıp onaylayabilirsiniz.
          </span>
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
            {fields.map((item) => {
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
                  className={clsx(
                    "border-t hairline align-top transition-colors",
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
                    {item.field.page ?? "—"}
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
