import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { twMerge } from "tailwind-merge";
import type { SceneData } from "../../lib/scene";
import SceneCanvas from "./SceneCanvas";
import { SceneLabels } from "./SceneHtml";
import SceneFallback from "./SceneFallback";
import {
  PresetToolbar,
  SceneDataTable,
  SceneLegend,
  SelectionCard,
} from "./SceneOverlay";
import type { PigTelemetry } from "./PigAndFlow";
import {
  buildSceneLayout,
  focusEquipmentFor,
  formatDistance,
  numberFormat0,
  numberFormat1,
  pigStartDistance,
  resolveSceneData,
  type CameraPreset,
  type ColorMode,
  type SceneViewMode,
  type VerticalScaleMode,
} from "./sceneModel";
import type { CameraRequest } from "./SceneCamera";
import {
  detectWebGL,
  useCompactViewport,
  useDocumentVisible,
  useReducedMotion,
} from "./useScenePreferences";

export type { PigTelemetry };

export interface ExternalPigControl {
  playing?: boolean;
  rate?: number;
  direction?: 1 | -1;
  seekDistance?: number | null;
  seekNonce?: number;
}

export interface PipelineSceneProps {
  data: SceneData;
  className?: string;
  heightClassName?: string;
  mode?: SceneViewMode;
  defaultTranslucent?: boolean;
  hideDataTable?: boolean;
  onOpenSession?: (sessionId: string) => void;
  onSelectSection?: (sessionId: string) => void;
  onPigTelemetry?: (telemetry: PigTelemetry) => void;
  externalPigControl?: ExternalPigControl;
  onPigPlayToggle?: () => void;
  onPigRateCycle?: () => void;
}

const PIG_RATES = [1, 4, 16];

/**
 * Birleşik 3D saha görünümü: arazi, basınç/kullanım renkli segmentler,
 * ekipmanlar, pig simülasyonu, akış izleri, kesit düzlemi, kamera presetleri
 * ve erişilebilir segment/ekipman veri tablosu tek bileşende.
 */
