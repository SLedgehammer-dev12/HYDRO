import type {
  DraftSectionItem,
  PlanProfileScanResponse,
  SectionMeta,
  SegmentRow,
  SessionListItem,
  SimilarProjectCandidate,
} from "./types";

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
  /** Tüm section'ların uzunlukları toplamı (Σ Section) */
  totalSectionsLengthM: number;
  /** İlk section başlangıç KP ile son section bitiş KP arasındaki toplam boru hattı boyu */
  pipelineSpanM: number | null;
  /** Σ Section == Boru hattı toplam boyu kontrolü */
  sumMatchesPipeline: boolean;
}

export interface SegmentRowCheck {
  id: string;
  index: number;
  startStationM: number;
  endStationM: number;
  startKp: string;
  endKp: string;
  lengthM: number;
  volumeM3: number | null;
  stationMatch: boolean;
  dimensionValid: boolean;
  status: "pass" | "warning" | "fail";
  note: string;
}

export interface SegmentConsistencySummary {
  hasSegments: boolean;
  sectionStartM: number;
  sectionEndM: number | null;
  sectionStartKp: string;
  sectionEndKp: string;
  targetSectionLengthM: number | null;
  totalSegmentLengthM: number;
  deltaLengthM: number | null;
  lengthMatchesSection: boolean;
  status: "pass" | "warning" | "fail" | "neutral";
  badgeLabel: string;
  headline: string;
  issues: string[];
  rows: SegmentRowCheck[];
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
  const totalSectionsLengthM = Math.round(
    Object.values(byId).reduce((sum, item) => sum + (item.lengthM && item.lengthM > 0 ? item.lengthM : 0), 0) * 100,
  ) / 100;

  const validOrdered = ordered.filter((item) => item.startM !== null && item.endM !== null && item.endM > item.startM);
  const pipelineSpanM =
    validOrdered.length > 0
      ? Math.round(((validOrdered[validOrdered.length - 1].endM ?? 0) - (validOrdered[0].startM ?? 0)) * 100) / 100
      : null;
  const sumMatchesPipeline =
    pipelineSpanM !== null && missingCount === 0
      ? Math.abs(totalSectionsLengthM - pipelineSpanM) <= KP_TOLERANCE_M
      : false;

  if (pipelineSpanM !== null && missingCount === 0 && !sumMatchesPipeline) {
    const diff = Math.round(totalSectionsLengthM - pipelineSpanM);
    issues.push(
      `Section uzunlukları toplamı (${totalSectionsLengthM} m) ile boru hattı KP aralığı (${pipelineSpanM} m) eşleşmiyor (${diff > 0 ? `+${diff}` : diff} m fark).`,
    );
  }

  let status: ProjectKpContinuitySummary["status"] = "pass";
  let headline = "";

  if (ordered.length === 0) {
    status = "pending";
    headline = "Projede henüz Test Bölümü (Section) kaydı yok.";
  } else if (issues.length > 0) {
    status = "fail";
    headline = `${issues.length} noktada KP süreklilik veya toplam uzunluk uyuşmazlığı tespit edildi.`;
  } else if (missingCount > 0) {
    status = "warning";
    headline = `${missingCount} Test Bölümünde (Section) başlangıç/bitiş KP bilgisi henüz girilmedi.`;
  } else if (ordered.length === 1) {
    const only = ordered[0];
    status = "pass";
    headline = `Tek Test Bölümü (Section) kayıtlı: KP ${only.startKp} → ${only.endKp} (${Math.round((only.endM ?? 0) - (only.startM ?? 0))} m).`;
  } else {
    const first = ordered[0];
    const last = ordered[ordered.length - 1];
    status = "pass";
    headline = `Tüm Test Bölümleri (${ordered.length} Section) uç uca eşleşiyor ve toplamları boru hattı boyuna eşit: KP ${first.startKp} → ${last.endKp} (Σ = ${Math.round(totalSectionsLengthM)} m).`;
  }

  return {
    orderedIds: ordered.map((item) => item.session.id),
    byId,
    status,
    headline,
    issues,
    totalSectionsLengthM,
    pipelineSpanM,
    sumMatchesPipeline,
  };
}

/**
 * Bir Test Bölümü (Section) içindeki alt boru parçalarının (Segment) kontrolü:
 *  1) Σ Segment Uzunluğu == Section Uzunluğu (ΔKP veya geometry.length_m)
 *  2) Ardışık segmentlerin istasyon ve KP sürekliliği (Section Başlangıç KP -> Section Bitiş KP)
 *  3) Her segmentin OD / WT / Uzunluk fiziksel geçerliliği
 */
