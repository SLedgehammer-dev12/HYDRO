import { useMemo } from "react";
import { AlertTriangle, CalendarDays, CheckCircle2, FolderOpen, GitCompareArrows, MapPin, Ruler, Tag } from "lucide-react";
import { SectionCard } from "./ui/Card";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { FieldGrid, TextField } from "./ui/Field";
import { useSessions } from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import {
  evaluateProjectKpContinuity,
  evaluateSegmentConsistency,
  formatKp,
  formatKpLocation,
  parseKpMeters,
} from "../lib/kp";
import { num } from "../lib/format";
import type { SessionListItem } from "../lib/types";

/**
 * Test Bölümü (Section) kimlik kartı: proje bağlantısı, bölüm numarası, başlangıç/bitiş KP
 * noktaları, ardışık bölümlerle canlı KP süreklilik kontrolü ve alt parçaların (Segment)
 * uzunluk/istasyon tutarlılık özeti.
 * Aynı bilgi oturum `inputs.section_meta` alanında saklanır.
 */
export function SectionIdentityCard() {
  const inputs = useAppStore((state) => state.inputs);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const sessionId = useAppStore((state) => state.sessionId);
  const sessionName = useAppStore((state) => state.sessionName);
  const sessionStatus = useAppStore((state) => state.sessionStatus);
  const revision = useAppStore((state) => state.revision);
  const projectName = useAppStore((state) => state.projectName);
  const projectCode = useAppStore((state) => state.projectCode);
  const projectId = useAppStore((state) => state.projectId);

  const meta = inputs.section_meta;
  const sessionsQuery = useSessions(projectId);

  const startM = parseKpMeters(meta.start_kp);
  const endM = parseKpMeters(meta.end_kp);
  const spanM = startM !== null && endM !== null ? endM - startM : null;

  /* Alt parça (Segment) kontrolü: Σ Segment Uzunluğu == Section (ΔKP) */
  const segmentSummary = useMemo(
    () =>
      evaluateSegmentConsistency({
        segments: inputs.segments,
        sectionMeta: inputs.section_meta,
        fallbackLengthM: inputs.geometry.length_m,
      }),
    [inputs.segments, inputs.section_meta, inputs.geometry.length_m],
  );
  const segmentTone: "pass" | "warning" | "fail" =
    segmentSummary.status === "pass" ? "pass" : segmentSummary.status === "warning" ? "warning" : "fail";

  /* Seçili projedeki kesit listesine aktif kesitin güncel KP değerlerini yansıtıp sürekliliği denetle */
  const currentId = sessionId ?? "__active_section__";
  const continuity = useMemo(() => {
    const list = [...(sessionsQuery.data ?? [])];
    const currentItem: SessionListItem = {
      id: currentId,
      project_id: projectId,
      name: meta.section_no ? `${meta.section_no} · ${meta.description || sessionName}` : sessionName,
      status: sessionStatus,
      revision,
      updated_at: new Date().toISOString(),
      section_meta: meta,
    };
    const idx = list.findIndex((item) => item.id === currentId);
    if (idx >= 0) {
      list[idx] = currentItem;
    } else {
      list.push(currentItem);
    }
    return evaluateProjectKpContinuity(list);
  }, [sessionsQuery.data, currentId, projectId, meta, sessionName, sessionStatus, revision]);

  const currentCheck = continuity.byId[currentId];

  function updateKp(patch: { start_kp?: string; end_kp?: string }) {
    const nextStart = patch.start_kp !== undefined ? patch.start_kp : meta.start_kp;
    const nextEnd = patch.end_kp !== undefined ? patch.end_kp : meta.end_kp;
    const autoLocation = formatKpLocation(nextStart, nextEnd, meta.location);
    patchInputs({
      section_meta: {
        ...patch,
        location: autoLocation,
      },
    });
  }

  function applyKpLengthToGeometry() {
    if (spanM === null || spanM <= 0) return;
    patchInputs({
      geometry: {
        length_m: Math.round(spanM * 100) / 100,
      },
    });
  }

  return (
    <SectionCard
      title="Test Bölümü (Section) kimliği ve KP aralığı"
      description="Proje bağlantısı, bölüm no, başlangıç/bitiş KP noktaları, ardışık bölüm sürekliliği ve segment özeti."
      icon={Tag}
      action={
        <div className="flex flex-wrap items-center gap-1.5">
          {currentCheck ? (
            <Badge tone={currentCheck.tone}>{currentCheck.badgeLabel}</Badge>
          ) : null}
          {segmentSummary.hasSegments ? (
            <Badge tone={segmentTone}>
              {segmentSummary.badgeLabel}
            </Badge>
          ) : null}
          <Button size="sm" variant="ghost" icon={<FolderOpen size={12} />} onClick={() => setTab("projects")}>
            Projeler & Kesitler
          </Button>
        </div>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={projectId ? "info" : "warning"}>
          {projectId ? projectCode || projectName || "Proje bağlı" : "Proje seçilmedi"}
        </Badge>
        {projectName ? <span className="text-[11px] text-[var(--text-muted)]">{projectName}</span> : null}
        <span className="chip">
          <MapPin size={10} />{" "}
          {meta.start_kp || meta.end_kp
            ? `KP ${meta.start_kp || "?"} → ${meta.end_kp || "?"}`
            : meta.location || "KP girilmedi"}
        </span>
        {spanM !== null && spanM > 0 ? (
          <span className="chip font-mono">ΔKP {num(spanM, 0)} m</span>
        ) : null}
        <span className="chip">
          <CalendarDays size={10} /> {meta.test_date || "tarih girilmedi"}
        </span>
      </div>

      <FieldGrid cols={4}>
        <TextField
          label="Test Bölümü (Section) no"
          value={meta.section_no}
          onChange={(value) => patchInputs({ section_meta: { section_no: value } })}
          placeholder="K-01"
          maxLength={40}
        />
        <TextField
          label="Başlangıç KP"
          value={meta.start_kp}
          onChange={(value) => updateKp({ start_kp: value })}
          placeholder="0+000"
          maxLength={40}
          help={
            startM !== null
              ? `${formatKp(startM)} (${num(startM, 0)} m)`
              : "Ör: 0+000 veya 12+000"
          }
        />
        <TextField
          label="Bitiş KP"
          value={meta.end_kp}
          onChange={(value) => updateKp({ end_kp: value })}
          placeholder="12+000"
          maxLength={40}
          help={
            endM !== null
              ? `${formatKp(endM)} (${num(endM, 0)} m)${spanM !== null && spanM > 0 ? ` · ΔKP ${num(spanM, 0)} m` : ""}`
              : "Ör: 12+000 veya 24+500"
          }
        />
        <TextField
          label="Test Bölümü açıklaması"
          value={meta.description}
          onChange={(value) => patchInputs({ section_meta: { description: value } })}
          placeholder="Bölüm 12–13 · Doğu Hattı"
          maxLength={200}
        />
      </FieldGrid>

      <FieldGrid cols={4} className="mt-3">
        <TextField
          label="Konum / KP etiketi"
          value={meta.location}
          onChange={(value) => patchInputs({ section_meta: { location: value } })}
          placeholder="KP 0+000 – 12+000"
          maxLength={120}
        />
        <TextField
          label="Test tarihi"
          type="date"
          value={meta.test_date}
          onChange={(value) => patchInputs({ section_meta: { test_date: value } })}
        />
        <TextField
          label="Test türü"
          value={meta.test_type}
          onChange={(value) => patchInputs({ section_meta: { test_type: value } })}
          placeholder="Hidrostatik test"
          maxLength={80}
        />
        <TextField
          label="Not"
          value={meta.notes}
          onChange={(value) => patchInputs({ section_meta: { notes: value } })}
          placeholder="Kısa saha notu"
          maxLength={240}
        />
      </FieldGrid>

      {currentCheck ? (
        <div
          className={`mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-[11.5px] ${
            currentCheck.tone === "fail"
              ? "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--text)]"
              : currentCheck.tone === "warning"
                ? "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--text)]"
                : currentCheck.tone === "pass"
                  ? "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--text)]"
                  : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)]"
          }`}
        >
          <div className="flex items-start gap-2">
            {currentCheck.tone === "pass" ? (
              <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
            ) : currentCheck.tone === "fail" || currentCheck.tone === "warning" ? (
              <AlertTriangle size={14} className="mt-0.5 shrink-0 tone-warning" aria-hidden />
            ) : (
              <GitCompareArrows size={14} className="mt-0.5 shrink-0 text-[var(--text-faint)]" aria-hidden />
            )}
            <div className="space-y-0.5">
              <p className="font-medium leading-snug">{currentCheck.detail}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10.5px] text-[var(--text-muted)]">
                {currentCheck.prevCheck ? (
                  <span>
                    Önceki ({currentCheck.prevCheck.prevLabel}) bitiş: KP {currentCheck.prevCheck.prevEndKp} ↔ Bu kesit başlangıç: KP {currentCheck.startKp || "—"}{" "}
                    {currentCheck.prevCheck.matched ? "✓ Eşleşiyor" : `✗ Fark: ${currentCheck.prevCheck.deltaM > 0 ? "+" : ""}${Math.round(currentCheck.prevCheck.deltaM)} m`}
                  </span>
                ) : null}
                {currentCheck.nextCheck ? (
                  <span>
                    Bu kesit bitiş: KP {currentCheck.endKp || "—"} ↔ Sonraki ({currentCheck.nextCheck.nextLabel}) başlangıç: KP {currentCheck.nextCheck.nextStartKp}{" "}
                    {currentCheck.nextCheck.matched ? "✓ Eşleşiyor" : `✗ Fark: ${currentCheck.nextCheck.deltaM > 0 ? "+" : ""}${Math.round(currentCheck.nextCheck.deltaM)} m`}
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          {spanM !== null && spanM > 0 && Math.abs((inputs.geometry.length_m ?? 0) - spanM) > 0.5 ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<Ruler size={12} />}
              onClick={applyKpLengthToGeometry}
            >
              ΔKP ({num(spanM, 0)} m) uzunluğunu geometriye uygula
            </Button>
          ) : null}
        </div>
      ) : null}

      {segmentSummary.hasSegments ? (
        <div
          className={`mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-[11.5px] ${
            segmentSummary.status === "fail"
              ? "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--text)]"
              : segmentSummary.status === "warning"
                ? "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--text)]"
                : "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--text)]"
          }`}
        >
          <div className="flex items-start gap-2">
            {segmentTone === "pass" ? (
              <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
            ) : (
              <AlertTriangle size={14} className={`mt-0.5 shrink-0 ${segmentTone === "fail" ? "tone-fail" : "tone-warning"}`} aria-hidden />
            )}
            <div className="space-y-0.5">
              <p className="font-medium leading-snug">
                Et Kalınlığı / Çap Alt Parçaları (Segmentler): {segmentSummary.headline}
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10.5px] text-[var(--text-muted)]">
                <span>
                  Σ Segment: {num(segmentSummary.totalSegmentLengthM, 1)} m
                  {segmentSummary.targetSectionLengthM !== null
                    ? ` ↔ Test Bölümü (Section): ${num(segmentSummary.targetSectionLengthM, 1)} m`
                    : ""}
                  {segmentSummary.deltaLengthM !== null
                    ? segmentSummary.deltaLengthM === 0
                      ? " ✓ Tam eşit"
                      : ` (${segmentSummary.deltaLengthM > 0 ? "+" : ""}${num(segmentSummary.deltaLengthM, 1)} m fark)`
                    : ""}
                </span>
                {segmentSummary.issues.length > 0 ? (
                  <span className="text-[var(--danger)]">
                    {segmentSummary.issues[0]}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <Badge tone={segmentTone}>
            {segmentSummary.badgeLabel}
          </Badge>
        </div>
      ) : null}
    </SectionCard>
  );
}
