import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  X,
} from "lucide-react";
import { api } from "../../lib/api";
import { num } from "../../lib/format";
import { formatKp, parseKpMeters } from "../../lib/kp";
import { buildSectionDetailSceneData, interpolateElevation, resolveProfileCurve, sectionsFromInputs } from "../../lib/mock";
import { normalizeInputs } from "../../lib/normalize";
import type { ProjectSceneSectionItem } from "../../lib/types";
import PipelineScene, { type PigTelemetry } from "./PipelineScene";

export interface SectionDetailModalProps {
  sessionId: string | null;
  sections?: ProjectSceneSectionItem[];
  onClose: () => void;
  onSelectSection?: (sessionId: string) => void;
  onOpenWorkspace?: (sessionId: string) => void;
}

const RATES = [1, 4, 16];

export default function SectionDetailModal({
  sessionId,
  sections = [],
  onClose,
  onSelectSection,
  onOpenWorkspace,
}: SectionDetailModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const open = Boolean(sessionId);
  const [fullscreen, setFullscreen] = useState(false);
  const [pigPlaying, setPigPlaying] = useState(false);
  const [pigRate, setPigRate] = useState(1);
  const [pigDirection, setPigDirection] = useState<1 | -1>(1);
  const [seekState, setSeekState] = useState<{ distance: number | null; nonce: number }>({
    distance: null,
    nonce: 0,
  });
  const [telemetry, setTelemetry] = useState<PigTelemetry | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["session-detail-scene", sessionId],
    queryFn: ({ signal }) => api.session(sessionId!, signal),
    enabled: Boolean(sessionId),
    staleTime: 15_000,
  });

  // Reset playback state when switching section
  useEffect(() => {
    setPigPlaying(false);
    setPigRate(1);
    setPigDirection(1);
    setSeekState({ distance: 0, nonce: 1 });
    setTelemetry(null);
  }, [sessionId]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const handleClose = () => {
      dialog.returnValue = "";
      onCloseRef.current();
    };
    dialog.addEventListener("close", handleClose);

    let cleanupFallback: (() => void) | undefined;
    if (
      typeof HTMLDialogElement !== "undefined" &&
      !("closedBy" in HTMLDialogElement.prototype)
    ) {
      let pressedOutside = false;
      const outside = (e: PointerEvent) => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      const onPointerDown = (e: PointerEvent) => {
        pressedOutside = e.target === dialog && outside(e);
      };
      const onPointerUp = (e: PointerEvent) => {
        if (pressedOutside && e.target === dialog && outside(e) && dialog.open) {
          dialog.close();
        }
        pressedOutside = false;
      };
      dialog.addEventListener("pointerdown", onPointerDown);
      dialog.addEventListener("pointerup", onPointerUp);
      cleanupFallback = () => {
        dialog.removeEventListener("pointerdown", onPointerDown);
        dialog.removeEventListener("pointerup", onPointerUp);
      };
    }
    return () => {
      dialog.removeEventListener("close", handleClose);
      cleanupFallback?.();
    };
  }, [open]);

  // Trigger resize event when toggling fullscreen so WebGL canvas fits immediately
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
    });
    return () => cancelAnimationFrame(raf);
  }, [fullscreen, open]);

  const parsed = useMemo(() => {
    const sess = sessionQuery.data;
    if (!sess) return null;
    const inputs = normalizeInputs(sess.inputs);
    const scene = buildSectionDetailSceneData(inputs);
    const pipeSections = sectionsFromInputs(inputs);
    const totalLengthM = pipeSections.reduce((sum, s) => sum + s.length_m, 0);
    const { points: curve, hasSurveyProfile } = resolveProfileCurve(inputs, totalLengthM);
    const elevs = curve.map((p) => p.y);
    const minEl = elevs.length ? Math.min(...elevs) : 0;
    const maxEl = elevs.length ? Math.max(...elevs) : 0;
    const startEl = interpolateElevation(curve, 0);
    const endEl = interpolateElevation(curve, totalLengthM);
    const firstPipe = pipeSections[0];
    const volumeM3 = pipeSections.reduce(
      (sum, s) =>
        sum +
        Math.PI * ((s.outside_diameter_mm / 2 - s.wall_thickness_mm) / 1000) ** 2 * s.length_m,
      0,
    );
    const startKpM = parseKpMeters(inputs.section_meta.start_kp);
    const od = firstPipe?.outside_diameter_mm ?? inputs.geometry.outside_diameter_mm;
    const wt = firstPipe?.wall_thickness_mm ?? inputs.geometry.wall_thickness_mm;
    const smys = firstPipe?.smys_mpa ?? inputs.section_profile.smys_mpa;
    const p100 = od && wt && smys ? (20 * smys * wt) / od : null;

    return {
      session: sess,
      inputs,
      scene,
      totalLengthM,
      hasSurveyProfile,
      minEl,
      maxEl,
      startEl,
      endEl,
      deltaH: maxEl - minEl,
      od,
      wt,
      smys,
      p100,
      volumeM3,
      startKpM,
    };
  }, [sessionQuery.data]);

  const currentIdx = sections.findIndex((item) => item.session_id === sessionId);
  const prevSection = currentIdx > 0 ? sections[currentIdx - 1] : null;
  const nextSection =
    currentIdx >= 0 && currentIdx < sections.length - 1 ? sections[currentIdx + 1] : null;

  const summaryItem = currentIdx >= 0 ? sections[currentIdx] : null;
  const headerTitle =
    parsed?.inputs.section_meta.section_no ||
    summaryItem?.section_no ||
    sessionQuery.data?.name ||
    "Kesit 3D Detay";
  const headerKp =
    parsed?.inputs.section_meta.start_kp && parsed?.inputs.section_meta.end_kp
      ? `KP ${parsed.inputs.section_meta.start_kp} – ${parsed.inputs.section_meta.end_kp}`
      : summaryItem?.start_kp && summaryItem?.end_kp
        ? `KP ${summaryItem.start_kp} – ${summaryItem.end_kp}`
        : "";

  const liveDistanceM = telemetry?.distanceM ?? 0;
  const liveKpLabel =
    parsed?.startKpM !== null && parsed?.startKpM !== undefined
      ? `KP ${formatKp(parsed.startKpM + liveDistanceM)}`
      : `${num(liveDistanceM, 0)} m`;

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={headingId}
      {...({ closedby: "any" } as Record<string, unknown>)}
      className={`modal-dialog modal-dialog-scene ${fullscreen ? "modal-dialog-scene-fullscreen" : ""}`}
    >
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id={headingId} className="truncate text-[16px] font-bold text-[var(--text)]">
                {headerTitle} · 3D Detay &amp; Pig Akışı
              </h2>
              {headerKp ? (
                <span className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] text-cyan">
                  {headerKp}
                </span>
              ) : null}
            </div>
            {parsed?.inputs.section_meta.description ? (
              <p className="truncate text-[11.5px] text-[var(--text-muted)]">
                {parsed.inputs.section_meta.description}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {sections.length > 1 && onSelectSection ? (
            <div className="mr-1 inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-0.5">
              <button
                type="button"
                disabled={!prevSection}
                onClick={() => prevSection && onSelectSection(prevSection.session_id)}
                className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium text-[var(--text-soft)] hover:bg-[var(--surface)] disabled:cursor-not-allowed disabled:opacity-40"
                title={prevSection ? `Önceki: ${prevSection.section_no}` : "İlk kesit"}
              >
                <ChevronLeft size={13} aria-hidden />
                Önceki
              </button>
              <span className="px-1 font-mono text-[10.5px] text-[var(--text-faint)]">
                {currentIdx + 1}/{sections.length}
              </span>
              <button
                type="button"
                disabled={!nextSection}
                onClick={() => nextSection && onSelectSection(nextSection.session_id)}
                className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium text-[var(--text-soft)] hover:bg-[var(--surface)] disabled:cursor-not-allowed disabled:opacity-40"
                title={nextSection ? `Sonraki: ${nextSection.section_no}` : "Son kesit"}
              >
                Sonraki
                <ChevronRight size={13} aria-hidden />
              </button>
            </div>
          ) : null}

          <button
            type="button"
            onClick={() => setFullscreen((prev) => !prev)}
            aria-label={fullscreen ? "Tam ekrandan çık" : "Tam ekran yap"}
            aria-pressed={fullscreen}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 text-[11.5px] font-semibold text-[var(--text-soft)] transition-colors hover:border-cyan/50 hover:text-[var(--text)]"
          >
            {fullscreen ? <Minimize2 size={13} aria-hidden /> : <Maximize2 size={13} aria-hidden />}
            {fullscreen ? "Küçült" : "Tam ekran"}
          </button>

          <button
            type="button"
            onClick={onClose}
            aria-label="Kapat"
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-soft)] hover:text-[var(--text)]"
          >
            <X size={15} aria-hidden />
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1fr_340px]">
        {/* Sol / Ana 3D Kesit Sahnesi */}
        <div className="relative min-h-[360px] bg-ink-950 p-2 sm:p-3">
          {sessionQuery.isLoading ? (
            <div className="flex h-full min-h-[360px] items-center justify-center text-xs text-mist-400">
              Kesit 3D profili ve ekipmanları yükleniyor...
            </div>
          ) : sessionQuery.isError || !parsed ? (
            <div className="flex h-full min-h-[360px] items-center justify-center text-xs text-rose-400">
              Kesit verisi alınamadı.
            </div>
          ) : (
            <PipelineScene
              data={parsed.scene}
              mode="detail"
              defaultTranslucent
              hideDataTable
              className="h-full"
              heightClassName="h-full min-h-[360px]"
              externalPigControl={{
                playing: pigPlaying,
                rate: pigRate,
                direction: pigDirection,
                seekDistance: seekState.distance,
                seekNonce: seekState.nonce,
              }}
              onPigPlayToggle={() => setPigPlaying((prev) => !prev)}
              onPigRateCycle={() =>
                setPigRate((curr) => RATES[(RATES.indexOf(curr) + 1) % RATES.length])
              }
              onPigTelemetry={setTelemetry}
              onOpenSession={onOpenWorkspace}
            />
          )}
        </div>

        {/* Sağ Panel: Mühendislik Bilgi Kartı */}
        <aside className="flex min-h-0 flex-col justify-between overflow-y-auto border-t border-[var(--border)] bg-[var(--surface)] p-4 lg:border-l lg:border-t-0">
          {parsed ? (
            <div className="space-y-4">
              {/* Pig Akış Kontrolü ve Canlı Telemetri */}
              <section className="rounded-xl border border-cyan/30 bg-[var(--surface-2)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-cyan">
                    Pig Akış Simülasyonu
                  </span>
                  <span className="rounded bg-amber/15 px-1.5 py-0.5 font-mono text-[10px] text-amber">
                    {parsed.inputs.modes.pig_mode || "Temizlik pigi"}
                  </span>
                </div>

                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setPigPlaying((prev) => !prev)}
                    className={`inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg border px-2.5 text-[12px] font-semibold transition-colors ${
                      pigPlaying
                        ? "border-cyan/70 bg-cyan/20 text-cyan"
                        : "border-[var(--border)] bg-[var(--surface)] text-[var(--text)] hover:border-cyan/50"
                    }`}
                  >
                    {pigPlaying ? <Pause size={13} aria-hidden /> : <Play size={13} aria-hidden />}
                    {pigPlaying ? "Duraklat" : "Oynat"}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setPigRate((curr) => RATES[(RATES.indexOf(curr) + 1) % RATES.length])
                    }
                    className="inline-flex h-8 items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 font-mono text-[11.5px] font-semibold text-[var(--text-soft)] hover:border-cyan/50"
                    title="Akış hızı çarpanı"
                  >
                    {pigRate}×
                  </button>
                  <button
                    type="button"
                    onClick={() => setPigDirection((d) => (d === 1 ? -1 : 1))}
                    className="inline-flex h-8 items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-[11px] font-medium text-[var(--text-soft)] hover:border-cyan/50"
                    title="Akış yönünü ters çevir"
                  >
                    <ArrowLeftRight size={12} aria-hidden />
                    {pigDirection === 1 ? "İleri" : "Geri"}
                  </button>
                </div>

                <div className="mt-2.5">
                  <div className="mb-1 flex items-center justify-between text-[10.5px] text-[var(--text-muted)]">
                    <span>İstasyon konumu</span>
                    <span className="font-mono text-[var(--text)]">{liveKpLabel}</span>
                  </div>
                  <input
                    type="range"
                    aria-label="Pig hat içi konumu"
                    min={0}
                    max={Math.max(1, parsed.totalLengthM)}
                    step={Math.max(1, Math.round(parsed.totalLengthM / 200))}
                    value={Math.round(liveDistanceM)}
                    onChange={(event) => {
                      const dist = Number(event.target.value);
                      setSeekState((prev) => ({ distance: dist, nonce: prev.nonce + 1 }));
                    }}
                    className="w-full accent-cyan-400"
                  />
                </div>

                <dl className="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 text-[11px]">
                  <div>
                    <dt className="text-[10px] text-[var(--text-faint)]">Anlık Kot</dt>
                    <dd className="font-mono font-semibold text-[var(--text)]">
                      {telemetry ? `${num(telemetry.elevationM, 1)} m` : `${num(parsed.startEl, 1)} m`}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] text-[var(--text-faint)]">Yerel Eğim</dt>
                    <dd className="font-mono font-semibold text-[var(--text)]">
                      {telemetry ? `${telemetry.slopePct >= 0 ? "+" : ""}${num(telemetry.slopePct, 1)}%` : "0.0%"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] text-[var(--text-faint)]">İlerleme</dt>
                    <dd className="font-mono font-semibold text-[var(--text)]">
                      {num((telemetry?.progress ?? 0) * 100, 0)}% · {num(liveDistanceM, 0)} m
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] text-[var(--text-faint)]">Yerel Basınç</dt>
                    <dd className="font-mono font-semibold text-[var(--text)]">
                      {telemetry?.pressureBar !== null && telemetry?.pressureBar !== undefined
                        ? `${num(telemetry.pressureBar, 1)} bar`
                        : "—"}
                    </dd>
                  </div>
                </dl>
              </section>

              {/* Kesit Özeti */}
              <section className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <h3 className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Boru &amp; Geometri
                </h3>
                <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5 text-[11.5px]">
                  <dt className="text-[var(--text-muted)]">Hat Boyu</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {num(parsed.totalLengthM, 1)} m
                  </dd>
                  <dt className="text-[var(--text-muted)]">İç Hacim</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {num(parsed.volumeM3, 1)} m³
                  </dd>
                  <dt className="text-[var(--text-muted)]">Çap / Et Kal.</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {odLabel(parsed.od, parsed.wt)}
                  </dd>
                  <dt className="text-[var(--text-muted)]">Malzeme / SMYS</dt>
                  <dd className="truncate text-right font-mono text-[var(--text)]">
                    {parsed.smys ? `${num(parsed.smys, 0)} MPa` : "—"}
                  </dd>
                  <dt className="text-[var(--text-muted)]">%100 SMYS</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {parsed.p100 ? `${num(parsed.p100, 1)} bar` : "—"}
                  </dd>
                </dl>
              </section>

              {/* Kot Profili */}
              <section className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    Kot Profili
                  </h3>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[9.5px] font-semibold ${
                      parsed.hasSurveyProfile
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-amber/15 text-amber"
                    }`}
                  >
                    {parsed.hasSurveyProfile
                      ? `${parsed.inputs.profile_points.length} pafta noktası`
                      : "4 nokta yaklaşık"}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5 text-[11.5px]">
                  <dt className="text-[var(--text-muted)]">Başlangıç → Bitiş</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {num(parsed.startEl, 1)} → {num(parsed.endEl, 1)} m
                  </dd>
                  <dt className="text-[var(--text-muted)]">Min / Maks Kot</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {num(parsed.minEl, 1)} / {num(parsed.maxEl, 1)} m
                  </dd>
                  <dt className="text-[var(--text-muted)]">Toplam Kot Farkı</dt>
                  <dd className="text-right font-mono font-semibold text-cyan">
                    Δ {num(parsed.deltaH, 1)} m
                  </dd>
                  <dt className="text-[var(--text-muted)]">Dizayn / Test P</dt>
                  <dd className="text-right font-mono text-[var(--text)]">
                    {parsed.inputs.section_profile.design_pressure_bar
                      ? `${num(parsed.inputs.section_profile.design_pressure_bar, 1)} bar`
                      : "—"}{" "}
                    /{" "}
                    {parsed.inputs.field.monitored_pressure_bar
                      ? `${num(parsed.inputs.field.monitored_pressure_bar, 1)} bar`
                      : "—"}
                  </dd>
                </dl>
                {parsed.inputs.landmarks.length > 0 ? (
                  <div className="mt-2.5 border-t border-[var(--border)] pt-2">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
                      Saha Geçişleri ({parsed.inputs.landmarks.length})
                    </p>
                    <ul className="max-h-24 space-y-1 overflow-y-auto text-[10.5px] text-[var(--text-soft)]">
                      {parsed.inputs.landmarks.slice(0, 8).map((lm, i) => (
                        <li key={`${lm.label}-${i}`} className="flex items-center justify-between gap-2">
                          <span className="truncate">{lm.label}</span>
                          <span className="shrink-0 font-mono text-[10px] text-[var(--text-faint)]">
                            {lm.kp || `${num(lm.station_m, 0)} m`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </section>
            </div>
          ) : null}

          {sessionId && onOpenWorkspace ? (
            <div className="mt-4 border-t border-[var(--border)] pt-3">
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenWorkspace(sessionId);
                }}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-cyan/50 bg-cyan/15 px-3 py-2 text-[12.5px] font-semibold text-cyan transition-colors hover:bg-cyan/25"
              >
                <ExternalLink size={14} aria-hidden />
                Kesiti Çalışma Alanında Aç
              </button>
            </div>
          ) : null}
        </aside>
      </div>
    </dialog>,
    document.body,
  );
}

function odLabel(od: number | null, wt: number | null): string {
  if (!od) return "—";
  if (!wt) return `${num(od, 1)} mm`;
  return `${num(od, 1)} × ${num(wt, 2)} mm`;
}
