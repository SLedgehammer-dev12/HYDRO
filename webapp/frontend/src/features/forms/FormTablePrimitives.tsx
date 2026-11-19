import { useState, type ClipboardEvent } from "react";
import { ClipboardPaste, Plus } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { Button } from "../../components/ui/Button";
import { isTabularClipboard } from "./pasteUtils";

export type DraftData = Record<string, unknown>;

export function toRecord(val: unknown): Record<string, unknown> {
  return val && typeof val === "object" && !Array.isArray(val) ? (val as Record<string, unknown>) : {};
}

export function toList(val: unknown): Array<Record<string, unknown>> {
  return Array.isArray(val)
    ? (val.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>)
    : [];
}

export function numVal(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  if (v === null || v === undefined || v === "") return "";
  return String(v);
}

export function strVal(obj: Record<string, unknown>, key: string): string {
  const v = obj[key];
  return v === null || v === undefined ? "" : String(v);
}

export function CellInput({
  value,
  onChange,
  placeholder = "—",
  type = "text",
  align = "right",
  ariaLabel,
  className = "",
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  type?: "text" | "number";
  align?: "left" | "right";
  ariaLabel: string;
  className?: string;
}) {
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState(value);
  const isNumeric = type === "number";
  const displayValue = isNumeric && focused ? draft : value;

  return (
    <input
      type="text"
      inputMode={isNumeric ? "decimal" : undefined}
      autoCorrect="off"
      spellCheck={false}
      value={displayValue}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onFocus={() => {
        setFocused(true);
        setDraft(value);
      }}
      onBlur={() => {
        setFocused(false);
      }}
      onChange={(e) => {
        const raw = e.target.value;
        setDraft(raw);
        const normalized =
          isNumeric && raw.includes(",") && !raw.includes(".") ? raw.replace(",", ".") : raw;
        onChange(normalized);
      }}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing) return;
        if (e.key !== "Enter" && e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        const input = e.currentTarget;
        const cell = input.closest("td, th");
        const row = cell?.closest("tr");
        const tbody = row?.parentElement;
        if (!cell || !row || !tbody) return;
        const cellIndex = Array.from(row.children).indexOf(cell);
        if (cellIndex < 0) return;
        const rows = Array.from(tbody.children).filter(
          (el): el is HTMLTableRowElement => el.tagName === "TR",
        );
        const rowIndex = rows.indexOf(row as HTMLTableRowElement);
        const delta = e.key === "ArrowUp" ? -1 : 1;
        const targetRow = rows[rowIndex + delta];
        if (!targetRow) return;
        const targetCell = targetRow.children[cellIndex];
        const targetInput = targetCell?.querySelector<HTMLInputElement>(
          "input:not([disabled]):not([readonly])",
        );
        if (targetInput) {
          e.preventDefault();
          targetInput.focus();
          targetInput.select();
        }
      }}
      className={`h-7 rounded border border-[var(--border)] bg-[var(--canvas)] px-2 font-mono text-[11px] text-[var(--text)] focus:border-[var(--primary)] focus:outline-none ${
        align === "right" ? "text-right" : "text-left"
      } ${className}`}
    />
  );
}

export function useTableClipboardPaste(
  parser: (rawText: string) => Array<Record<string, unknown>>,
  onAppendRows: (rows: Array<Record<string, unknown>>) => void,
) {
  const pushToast = useAppStore((state) => state.pushToast);

  return (event: ClipboardEvent<HTMLElement>) => {
    const raw = event.clipboardData?.getData("text/plain") ?? "";
    if (!isTabularClipboard(raw)) return;
    const parsed = parser(raw);
    if (parsed.length === 0) return;
    event.preventDefault();
    onAppendRows(parsed);
    pushToast("success", "Tablo satırları eklendi", `${parsed.length} satır panodan aktarıldı.`);
  };
}

export function PasteRowsTray({
  hint,
  parser,
  hasExistingRows,
  onApplyRows,
}: {
  hint: string;
  parser: (rawText: string) => Array<Record<string, unknown>>;
  hasExistingRows: boolean;
  onApplyRows: (rows: Array<Record<string, unknown>>, replace: boolean) => void;
}) {
  const pushToast = useAppStore((state) => state.pushToast);
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");

  function submit(replace: boolean) {
    const parsed = parser(raw);
    if (parsed.length === 0) {
      pushToast(
        "warning",
        "Uygun satır bulunamadı",
        "Excel veya metin tablosundan en az bir sayısal satır yapıştırın.",
      );
      return;
    }
    onApplyRows(parsed, replace);
    pushToast(
      "success",
      replace ? "Tablo güncellendi" : "Satırlar eklendi",
      `${parsed.length} satır aktarıldı.`,
    );
    setRaw("");
    setOpen(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <Button
          size="sm"
          variant="ghost"
          icon={<ClipboardPaste size={12} />}
          onClick={() => setOpen((v) => !v)}
          title="Excel'den kopyalanan çoklu satırları topluca yapıştır"
        >
          {open ? "Yapıştırmayı Kapat" : "Excel'den Yapıştır"}
        </Button>
      </div>

      {open ? (
        <div className="space-y-2 rounded-xl border border-[var(--primary-border)] bg-[var(--surface-2)] p-3">
          <p className="text-[11px] font-medium text-[var(--text-soft)]">
            Excel veya BOTAŞ tablosundan kopyaladığınız satırları aşağıya yapıştırın (veya doğrudan
            tablodaki bir hücreye <kbd className="kbd">Ctrl+V</kbd> yapın):
          </p>
          <p className="font-mono text-[10px] text-[var(--text-faint)]">Sütun sırası: {hint}</p>
          <textarea
            rows={4}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="08:00&#9;60.0&#9;12.0&#9;..."
            className="textarea min-h-[76px] font-mono text-[11px]"
          />
          <div className="flex flex-wrap justify-end gap-2">
            {hasExistingRows ? (
              <Button size="sm" variant="ghost" onClick={() => submit(true)}>
                Mevcut Satırları Değiştir
              </Button>
            ) : null}
            <Button size="sm" variant="primary" icon={<Plus size={12} />} onClick={() => submit(false)}>
              Satırları Ekle
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
