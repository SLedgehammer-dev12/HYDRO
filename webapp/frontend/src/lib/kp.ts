import type { SectionMeta, SessionListItem } from "./types";

/**
 * Boru hattı KP (Kilometre Point / Chainage) ayrıştırıcı, biçimleyici ve
 * ardışık kesit (section) KP süreklilik denetleyicisi.
 *
 * Desteklenen giriş biçimleri:
 *  - Standart chainage: "0+000", "12+000", "KP 12+345", "12+345,5" -> 12345.5 m
 *  - Birimli değer: "12.5 km", "12,5 km" -> 12500 m; "12000 m" -> 12000 m
 *  - Düz metre: "0" -> 0 m, "12000" -> 12000 m
 */
export function parseKpMeters(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) && raw >= 0 ? raw : null;
  }
  const cleaned = raw
    .trim()
    .replace(/^kp\s*[:=-]?\s*/i, "")
    .trim();
  if (!cleaned) return null;

  /* 1) Chainage: "12+345" veya "12+345,5" */
  const chainageMatch = /^(\d+)\s*\+\s*(\d+(?:[.,]\d+)?)$/.exec(cleaned);
  if (chainageMatch) {
    const km = Number(chainageMatch[1]);
    const meters = Number(chainageMatch[2].replace(",", "."));
    if (Number.isFinite(km) && Number.isFinite(meters)) {
      return km * 1000 + meters;
    }
  }

  /* 2) "12.5 km" / "12,5 km" */
  const kmMatch = /^(\d+(?:[.,]\d+)?)\s*km$/i.exec(cleaned);
  if (kmMatch) {
    const km = Number(kmMatch[1].replace(",", "."));
    return Number.isFinite(km) ? km * 1000 : null;
  }

  /* 3) "12000 m" veya düz sayı ("0", "12000") */
  const meterMatch = /^(\d+(?:[.,]\d+)?)\s*m?$/i.exec(cleaned.replace(/\s+/g, ""));
  if (meterMatch) {
    const value = Number(meterMatch[1].replace(",", "."));
    return Number.isFinite(value) && value >= 0 ? value : null;
  }

  return null;
}

/** Metre değerini standart "K+MMM" (ör. 12000 -> "12+000") biçimine çevirir. */
export function formatKp(meters: number | null | undefined): string {
  if (meters === null || meters === undefined || !Number.isFinite(meters) || meters < 0) {
    return "";
  }
  const rounded = Math.round(meters * 10) / 10;
  const km = Math.floor(rounded / 1000);
  const rem = rounded - km * 1000;
  const wholeMeters = Math.floor(rem);
  const frac = Math.round((rem - wholeMeters) * 10);
  const padded = String(wholeMeters).padStart(3, "0");
  return frac > 0 ? `${km}+${padded},${frac}` : `${km}+${padded}`;
}

/** Kullanıcının girdiği KP metnini okunabilir chainage biçimine normalize eder. */
export function normalizeKpText(raw: string | null | undefined): string {
  if (!raw) return "";
  const meters = parseKpMeters(raw);
  return meters !== null ? formatKp(meters) : raw.trim();
}

/** "KP 0+000 – 12+000" özet metni üretir. */
export function formatKpLocation(startKp?: string, endKp?: string, fallbackLocation?: string): string {
  const s = normalizeKpText(startKp);
  const e = normalizeKpText(endKp);
  if (s && e) return `KP ${s} – ${e}`;
  if (s) return `KP ${s} →`;
  if (e) return `→ KP ${e}`;
  return fallbackLocation?.trim() || "";
}

/** Eski kayıtlarda `location` içinde "KP 0+000 – 12+000" varsa başlangıç/bitiş KP'yi çıkarır. */
export function extractKpFromLocation(location: string | undefined): { start_kp: string; end_kp: string } {
  if (!location) return { start_kp: "", end_kp: "" };
  const matches = location.match(/\d+\s*\+\s*\d+(?:[.,]\d+)?/g);
  if (matches && matches.length >= 2) {
    return {
      start_kp: normalizeKpText(matches[0]),
      end_kp: normalizeKpText(matches[1]),
    };
  }
  return { start_kp: "", end_kp: "" };
}

export type KpContinuityState =
  | "match"
  | "first_ok"
  | "gap"
  | "overlap"
  | "invalid_range"
  | "missing";

export interface SectionKpCheck {
  sessionId: string;
  sectionLabel: string;
  startKp: string;
  endKp: string;
  startM: number | null;
  endM: number | null;
  lengthM: number | null;
  state: KpContinuityState;
  tone: "pass" | "warning" | "fail" | "pending";
  badgeLabel: string;
  detail: string;
  /** Bir önceki kesitin bitiş KP'si ile karşılaştırma */
  prevCheck?: {
    prevLabel: string;
    prevEndKp: string;
    deltaM: number;
    matched: boolean;
  };
  /** Bir sonraki kesitin başlangıç KP'si ile karşılaştırma */
  nextCheck?: {
    nextLabel: string;
    nextStartKp: string;
    deltaM: number;
    matched: boolean;
  };
}