export function evaluateSegmentConsistency(params: {
  segments: SegmentRow[];
  sectionMeta: SectionMeta;
  fallbackLengthM: number | null;
}): SegmentConsistencySummary {
  const { segments, sectionMeta, fallbackLengthM } = params;
  const kpStartM = parseKpMeters(sectionMeta.start_kp);
  const kpEndM = parseKpMeters(sectionMeta.end_kp);
  const sectionStartM = kpStartM ?? 0;
  const kpSpanM =
    kpStartM !== null && kpEndM !== null && kpEndM > kpStartM ? kpEndM - kpStartM : null;
  const targetSectionLengthM = kpSpanM ?? (fallbackLengthM && fallbackLengthM > 0 ? fallbackLengthM : null);
  const sectionEndM =
    kpEndM ?? (targetSectionLengthM !== null ? sectionStartM + targetSectionLengthM : null);
  const sectionStartKp = formatKp(sectionStartM);
  const sectionEndKp = sectionEndM !== null ? formatKp(sectionEndM) : "";

  if (segments.length === 0) {
    return {
      hasSegments: false,
      sectionStartM,
      sectionEndM,
      sectionStartKp,
      sectionEndKp,
      targetSectionLengthM,
      totalSegmentLengthM: 0,
      deltaLengthM: null,
      lengthMatchesSection: true,
      status: "neutral",
      badgeLabel: "Tek tip boru modu",
      headline:
        "Segment girilmedi; bu Test Bölümü (Section) boyunca dış çap ve et kalınlığı sabit kabul edilir.",
      issues: [],
      rows: [],
    };
  }

  const issues: string[] = [];
  const rows: SegmentRowCheck[] = [];
  let runningM = 0;

  segments.forEach((seg, index) => {
    const len = seg.length_m && seg.length_m > 0 ? seg.length_m : 0;
    const expectedStartM = runningM;
    const recordedStartM = seg.start_station_m ?? expectedStartM;
    const stationMatch = Math.abs(recordedStartM - expectedStartM) <= KP_TOLERANCE_M;

    const absStartM = sectionStartM + expectedStartM;
    const absEndM = absStartM + len;
    const startKp = formatKp(absStartM);
    const endKp = formatKp(absEndM);

    const od = seg.outside_diameter_mm;
    const wt = seg.wall_thickness_mm;
    const smys = seg.smys_mpa;
    const smysValid =
      smys === null ||
      smys === undefined ||
      (typeof smys === "number" && Number.isFinite(smys) && smys > 0);
    const dimensionValid =
      od !== null &&
      od > 0 &&
      wt !== null &&
      wt > 0 &&
      wt * 2 < od &&
      seg.length_m !== null &&
      seg.length_m > 0 &&
      smysValid;

    const volumeM3 =
      dimensionValid && od !== null && wt !== null
        ? Math.PI * ((od / 2 - wt) / 1000) ** 2 * len
        : null;

    let status: SegmentRowCheck["status"] = "pass";
    let note = `KP ${startKp} → ${endKp}`;

    if (!dimensionValid) {
      status = "fail";
      if (!smysValid) {
        note = "Segment SMYS > 0 MPa olmalıdır.";
      } else if (!seg.length_m || seg.length_m <= 0) {
        note = "Segment uzunluğu > 0 olmalıdır.";
      } else if (!od || od <= 0 || !wt || wt <= 0) {
        note = "OD ve WT > 0 olmalıdır.";
      } else {
        note = "2·WT < OD olmalıdır (et kalınlığı dış yarıçapı aşamaz).";
      }
      issues.push(`Segment #${index + 1}: ${note}`);
    } else if (!stationMatch) {
      status = "warning";
      note = `İstasyon kayması: beklenen ${Math.round(expectedStartM)} m, kayıtlı ${Math.round(recordedStartM)} m.`;
      issues.push(`Segment #${index + 1}: ${note}`);
    }

    rows.push({
      id: seg.id,
      index,
      startStationM: expectedStartM,
      endStationM: expectedStartM + len,
      startKp,
      endKp,
      lengthM: len,
      volumeM3,
      stationMatch,
      dimensionValid,
      status,
      note,
    });

    runningM += len;
  });

  const totalSegmentLengthM = Math.round(runningM * 100) / 100;
  const deltaLengthM =
    targetSectionLengthM !== null
      ? Math.round((totalSegmentLengthM - targetSectionLengthM) * 100) / 100
      : null;
  // Gerçek sahada "Bölüm Uzunluğu" (boru metresi) ile KP aralığı
  // fitting/elbow farkı kadar ayrışır (örn. 3.722,21 m vs 3.697 m).
  // Bu yüzden toplam uzunluk denetimi max(0,5 m, %0,5) tolerans kullanır;
  // ardışık KP sürekliliği ise 0,5 m'de kalır.
  const sectionLengthToleranceM =
    targetSectionLengthM === null
      ? KP_TOLERANCE_M
      : Math.max(KP_TOLERANCE_M, targetSectionLengthM * 0.005);
  const lengthMatchesSection =
    deltaLengthM === null ? true : Math.abs(deltaLengthM) <= sectionLengthToleranceM;

  if (!lengthMatchesSection && deltaLengthM !== null && targetSectionLengthM !== null) {
    const absDiff = Math.round(Math.abs(deltaLengthM));
    const endSegmentKp = formatKp(sectionStartM + totalSegmentLengthM);
    if (deltaLengthM < 0) {
      issues.unshift(
        `Segment uzunlukları toplamı (${totalSegmentLengthM} m · bitiş KP ${endSegmentKp}), bu Test Bölümünün (Section) uzunluğundan (${targetSectionLengthM} m${sectionEndKp ? ` · bitiş KP ${sectionEndKp}` : ""}) ${absDiff} m eksik.`,
      );
    } else {
      issues.unshift(
        `Segment uzunlukları toplamı (${totalSegmentLengthM} m · bitiş KP ${endSegmentKp}), bu Test Bölümünün (Section) uzunluğunu (${targetSectionLengthM} m${sectionEndKp ? ` · bitiş KP ${sectionEndKp}` : ""}) +${absDiff} m aşıyor.`,
      );
    }
  }

  let status: SegmentConsistencySummary["status"] = "pass";
  let badgeLabel = "Segmentler Section ile uyumlu";
  let headline = "";

  if (issues.length > 0) {
    status = "fail";
    if (!lengthMatchesSection && deltaLengthM !== null) {
      const absDiff = Math.round(Math.abs(deltaLengthM));
      badgeLabel =
        deltaLengthM < 0 ? `Section'dan ${absDiff} m eksik` : `Section'ı +${absDiff} m aşıyor`;
    } else {
      badgeLabel = "Segment hatası var";
    }
    headline = issues[0];
  } else if (targetSectionLengthM !== null) {
    status = "pass";
    badgeLabel = "Σ Segment = Section";
    const diffM = Math.abs(deltaLengthM ?? 0);
    headline =
      diffM <= KP_TOLERANCE_M
        ? `${segments.length} segmentin toplam uzunluğu (${totalSegmentLengthM} m), Test Bölümü (Section) aralığı KP ${sectionStartKp} → ${sectionEndKp} (${Math.round(targetSectionLengthM)} m) ile birebir eşleşiyor.`
        : `${segments.length} segmentin toplam uzunluğu (${totalSegmentLengthM} m), Test Bölümü (Section) aralığı KP ${sectionStartKp} → ${sectionEndKp} (${Math.round(targetSectionLengthM)} m) ile uyumlu; fark ${diffM.toFixed(1)} m (izin verilen ±${sectionLengthToleranceM.toFixed(1)} m).`;
  } else {
    status = "pass";
    badgeLabel = `${segments.length} segment hazır`;
    headline = `${segments.length} segment tanımlı · toplam uzunluk ${totalSegmentLengthM} m (KP ${sectionStartKp} → ${formatKp(sectionStartM + totalSegmentLengthM)}).`;
  }

  return {
    hasSegments: true,
    sectionStartM,
    sectionEndM,
    sectionStartKp,
    sectionEndKp,
    targetSectionLengthM,
    totalSegmentLengthM,
    deltaLengthM,
    lengthMatchesSection,
    status,
    badgeLabel,
    headline,
    issues,
    rows,
  };
}

