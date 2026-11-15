import { useMemo, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { formatDelta, formatUnit, formatValue } from "../format";
import { fieldLabel } from "../fields";
import {
  DISCREPANCY_STATUS_LABELS,
  SEVERITY_LABELS,
  isBlockingDiscrepancy,
  type Discrepancy,
} from "../types";
import { TONE_BADGE_CLASSES, type Tone } from "./tone";

export function discrepancyTone(item: Discrepancy): Tone {
  switch (item.status) {
    case "match":
      return "success";
    case "within_tolerance":
      return "info";
    case "mismatch":
    case "missing_in_report":
      return "danger";
    case "not_comparable":
      return "warning";
    case "missing_in_calculation":
    default:
      return "neutral";
  }
}

export interface DiscrepanciesTableProps {
  items: Discrepancy[];
  hasCalculated: boolean;
}

export default function DiscrepanciesTable({ items, hasCalculated }: DiscrepanciesTableProps) {
  const [onlyBlocking, setOnlyBlocking] = useState(false);

  const blockingCount = useMemo(
    () => items.filter(isBlockingDiscrepancy).length,
    [items],
  );
  const warningCount = useMemo(
    () => items.filter((item) => item.severity === "warning" && !isBlockingDiscrepancy(item)).length,
    [items],
  );

  const visible = onlyBlocking ? items.filter(isBlockingDiscrepancy) : items;

  if (items.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <span className="mx-auto grid h-10 w-10 place-items-center rounded-full border border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]">
          <CheckCircle2 size={18} aria-hidden="true" />
        </span>
        <p className="mt-3 text-sm font-medium text-[var(--text)]">
          {hasCalculated
            ? "Uyuşmazlık yok."
            : "Karşılaştırma yapılmadı."}
        </p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[var(--text-faint)]">
          {hasCalculated
            ? "Rapor değerleri hesaplanan değerlerle tolerans içinde. İnsan onayı yine de zorunludur."
            : "Hesaplanan değerler gönderilmediği için rapor yalnızca okundu; alanlar hesaplarla karşılaştırılmadı."}
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b hairline px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          <span
            className={clsx(
              "rounded-full border px-2 py-0.5 font-semibold uppercase tracking-[0.08em]",
              blockingCount > 0 ? TONE_BADGE_CLASSES.danger : TONE_BADGE_CLASSES.success,
            )}
          >
            {blockingCount} engelleyici
          </span>
          <span className={clsx("rounded-full border px-2 py-0.5", TONE_BADGE_CLASSES.warning)}>
            {warningCount} uyarı
          </span>
          <span className={clsx("rounded-full border px-2 py-0.5", TONE_BADGE_CLASSES.neutral)}>
            {items.length} karşılaştırma
          </span>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--text-soft)]">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--primary)]"
            checked={onlyBlocking}
            onChange={(event) => setOnlyBlocking(event.target.checked)}
          />
          Yalnızca engelleyicileri göster
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Rapor değerleri ile hesaplanan değerlerin karşılaştırması: alan, rapor, hesap, fark,
            tolerans, durum ve mesaj.
          </caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
              <th scope="col" className="min-w-[170px] px-4 py-2 font-medium">
                Alan
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Rapor
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Hesap
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Fark
              </th>
              <th scope="col" className="min-w-[130px] px-3 py-2 font-medium">
                Tolerans
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Durum
              </th>
              <th scope="col" className="min-w-[240px] px-3 py-2 font-medium">
                Mesaj
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item, index) => {
              const blocking = isBlockingDiscrepancy(item);
              const tone = discrepancyTone(item);
              return (
                <tr
                  key={`${item.field}-${item.status}-${index}`}
                  className={clsx(
                    "border-t hairline align-top",
                    blocking && "bg-[var(--danger-bg)]",
                    !blocking && item.severity === "warning" && "bg-[var(--warning-bg)]",
                  )}
                >
                  <td
                    className={clsx(
                      "px-4 py-2.5",
                      blocking && "border-l-2 border-l-[var(--danger)]",
                      !blocking && item.severity === "warning" && "border-l-2 border-l-[var(--warning)]",
                    )}
                  >
                    <p className="font-medium text-[var(--text)]">{item.label || fieldLabel(item.field)}</p>
                    <p className="numeric mt-1 text-[10px] text-[var(--text-faint)]">{item.field}</p>
                  </td>
                  <td className="numeric whitespace-nowrap px-3 py-2.5 text-right text-[var(--text-soft)]">
                    {formatValue(item.reported, item.field, item.unit)}
                    {item.unit ? (
                      <span className="ml-1 text-[10px] text-[var(--text-faint)]">{formatUnit(item.unit)}</span>
                    ) : null}
                  </td>
                  <td className="numeric whitespace-nowrap px-3 py-2.5 text-right text-[var(--text-soft)]">
                    {item.calculated === null || item.calculated === undefined ? (
                      <span
                        className="text-[var(--text-faint)]"
                        title="Hesaplanan değer gönderilmedi"
                      >
                        —
                      </span>
                    ) : (
                      <>
                        {formatValue(item.calculated, item.field, item.unit)}
                        {item.unit ? (
                          <span className="ml-1 text-[10px] text-[var(--text-faint)]">
                            {formatUnit(item.unit)}
                          </span>
                        ) : null}
                      </>
                    )}
                  </td>
                  <td
                    className={clsx(
                      "numeric whitespace-nowrap px-3 py-2.5 text-right",
                      blocking ? "text-[var(--danger)]" : "text-[var(--text-soft)]",
                    )}
                  >
                    {formatDelta(item.delta, item.unit)}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-soft)]">{item.tolerance || "—"}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                        TONE_BADGE_CLASSES[tone],
                      )}
                    >
                      {blocking ? (
                        <AlertTriangle size={11} aria-hidden="true" />
                      ) : null}
                      {DISCREPANCY_STATUS_LABELS[item.status] ?? item.status}
                    </span>
                    <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                      Önem: {SEVERITY_LABELS[item.severity]}
                    </p>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] leading-relaxed text-[var(--text-soft)]">
                    {item.message}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="border-t hairline px-4 py-2.5 text-[10px] leading-relaxed text-[var(--text-faint)]">
        Engelleyici satırlar kabul akışını durdurur; düzeltme ilgili hesap sekmesinde yapılır ve
        analiz yeniden çalıştırılır.
      </p>
    </div>
  );
}