export interface ProjectKpContinuitySummary {
  orderedIds: string[];
  byId: Record<string, SectionKpCheck>;
  status: "pass" | "warning" | "fail" | "pending";
  headline: string;
  issues: string[];
}

const KP_TOLERANCE_M = 0.5;

function sectionDisplayLabel(session: SessionListItem): string {
  const no = session.section_meta?.section_no?.trim();
  if (no) return no;
  return session.name.split("·")[0]?.trim() || session.name;
}

export function resolveSectionMeta(session: SessionListItem): SectionMeta {
  const meta = session.section_meta;
  const fallback = extractKpFromLocation(meta?.location);
  return {
    section_no: meta?.section_no ?? "",
    description: meta?.description ?? "",
    location: meta?.location ?? "",
    start_kp: meta?.start_kp || fallback.start_kp || "",
    end_kp: meta?.end_kp || fallback.end_kp || "",
    test_date: meta?.test_date ?? "",
    test_type: meta?.test_type ?? "Hidrostatik test",
    notes: meta?.notes ?? "",
  };
}

/**
 * Bir projedeki kesitleri sıraya dizer ve her kesitin:
 *  1) Kendi Başlangıç KP < Bitiş KP geçerliliğini,
 *  2) Önceki kesitin Bitiş KP'si == bu kesitin Başlangıç KP'si eşitliğini,
 *  3) Bu kesitin Bitiş KP'si == sonraki kesitin Başlangıç KP'si eşitliğini
 * denetler.
 */