function normalizeSectionKey(raw: string): string {
  const cleaned = raw.trim().replace(/\s+/g, " ").toUpperCase();
  const kMatch = /^K\s*[-_.]?\s*0*(\d{1,3})$/.exec(cleaned);
  if (kMatch) {
    return `K-${String(Number(kMatch[1])).padStart(2, "0")}`;
  }
  const bMatch = /^(?:TEST\s*)?B[ÖO]L[ÜU]M[ÜU]?\s*[-_:.#]?\s*0*(\d{1,3}[A-Z]?)$/.exec(cleaned);
  if (bMatch) {
    return `BÖLÜM ${bMatch[1]}`;
  }
  return cleaned;
}

/**
 * Birden fazla plan-profil paftasından çıkan tarama sonuçlarını KP sırasına göre
 * tek taslak listesinde birleştirir, mevcut proje kesitleriyle `K-01` çakışmalarını
 * önler ve ardışık KP süreklilik denetimini günceller.
 */
export function mergePlanProfileScans(
  scans: PlanProfileScanResponse[],
  existingSessions: SessionListItem[] = [],
): { mergedScan: PlanProfileScanResponse; drafts: DraftSectionItem[] } {
  if (scans.length === 0) {
    return {
      mergedScan: {
        file_name: "",
        page_count: 0,
        extraction_method: "",
        strategy: "explicit",
        station_count: 0,
        elevation_point_count: 0,
        min_kp: "0+000",
        max_kp: "0+000",
        total_length_m: 0,
        pipe_meta: {
          outside_diameter_mm: null,
          wall_thickness_mm: null,
          design_pressure_bar: null,
          material_grade: "",
          smys_mpa: null,
        },
        profile_points: [],
        draft_sections: [],
        continuity_ok: true,
        continuity_issues: [],
        warnings: [],
      },
      drafts: [],
    };
  }

  const existingRanges = new Map<string, Array<{ s: number | null; e: number | null }>>();
  const existingOrderedEnds: Array<{ label: string; startM: number; endM: number; endKp: string }> = [];
  const usedKeys = new Set<string>();
  let bolumStyleCount = 0;
  let kStyleCount = 0;

  for (const sess of existingSessions) {
    const meta = resolveSectionMeta(sess);
    const label = meta.section_no || sectionDisplayLabel(sess);
    const norm = normalizeSectionKey(label);
    const sM = parseKpMeters(meta.start_kp);
    const eM = parseKpMeters(meta.end_kp);
    if (norm) {
      usedKeys.add(norm);
      const arr = existingRanges.get(norm) ?? [];
      arr.push({ s: sM, e: eM });
      existingRanges.set(norm, arr);
      if (/^BÖLÜM \d+/.test(norm)) bolumStyleCount += 1;
      if (/^K-\d+$/.test(norm)) kStyleCount += 1;
    }
    if (sM !== null && eM !== null && eM > sM) {
      existingOrderedEnds.push({ label, startM: sM, endM: eM, endKp: formatKp(eM) });
    }
  }

  const rawDrafts: DraftSectionItem[] = [];
  for (const scan of scans) {
    for (const row of scan.draft_sections) {
      const norm = normalizeSectionKey(row.section_no);
      if (/^BÖLÜM \d+/.test(norm)) bolumStyleCount += 1;
      const sm = parseKpMeters(row.start_kp) ?? row.start_m;
      const em = parseKpMeters(row.end_kp) ?? row.end_m;
      rawDrafts.push({
        ...row,
        start_m: sm,
        end_m: em,
        start_kp: Number.isFinite(sm) ? formatKp(sm) : row.start_kp,
        end_kp: Number.isFinite(em) ? formatKp(em) : row.end_kp,
        length_m: Number.isFinite(sm) && Number.isFinite(em) && em > sm ? Math.round((em - sm) * 100) / 100 : row.length_m,
        source_file: row.source_file || scan.file_name,
      });
    }
  }

  rawDrafts.sort((a, b) => a.start_m - b.start_m || a.end_m - b.end_m);

  const preferBolum = bolumStyleCount > 0 && kStyleCount === 0;
  const claimedInBatch = new Map<string, Array<{ s: number; e: number }>>();

  const nextFreeKey = (genericStyleOnly = false): string => {
    const useBolum = preferBolum && !genericStyleOnly;
    let n = 1;
    while (true) {
      const cand = useBolum ? `BÖLÜM ${n}` : `K-${String(n).padStart(2, "0")}`;
      if (!usedKeys.has(cand) && !claimedInBatch.has(cand)) {
        return cand;
      }
      n += 1;
    }
  };

  const drafts: DraftSectionItem[] = rawDrafts.map((row) => {
    const origNo = row.section_no.trim() || "K-01";
    let norm = normalizeSectionKey(origNo);
    const isGeneric = /^K-\d+$/.test(norm);

    const existingList = existingRanges.get(norm) ?? [];
    const collidesExistingDisjoint =
      existingList.length > 0 &&
      existingList.every(
        (ex) =>
          ex.s !== null &&
          ex.e !== null &&
          (row.end_m <= ex.s + 1.0 || row.start_m >= ex.e - 1.0),
      );
    const batchList = claimedInBatch.get(norm) ?? [];
    const collidesInBatch = batchList.some(
      (b) => row.end_m <= b.s + 1.0 || row.start_m >= b.e - 1.0,
    );

    let nextNo = origNo;
    if ((isGeneric && collidesExistingDisjoint) || collidesInBatch) {
      nextNo = nextFreeKey(!isGeneric && !preferBolum);
      norm = normalizeSectionKey(nextNo);
    }

    const updatedClaims = claimedInBatch.get(norm) ?? [];
    updatedClaims.push({ s: row.start_m, e: row.end_m });
    claimedInBatch.set(norm, updatedClaims);
    usedKeys.add(norm);

    const nextDesc =
      row.description && nextNo !== origNo && row.description.includes(origNo)
        ? row.description.replace(origNo, nextNo)
        : row.description;

    return {
      ...row,
      section_no: nextNo,
      description: nextDesc,
    };
  });

  // Ardışık KP sürekliliğini birleştirilmiş sıraya göre yeniden hesapla
  const continuityIssues: string[] = [];
  for (let idx = 0; idx < drafts.length; idx += 1) {
    const cur = drafts[idx];
    if (idx === 0) {
      const prevExisting = existingOrderedEnds
        .filter((ex) => ex.endM <= cur.start_m + 1.0)
        .sort((a, b) => b.endM - a.endM)[0];
      if (prevExisting) {
        const delta = Math.round(cur.start_m - prevExisting.endM);
        cur.prev_end_kp = prevExisting.endKp;
        cur.continuity_ok = Math.abs(delta) <= 0.5;
        cur.continuity_note = cur.continuity_ok
          ? `Projedeki önceki (${prevExisting.label}) bitiş KP (${prevExisting.endKp}) ile eşleşiyor.`
          : `Projedeki ${prevExisting.label} bitişi (${prevExisting.endKp}) ile +${delta} m fark`;
      } else {
        cur.prev_end_kp = null;
        cur.continuity_ok = true;
        cur.continuity_note = "Başlangıç kesiti";
      }
    } else {
      const prev = drafts[idx - 1];
      const delta = Math.round(cur.start_m - prev.end_m);
      cur.prev_end_kp = prev.end_kp;
      cur.continuity_ok = Math.abs(delta) <= 0.5;
      if (cur.continuity_ok) {
        cur.continuity_note = `Önceki kesit (${prev.section_no}) bitiş KP (${prev.end_kp}) ile tam eşleşiyor.`;
      } else {
        const kind = delta > 0 ? `+${Math.abs(delta)} m boşluk` : `${Math.abs(delta)} m bindirme`;
        cur.continuity_note = `${prev.section_no} bitiş KP (${prev.end_kp}) ile ${cur.section_no} başlangıç KP (${cur.start_kp}) eşleşmiyor (${kind}).`;
        continuityIssues.push(cur.continuity_note);
      }
    }
  }

  // Tüm kot noktalarını station_m sırasıyla birleştir
  const rawPts = scans
    .flatMap((s) => s.profile_points ?? [])
    .filter((p) => Number.isFinite(p.station_m) && Number.isFinite(p.elevation_m))
    .sort((a, b) => a.station_m - b.station_m);
  const mergedPoints: Array<{ kp: string; station_m: number; elevation_m: number }> = [];
  for (const pt of rawPts) {
    const last = mergedPoints[mergedPoints.length - 1];
    if (!last || Math.abs(pt.station_m - last.station_m) > 0.5) {
      mergedPoints.push({
        kp: pt.kp || formatKp(pt.station_m),
        station_m: pt.station_m,
        elevation_m: pt.elevation_m,
      });
    } else {
      mergedPoints[mergedPoints.length - 1] = {
        kp: pt.kp || formatKp(pt.station_m),
        station_m: pt.station_m,
        elevation_m: pt.elevation_m,
      };
    }
  }

  const pipeMeta = {
    outside_diameter_mm: scans.map((s) => s.pipe_meta.outside_diameter_mm).find((v) => v != null) ?? null,
    wall_thickness_mm: scans.map((s) => s.pipe_meta.wall_thickness_mm).find((v) => v != null) ?? null,
    design_pressure_bar: scans.map((s) => s.pipe_meta.design_pressure_bar).find((v) => v != null) ?? null,
    material_grade: scans.map((s) => s.pipe_meta.material_grade).find((v) => Boolean(v)) ?? "",
    smys_mpa: scans.map((s) => s.pipe_meta.smys_mpa).find((v) => v != null) ?? null,
  };

  const strategies = new Set(scans.map((s) => s.strategy));
  const strategy: PlanProfileScanResponse["strategy"] =
    strategies.size === 1
      ? scans[0].strategy
      : strategies.has("cad_profile")
        ? "cad_profile"
        : "explicit";

  const minM = drafts.length ? Math.min(...drafts.map((d) => d.start_m)) : 0;
  const maxM = drafts.length ? Math.max(...drafts.map((d) => d.end_m)) : 0;
  const sumLen = drafts.reduce((acc, d) => acc + (Number(d.length_m) || 0), 0);

  const similarMap = new Map<string, SimilarProjectCandidate>();
  for (const scan of scans) {
    for (const cand of scan.similar_projects ?? []) {
      const prev = similarMap.get(cand.id);
      if (!prev || cand.similarity > prev.similarity) {
        similarMap.set(cand.id, cand);
      }
    }
  }

  const warnings = Array.from(new Set(scans.flatMap((s) => s.warnings ?? [])));
  const methods = Array.from(new Set(scans.map((s) => s.extraction_method).filter(Boolean)));

  const detectedProjectName = pickBestDetectedProjectName(
    scans.map((s) => s.detected_project_name),
  );

  return {
    mergedScan: {
      file_name:
        scans.length === 1
          ? scans[0].file_name
          : `${scans.length} pafta (${scans.map((s) => s.file_name).join(", ")})`,
      page_count: scans.reduce((acc, s) => acc + (s.page_count || 0), 0),
      extraction_method: methods.join(" + ") || scans[0].extraction_method,
      strategy,
      station_count: scans.reduce((acc, s) => acc + (s.station_count || 0), 0),
      elevation_point_count:
        mergedPoints.length || scans.reduce((acc, s) => acc + (s.elevation_point_count || 0), 0),
      min_kp: drafts.length ? formatKp(minM) : scans[0].min_kp,
      max_kp: drafts.length ? formatKp(maxM) : scans[0].max_kp,
      total_length_m: drafts.length ? Math.round(sumLen * 100) / 100 : scans[0].total_length_m,
      pipe_meta: pipeMeta,
      profile_points: mergedPoints,
      draft_sections: drafts,
      continuity_ok: continuityIssues.length === 0,
      continuity_issues: continuityIssues,
      warnings,
      detected_project_name: detectedProjectName,
      similar_projects: Array.from(similarMap.values()).sort((a, b) => b.similarity - a.similarity),
    },
    drafts,
  };
}

function foldTurkishAscii(text: string): string {
  return text
    .replace(/[İIı]/g, "i")
    .replace(/[Çç]/g, "c")
    .replace(/[Ğğ]/g, "g")
    .replace(/[Öö]/g, "o")
    .replace(/[Şş]/g, "s")
    .replace(/[Üü]/g, "u")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function pickBestDetectedProjectName(
  names: Array<string | null | undefined>,
): string | null {
  const cleaned = names.map((v) => v?.trim()).filter((v): v is string => Boolean(v));
  if (cleaned.length === 0) return null;

  const groups = new Map<string, string[]>();
  for (const name of cleaned) {
    const key = foldTurkishAscii(name) || name.toLowerCase();
    const arr = groups.get(key) ?? [];
    arr.push(name);
    groups.set(key, arr);
  }

  let bestGroup: string[] = [];
  for (const arr of groups.values()) {
    if (arr.length > bestGroup.length) {
      bestGroup = arr;
    }
  }
  const turkishCount = (s: string) => (s.match(/[ÇĞİÖŞÜçğıöşü]/g) ?? []).length;
  return bestGroup.sort(
    (a, b) => turkishCount(b) - turkishCount(a) || b.length - a.length,
  )[0];
}
