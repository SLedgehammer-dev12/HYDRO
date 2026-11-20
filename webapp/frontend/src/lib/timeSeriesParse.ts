import { parseNumber } from "./format";
import type { TimeSeriesRecordInput } from "./types";

function splitColumns(line: string): string[] {
  if (line.includes("\t")) return line.split("\t").map((cell) => cell.trim());
  if (line.includes(";")) return line.split(";").map((cell) => cell.trim());
  const byMultiSpace = line.split(/\s{2,}/).map((cell) => cell.trim());
  if (byMultiSpace.length >= 3) return byMultiSpace;
  // Tek boşlukla ayrılmış zaman + sayılar ("2026-11-14T08:00:00Z 80.2 15.1" veya "08:00 80,2 15,1")
  const trimmed = line.trim();
  const tsSpaceMatch = trimmed.match(
    /^(\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{1,2}[./-]\d{1,2}[./-]\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$/,
  );
  if (tsSpaceMatch) {
    const [, headTs, tail] = tsSpaceMatch;
    if (tail.includes(",")) {
      const commaParts = tail.split(",").map((p) => p.trim());
      if (commaParts.length >= 2 && commaParts.every((p) => /^-?\d+(?:\.\d+)?$/.test(p))) {
        return [headTs.trim(), ...commaParts];
      }
    }
    const wsParts = tail.split(/\s+/).map((p) => p.trim()).filter(Boolean);
    if (wsParts.length >= 2) {
      return [headTs.trim(), ...wsParts];
    }
  }
  if (trimmed.includes(",")) {
    const commaCols = trimmed.split(",").map((c) => c.trim());
    if (commaCols.length >= 3) return commaCols;
  }
  return trimmed.split(/\s+/).filter(Boolean);
}

function parseHhMmSeconds(raw: string): number | null {
  const m = raw.trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  const ss = Number(m[3] ?? "0");
  if (hh < 0 || hh > 23 || mm < 0 || mm > 59 || ss < 0 || ss > 59) return null;
  return hh * 3600 + mm * 60 + ss;
}

function parseExplicitTimestamp(raw: string): Date | null {
  const text = raw.trim();
  if (!text) return null;
  const trMatch = text.match(
    /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (trMatch) {
    const day = Number(trMatch[1]);
    const month = Number(trMatch[2]);
    const year = Number(trMatch[3]);
    const hh = Number(trMatch[4]);
    const mm = Number(trMatch[5]);
    const ss = Number(trMatch[6] ?? "0");
    if (month < 1 || month > 12 || day < 1 || day > 31 || hh > 23 || mm > 59 || ss > 59) {
      return null;
    }
    const utcMs = Date.UTC(year, month - 1, day, hh, mm, ss);
    const dt = new Date(utcMs);
    if (
      dt.getUTCFullYear() !== year ||
      dt.getUTCMonth() !== month - 1 ||
      dt.getUTCDate() !== day
    ) {
      return null;
    }
    return dt;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    const normalized = text.includes("T") ? text : text.replace(/\s+/, "T");
    const withTz = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`;
    const parsed = new Date(withTz);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function resolveBaseUtcMidnight(baseDateIso?: string): number {
  if (baseDateIso && /^\d{4}-\d{2}-\d{2}/.test(baseDateIso.trim())) {
    const [y, m, d] = baseDateIso.trim().slice(0, 10).split("-").map(Number);
    if (y && m && d) return Date.UTC(y, m - 1, d, 0, 0, 0);
  }
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0);
}

export function parseTimeSeriesPaste(
  text: string,
  baseDateIso?: string,
): { records: TimeSeriesRecordInput[]; skipped: number; error: string | null } {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return { records: [], skipped: 0, error: "Yapıştırılacak en az bir satır girin." };
  }

  const baseMidnightMs = resolveBaseUtcMidnight(baseDateIso);
  let dayOffset = 0;
  let prevSecondsOfDay: number | null = null;
  const records: TimeSeriesRecordInput[] = [];
  let skipped = 0;

  for (let i = 0; i < lines.length; i += 1) {
    const cols = splitColumns(lines[i]);
    const startsWithTimestamp =
      cols.length > 0 &&
      (parseExplicitTimestamp(cols[0]) !== null || parseHhMmSeconds(cols[0]) !== null);
    const isHeaderRow =
      i === 0 &&
      lines.length > 1 &&
      !startsWithTimestamp &&
      /[a-zA-ZğüşöçıİĞÜŞÖÇ]/.test(lines[i]);
    if (cols.length < 3) {
      if (isHeaderRow) {
        skipped += 1;
        continue;
      }
      return {
        records: [],
        skipped: 0,
        error: `${i + 1}. satırda en az 3 sütun olmalı (Zaman, Basınç, Sıcaklık).`,
      };
    }

    const pVal = parseNumber(cols[1]);
    const tVal = parseNumber(cols[2]);
    if (pVal === null || tVal === null || !Number.isFinite(pVal) || !Number.isFinite(tVal)) {
      if (isHeaderRow) {
        skipped += 1;
        continue;
      }
      return {
        records: [],
        skipped: 0,
        error: `${i + 1}. satırda basınç (${cols[1]}) veya sıcaklık (${cols[2]}) sayısal değil.`,
      };
    }

    let ts: Date | null = parseExplicitTimestamp(cols[0]);
    if (ts === null) {
      const sec = parseHhMmSeconds(cols[0]);
      if (sec === null) {
        return {
          records: [],
          skipped: 0,
          error: `${i + 1}. satırda zaman formatı tanınmadı ("${cols[0]}"). Örnek: 2026-11-14T08:00Z, 14.11.2026 08:00 veya 08:00.`,
        };
      }
      if (prevSecondsOfDay !== null && sec + dayOffset * 86_400 < prevSecondsOfDay - 1800) {
        dayOffset += 1;
      }
      prevSecondsOfDay = sec + dayOffset * 86_400;
      ts = new Date(baseMidnightMs + prevSecondsOfDay * 1000);
    }

    let volumeM3: number | null = null;
    const rawVol = cols[3]?.trim() ?? "";
    if (rawVol && rawVol !== "-" && rawVol !== "—") {
      const parsedVol = parseNumber(rawVol);
      if (parsedVol === null || !Number.isFinite(parsedVol)) {
        return {
          records: [],
          skipped: 0,
          error: `${i + 1}. satırda hacim değeri geçersiz ("${rawVol}").`,
        };
      }
      volumeM3 = parsedVol;
    }

    const notes = cols.slice(4).join(" ").trim().slice(0, 500);
    records.push({
      timestamp: ts.toISOString(),
      pressure_bar: pVal,
      temperature_c: tVal,
      volume_m3: volumeM3,
      notes,
      source: "batch",
    });
  }

  if (records.length === 0) {
    return { records: [], skipped, error: "Geçerli veri satırı bulunamadı." };
  }
  return { records, skipped, error: null };
}

export function formatTsShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  const dd = String(dt.getUTCDate()).padStart(2, "0");
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const hh = String(dt.getUTCHours()).padStart(2, "0");
  const mi = String(dt.getUTCMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${mi}`;
}

export function toLocalDateTimeInputValue(date: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