export default function PipelineScene({
  data,
  className,
  heightClassName = "h-[620px] sm:h-[600px]",
  mode = "detail",
  defaultTranslucent = false,
  hideDataTable = false,
  onOpenSession,
  onSelectSection,
  onPigTelemetry,
  externalPigControl,
  onPigPlayToggle,
  onPigRateCycle,
}: PipelineSceneProps) {
  const resolved = useMemo(() => resolveSceneData(data), [data]);
  const scene = resolved.data;
  const [verticalScale, setVerticalScale] = useState<VerticalScaleMode>("auto");
  const layout = useMemo(
    () => buildSceneLayout(scene, { mode, verticalScaleMode: verticalScale }),
    [scene, mode, verticalScale],
  );

  const [webglAvailable] = useState(detectWebGL);
  const reducedMotion = useReducedMotion();
  const compact = useCompactViewport();
  const documentVisible = useDocumentVisible();

  const [preset, setPreset] = useState<CameraPreset>("overview");
  const [cameraRequest, setCameraRequest] = useState<CameraRequest>({
    preset: "overview",
    nonce: 0,
  });
  const [cutaway, setCutaway] = useState(false);
  const [translucentPipe, setTranslucentPipe] = useState(
    () => mode === "detail" && defaultTranslucent,
  );
  const [showFlow, setShowFlow] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showLandmarks, setShowLandmarks] = useState(() => mode === "detail");
  const [colorMode, setColorMode] = useState<ColorMode>("utilization");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pigPlaying, setPigPlaying] = useState(false);
  const [pigRate, setPigRate] = useState(1);
  const [tableOpen, setTableOpen] = useState(false);

  const effectivePigPlaying = externalPigControl?.playing ?? pigPlaying;
  const effectivePigRate = externalPigControl?.rate ?? pigRate;
  const effectivePigDirection = externalPigControl?.direction ?? 1;
  const effectiveSeekDistance = externalPigControl?.seekDistance ?? null;
  const effectiveSeekNonce = externalPigControl?.seekNonce ?? 0;

  const rawTableId = useId();
  const tableId = `scene-table-${rawTableId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const tableWrapRef = useRef<HTMLDivElement>(null);

  const clipPlane = useMemo(
    () => new THREE.Plane(new THREE.Vector3(0, 0, -1), 0),
    [],
  );
  const clipPlanes = useMemo(
    () => (cutaway ? [clipPlane] : []),
    [cutaway, clipPlane],
  );

  const pigStart = useMemo(
    () => pigStartDistance(scene, layout.totalLengthM),
    [scene, layout.totalLengthM],
  );
  const pigPosition = useRef(new THREE.Vector3());

  const focusEquipment = useMemo(
    () => focusEquipmentFor(layout.equipment, selectedId),
    [layout.equipment, selectedId],
  );

  const selectedSegment = useMemo(
    () => scene.segments.find((segment) => segment.id === selectedId) ?? null,
    [scene.segments, selectedId],
  );
  const selectedEquipment = useMemo(
    () => scene.equipment.find((item) => item.id === selectedId) ?? null,
    [scene.equipment, selectedId],
  );

  useEffect(() => {
    if (scene.pig) {
      layout.sample(pigStart, pigPosition.current);
    } else {
      pigPosition.current.copy(layout.center);
    }
  }, [layout, pigStart, scene.pig]);

  useEffect(() => {
    if (reducedMotion) setPigPlaying(false);
  }, [reducedMotion]);

  useEffect(() => {
    if (compact) setShowLabels(false);
  }, [compact]);

  const requestPreset = useCallback((next: CameraPreset) => {
    setPreset(next);
    setCameraRequest((previous) => ({ preset: next, nonce: previous.nonce + 1 }));
    if (next === "pig" && !translucentPipe) {
      // Make pig visible inside the pipe if pipe is currently opaque.
      setCutaway(true);
    }
  }, [translucentPipe]);

  const resetScene = useCallback(() => {
    setCutaway(false);
    setTranslucentPipe(mode === "detail" && defaultTranslucent);
    setVerticalScale("auto");
    setShowFlow(true);
    setShowLabels(true);
    setShowLandmarks(mode === "detail");
    setColorMode("utilization");
    setPigPlaying(false);
    setPigRate(1);
    setSelectedId(null);
    setPreset("overview");
    setCameraRequest((previous) => ({ preset: "overview", nonce: previous.nonce + 1 }));
  }, [mode, defaultTranslucent]);

  const cyclePigRate = useCallback(() => {
    setPigRate((current) => {
      const index = PIG_RATES.indexOf(current);
      return PIG_RATES[(index + 1) % PIG_RATES.length];
    });
  }, []);

  const openTable = useCallback(() => {
    setTableOpen(true);
    window.setTimeout(() => {
      tableWrapRef.current?.scrollIntoView({
        block: "start",
        behavior: reducedMotion ? "auto" : "smooth",
      });
    }, 0);
  }, [reducedMotion]);

  const isOverview = mode === "overview";
  const hasLandmarks = Boolean(scene.landmarks && scene.landmarks.length > 0);
  const sectionCount = useMemo(() => {
    const keys = new Set(
      scene.segments.map((seg) => seg.session_id || seg.section_no || seg.id),
    );
    return keys.size;
  }, [scene.segments]);
  const visibleWarnings = useMemo(() => {
    const raw = scene.warnings ?? [];
    if (!isOverview) return raw;
    return raw.filter((w) => !w.includes("ekipman") && !w.includes("equipment"));
  }, [scene.warnings, isOverview]);

  const fallback = (
    <SceneFallback scene={scene} message="3D bu cihazda kapalı" />
  );

  return (
    <section
      aria-label="Boru hattı 3D saha görünümü"
      className={twMerge(
        "relative isolate overflow-hidden rounded-2xl border border-line bg-ink-950 text-mist-100 shadow-[0_18px_50px_-30px_rgba(0,0,0,0.9)]",
        className,
      )}
    >
      <div className={twMerge("relative w-full", heightClassName)}>
        <SceneLabels>
          {webglAvailable ? (
            <SceneCanvas
              scene={scene}
              layout={layout}
              mode={mode}
              translucentPipe={translucentPipe}
              showLandmarks={showLandmarks}
              clipPlane={clipPlane}
              clipPlanes={clipPlanes}
              colorMode={colorMode}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onSelectSection={onSelectSection}
              showLabels={showLabels}
              showFlow={showFlow}
              cutaway={cutaway}
              cameraRequest={cameraRequest}
              focusEquipment={focusEquipment}
              pigPlaying={effectivePigPlaying}
              pigRate={effectivePigRate}
              pigDirection={effectivePigDirection}
              pigSeekDistance={effectiveSeekDistance}
              pigSeekNonce={effectiveSeekNonce}
              onPigProgress={onPigTelemetry}
              pigStart={pigStart}
              pigPositionRef={pigPosition}
              reducedMotion={reducedMotion}
              compact={compact}
              visible={documentVisible}
              fallback={fallback}
            />
          ) : (
            fallback
          )}
        </SceneLabels>

        <div className="pointer-events-none absolute inset-0 z-30 flex flex-col justify-between gap-2 p-2 sm:p-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
            {!isOverview && hideDataTable ? (
              <div className="pointer-events-auto inline-flex flex-wrap items-center gap-1.5 rounded-xl border border-line/70 bg-ink-950/85 px-2.5 py-1.5 shadow-lg">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan" />
                <span
                  className={
                    scene.is_survey_profile
                      ? "rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9.5px] font-medium text-emerald-300"
                      : "rounded bg-amber/15 px-1.5 py-0.5 text-[9.5px] font-medium text-amber"
                  }
                >
                  {scene.is_survey_profile ? "Gerçek Topoğrafya" : "Yaklaşık Kot"}
                </span>
                <span className="numeric text-[10px] text-mist-300">
                  Kot Δ{numberFormat0.format(layout.elevationRangeM)} m · Dikey ×
                  {numberFormat1.format(layout.verticalExaggeration)}
                </span>
              </div>
            ) : (
              <div className="pointer-events-auto w-full rounded-xl border border-line/70 bg-ink-950/85 px-3 py-2 shadow-lg sm:max-w-[320px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan" />
                  <p className="text-[11px] font-semibold text-mist-100">
                    {isOverview ? "3D Genel Hat Görünümü" : "3D Kesit Detay Görünümü"}
                  </p>
                  {!resolved.isDemo ? (
                    <>
                      <span
                        className={
                          scene.is_survey_profile
                            ? "rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300"
                            : "rounded bg-amber/15 px-1.5 py-0.5 text-[9px] font-medium text-amber"
                        }
                      >
                        {scene.is_survey_profile ? "Gerçek Topoğrafya" : "Yaklaşık Kot"}
                      </span>
                      {!isOverview ? (
                        <span
                          className={
                            scene.is_custom_equipment
                              ? "rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300"
                              : "rounded bg-amber/15 px-1.5 py-0.5 text-[9px] font-medium text-amber"
                          }
                        >
                          {scene.is_custom_equipment ? "Gerçek Ekipman" : "Varsayılan Ekipman"}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                </div>
                <p className="numeric mt-0.5 text-[10px] text-mist-500">
                  {isOverview
                    ? `${numberFormat0.format(sectionCount)} kesit`
                    : `${numberFormat0.format(scene.segments.length)} kırılım`}{" "}
                  · {formatDistance(layout.totalLengthM)} · Kot Δ{numberFormat0.format(layout.elevationRangeM)} m · Dikey ×
                  {numberFormat1.format(layout.verticalExaggeration)}
                  {!isOverview ? ` · ${scene.equipment.length} ekipman` : ""}
                  {hasLandmarks ? ` · ${scene.landmarks!.length} geçiş` : ""}
                </p>
                {visibleWarnings.length > 0 ? (
                  <p
                    className="mt-1.5 rounded border border-amber/40 bg-amber/10 px-1.5 py-1 text-[10px] leading-snug text-amber"
                    title={visibleWarnings.join(" · ")}
                  >
                    <span className="font-semibold">
                      {!scene.is_survey_profile
                        ? "Yaklaşık kot"
                        : "Bilgi / Süreklilik"}
                    </span>{" "}
                    · {visibleWarnings[0]}
                    {visibleWarnings.length > 1 ? ` (+${visibleWarnings.length - 1})` : ""}
                  </p>
                ) : null}
                {!hideDataTable ? (
                  <a
                    href={`#${tableId}`}
                    onClick={(event) => {
                      event.preventDefault();
                      openTable();
                    }}
                    className="mt-1 inline-block text-[10px] text-cyan/90 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan"
                  >
                    3D&apos;yi atla → veri tablosu
                  </a>
                ) : null}
              </div>
            )}

            <PresetToolbar
              mode={mode}
              preset={preset}
              onPreset={requestPreset}
              verticalScale={verticalScale}
              onVerticalScale={setVerticalScale}
              translucentPipe={translucentPipe}
              onTranslucentPipe={() => setTranslucentPipe((value) => !value)}
              cutaway={cutaway}
              onCutaway={() => setCutaway((value) => !value)}
              flow={showFlow}
              onFlow={() => setShowFlow((value) => !value)}
              labels={showLabels}
              onLabels={() => setShowLabels((value) => !value)}
              hasLandmarks={hasLandmarks}
              landmarksVisible={showLandmarks}
              onLandmarks={() => setShowLandmarks((value) => !value)}
              hasPig={Boolean(scene.pig)}
              pigPlaying={effectivePigPlaying}
              onPigPlay={() => {
                if (onPigPlayToggle) {
                  onPigPlayToggle();
                } else {
                  setPigPlaying((value) => !value);
                }
                if (!translucentPipe) setCutaway(true);
              }}
              pigRate={effectivePigRate}
              onPigRate={onPigRateCycle ?? cyclePigRate}
              onReset={resetScene}
              reducedMotion={reducedMotion}
            />
          </div>

          <div className="flex flex-wrap items-end justify-between gap-2">
            <SceneLegend mode={colorMode} onModeChange={setColorMode} ranges={layout.ranges} />
            <p className="hidden rounded-full border border-line/60 bg-ink-950/70 px-2.5 py-1 text-[9px] text-mist-500 md:block">
              {isOverview
                ? "Kesite tıkla: 3D detay & pig akışı · Sürükle: döndür · Tekerlek: zoom"
                : "Sürükle: döndür · Tekerlek: zoom · Sağ tık: kaydır · Segmente tıkla: seç"}
            </p>
            {!isOverview ? (
              <SelectionCard
                segment={selectedSegment}
                equipment={selectedEquipment}
                onClose={() => setSelectedId(null)}
                onOpenSession={onOpenSession}
              />
            ) : null}
          </div>
        </div>
      </div>

      {!hideDataTable ? (
        <div ref={tableWrapRef}>
          <details
            open={tableOpen}
            onToggle={(event) => setTableOpen(event.currentTarget.open)}
            className="group bg-ink-950"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 border-t border-line/70 px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-mist-500 transition-colors hover:text-mist-200 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-cyan">
              <span>Veri tablosu · segmentler ve ekipman ({scene.segments.length} kesit · {scene.equipment.length} ekipman)</span>
              <span aria-hidden className="text-mist-500 transition-transform group-open:rotate-180">
                ▾
              </span>
            </summary>
            <SceneDataTable
              id={tableId}
              scene={scene}
              mode={colorMode}
              ranges={layout.ranges}
            />
          </details>
        </div>
      ) : null}
    </section>
  );
}