export function evaluateProjectKpContinuity(sections: SessionListItem[]): ProjectKpContinuitySummary {
  const enriched = sections.map((session) => {
    const meta = resolveSectionMeta(session);
    const startM = parseKpMeters(meta.start_kp);
    const endM = parseKpMeters(meta.end_kp);
    return {
      session,
      label: sectionDisplayLabel(session),
      startKp: startM !== null ? formatKp(startM) : meta.start_kp.trim(),
      endKp: endM !== null ? formatKp(endM) : meta.end_kp.trim(),
      startM,
      endM,
    };
  });

  /* Sıralama: önce kesit no / ad doğal sırası (K-01, K-02...), eşitse başlangıç KP */
  const ordered = [...enriched].sort((a, b) => {
    const byLabel = a.label.localeCompare(b.label, "tr", { numeric: true });
    if (byLabel !== 0) return byLabel;
    if (a.startM !== null && b.startM !== null && a.startM !== b.startM) {
      return a.startM - b.startM;
    }
    return a.session.name.localeCompare(b.session.name, "tr", { numeric: true });
  });

  const byId: Record<string, SectionKpCheck> = {};
  const issues: string[] = [];

  ordered.forEach((item, index) => {
    const prev = index > 0 ? ordered[index - 1] : null;
    const next = index < ordered.length - 1 ? ordered[index + 1] : null;

    const lengthM =
      item.startM !== null && item.endM !== null ? item.endM - item.startM : null;

    let prevCheck: SectionKpCheck["prevCheck"];
    if (prev && prev.endM !== null && item.startM !== null) {
      const deltaM = item.startM - prev.endM;
      prevCheck = {
        prevLabel: prev.label,
        prevEndKp: prev.endKp,
        deltaM,
        matched: Math.abs(deltaM) <= KP_TOLERANCE_M,
      };
    }

    let nextCheck: SectionKpCheck["nextCheck"];
    if (next && item.endM !== null && next.startM !== null) {
      const deltaM = next.startM - item.endM;
      nextCheck = {
        nextLabel: next.label,
        nextStartKp: next.startKp,
        deltaM,
        matched: Math.abs(deltaM) <= KP_TOLERANCE_M,
      };
    }

    if (item.startM === null || item.endM === null) {
      byId[item.session.id] = {
        sessionId: item.session.id,
        sectionLabel: item.label,
        startKp: item.startKp,
        endKp: item.endKp,
        startM: item.startM,
        endM: item.endM,
        lengthM: null,
        state: "missing",
        tone: "pending",
        badgeLabel: "KP eksik",
        detail: "Başlangıç ve bitiş KP noktaları girilmelidir.",
        prevCheck,
        nextCheck,
      };
      return;
    }

    if (item.endM <= item.startM) {
      const msg = `${item.label}: Bitiş KP (${item.endKp}), başlangıç KP (${item.startKp}) değerinden büyük olmalıdır.`;
      issues.push(msg);
      byId[item.session.id] = {
        sessionId: item.session.id,
        sectionLabel: item.label,
        startKp: item.startKp,
        endKp: item.endKp,
        startM: item.startM,
        endM: item.endM,
        lengthM,
        state: "invalid_range",
        tone: "fail",
        badgeLabel: "Ters KP aralığı",
        detail: msg,
        prevCheck,
        nextCheck,
      };
      return;
    }

    /* Önceki kesitle süreklilik kontrolü */
    if (prevCheck && !prevCheck.matched) {
      const absDelta = Math.round(Math.abs(prevCheck.deltaM));
      const isGap = prevCheck.deltaM > 0;
      const msg = isGap
        ? `${prevCheck.prevLabel} bitiş KP (${prevCheck.prevEndKp}) ile ${item.label} başlangıç KP (${item.startKp}) eşleşmiyor (+${absDelta} m boşluk).`
        : `${prevCheck.prevLabel} bitiş KP (${prevCheck.prevEndKp}) ile ${item.label} başlangıç KP (${item.startKp}) eşleşmiyor (${absDelta} m bindirme).`;
      issues.push(msg);
      byId[item.session.id] = {
        sessionId: item.session.id,
        sectionLabel: item.label,
        startKp: item.startKp,
        endKp: item.endKp,
        startM: item.startM,
        endM: item.endM,
        lengthM,
        state: isGap ? "gap" : "overlap",
        tone: "fail",
        badgeLabel: isGap ? `+${absDelta} m boşluk` : `${absDelta} m bindirme`,
        detail: msg,
        prevCheck,
        nextCheck,
      };
      return;
    }

    /* Sonraki kesitle süreklilik kontrolü (bu satırda da uyarı gösterelim) */
    if (nextCheck && !nextCheck.matched) {
      const absDelta = Math.round(Math.abs(nextCheck.deltaM));
      const isGap = nextCheck.deltaM > 0;
      byId[item.session.id] = {
        sessionId: item.session.id,
        sectionLabel: item.label,
        startKp: item.startKp,
        endKp: item.endKp,
        startM: item.startM,
        endM: item.endM,
        lengthM,
        state: isGap ? "gap" : "overlap",
        tone: "warning",
        badgeLabel: `Sonraki ile ${isGap ? `+${absDelta} m` : `${absDelta} m`} fark`,
        detail: `Bitiş KP (${item.endKp}) ile sonraki kesit ${nextCheck.nextLabel} başlangıç KP (${nextCheck.nextStartKp}) eşleşmiyor.`,
        prevCheck,
        nextCheck,
      };
      return;
    }

    byId[item.session.id] = {
      sessionId: item.session.id,
      sectionLabel: item.label,
      startKp: item.startKp,
      endKp: item.endKp,
      startM: item.startM,
      endM: item.endM,
      lengthM,
      state: prevCheck ? "match" : "first_ok",
      tone: "pass",
      badgeLabel: prevCheck ? "KP eşleşiyor" : nextCheck?.matched ? "KP eşleşiyor" : "Başlangıç kesiti",
      detail:
        prevCheck && nextCheck
          ? `${prevCheck.prevLabel} (${prevCheck.prevEndKp}) → ${item.label} → ${nextCheck.nextLabel} (${nextCheck.nextStartKp}) uç uca uyumlu.`
          : prevCheck
            ? `Önceki kesit ${prevCheck.prevLabel} bitiş KP (${prevCheck.prevEndKp}) ile tam eşleşiyor.`
            : nextCheck
              ? `Bitiş KP (${item.endKp}), sonraki kesit ${nextCheck.nextLabel} başlangıç KP (${nextCheck.nextStartKp}) ile tam eşleşiyor.`
              : `KP aralığı geçerli (${item.startKp} → ${item.endKp}).`,
      prevCheck,
      nextCheck,
    };
  });

  const missingCount = Object.values(byId).filter((item) => item.state === "missing").length;

  let status: ProjectKpContinuitySummary["status"] = "pass";
  let headline = "";

  if (ordered.length === 0) {
    status = "pending";
    headline = "Projede henüz kesit kaydı yok.";
  } else if (issues.length > 0) {
    status = "fail";
    headline = `${issues.length} kesitte KP süreklilik uyuşmazlığı tespit edildi.`;
  } else if (missingCount > 0) {
    status = "warning";
    headline = `${missingCount} kesitte başlangıç/bitiş KP bilgisi henüz girilmedi.`;
  } else if (ordered.length === 1) {
    const only = ordered[0];
    status = "pass";
    headline = `Tek kesit kayıtlı: KP ${only.startKp} → ${only.endKp} (${Math.round((only.endM ?? 0) - (only.startM ?? 0))} m).`;
  } else {
    const first = ordered[0];
    const last = ordered[ordered.length - 1];
    status = "pass";
    headline = `Tüm ardışık kesitlerin (${ordered.length} kesit) bitiş ve başlangıç KP noktaları uç uca eşleşiyor: KP ${first.startKp} → ${last.endKp}.`;
  }

  return {
    orderedIds: ordered.map((item) => item.session.id),
    byId,
    status,
    headline,
    issues,
  };
}
