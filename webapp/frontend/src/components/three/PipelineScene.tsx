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
import {
  buildSceneLayout,
  focusEquipmentFor,
  formatDistance,
  numberFormat0,
  pigStartDistance,
  resolveSceneData,
  type CameraPreset,
  type ColorMode,
} from "./sceneModel";
import type { CameraRequest } from "./SceneCamera";
import {
  detectWebGL,
  useCompactViewport,
  useDocumentVisible,
  useReducedMotion,
} from "./useScenePreferences";

export interface PipelineSceneProps {
  data: SceneData;
  className?: string;
  onOpenSession?: (sessionId: string) => void;
}

const PIG_RATES = [1, 4, 16];

/**
 * Birleşik 3D saha görünümü: arazi, basınç/kullanım renkli segmentler,
 * ekipmanlar, pig simülasyonu, akış izleri, kesit düzlemi, kamera presetleri
 * ve erişilebilir segment/ekipman veri tablosu tek bileşende.
 */
export default function PipelineScene({ data, className, onOpenSession }: PipelineSceneProps) {
  const resolved = useMemo(() => resolveSceneData(data), [data]);
  const scene = resolved.data;
  const layout = useMemo(() => buildSceneLayout(scene), [scene]);

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
  const [showFlow, setShowFlow] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [colorMode, setColorMode] = useState<ColorMode>("utilization");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pigPlaying, setPigPlaying] = useState(false);
  const [pigRate, setPigRate] = useState(1);
  const [tableOpen, setTableOpen] = useState(false);

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
    if (next === "pig") {
      // The cutaway makes the pig visible inside the pipe.
      setCutaway(true);
    }
  }, []);

  const resetScene = useCallback(() => {
    setCutaway(false);
    setShowFlow(true);
    setShowLabels(true);
    setColorMode("utilization");
    setPigPlaying(false);
    setPigRate(1);
    setSelectedId(null);
    setPreset("overview");
    setCameraRequest((previous) => ({ preset: "overview", nonce: previous.nonce + 1 }));
  }, []);

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
      <div className="relative h-[620px] w-full sm:h-[600px]">
        <SceneLabels>
          {webglAvailable ? (
            <SceneCanvas
              scene={scene}
              layout={layout}
              clipPlane={clipPlane}
              clipPlanes={clipPlanes}
              colorMode={colorMode}
              selectedId={selectedId}
              onSelect={setSelectedId}
              showLabels={showLabels}
              showFlow={showFlow}
              cutaway={cutaway}
              cameraRequest={cameraRequest}
              focusEquipment={focusEquipment}
              pigPlaying={pigPlaying}
              pigRate={pigRate}
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
            <div className="pointer-events-auto w-full rounded-xl border border-line/70 bg-ink-950/85 px-3 py-2 shadow-lg sm:max-w-[300px]">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan" />
                <p className="text-[11px] font-semibold text-mist-100">3D saha görünümü</p>
                {!resolved.isDemo && scene.is_survey_profile ? (
                  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300">
                    Plan-Profil Gerçek Topoğrafya
                  </span>
                ) : null}
              </div>
              <p className="numeric mt-0.5 text-[10px] text-mist-500">
                {numberFormat0.format(scene.segments.length)} segment ·{" "}
                {formatDistance(layout.totalLengthM)} · {scene.equipment.length} ekipman
                {scene.landmarks && scene.landmarks.length > 0
                  ? ` · ${scene.landmarks.length} saha noktası`
                  : ""}
              </p>
              {scene.warnings && scene.warnings.length > 0 ? (
                <p
                  className="mt-1.5 rounded border border-amber/40 bg-amber/10 px-1.5 py-1 text-[10px] leading-snug text-amber"
                  title={scene.warnings.join(" · ")}
                >
                  <span className="font-semibold">
                    {scene.is_survey_profile ? "Süreklilik / Kontrol" : "Yaklaşık sahne"}
                  </span>{" "}
                  · {scene.warnings[0]}
                  {scene.warnings.length > 1 ? ` (+${scene.warnings.length - 1})` : ""}
                </p>
              ) : null}
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
            </div>

            <PresetToolbar
              preset={preset}
              onPreset={requestPreset}
              cutaway={cutaway}
              onCutaway={() => setCutaway((value) => !value)}
              flow={showFlow}
              onFlow={() => setShowFlow((value) => !value)}
              labels={showLabels}
              onLabels={() => setShowLabels((value) => !value)}
              hasPig={Boolean(scene.pig)}
              pigPlaying={pigPlaying}
              onPigPlay={() => {
                setPigPlaying((value) => !value);
                setCutaway(true);
              }}
              pigRate={pigRate}
              onPigRate={cyclePigRate}
              onReset={resetScene}
              reducedMotion={reducedMotion}
            />
          </div>

          <div className="flex flex-wrap items-end justify-between gap-2">
            <SceneLegend mode={colorMode} onModeChange={setColorMode} ranges={layout.ranges} />
            <p className="hidden rounded-full border border-line/60 bg-ink-950/70 px-2.5 py-1 text-[9px] text-mist-500 md:block">
              Sürükle: döndür · Tekerlek: zoom · Sağ tık: kaydır · Segmente tıkla: seç
            </p>
            <SelectionCard
              segment={selectedSegment}
              equipment={selectedEquipment}
              onClose={() => setSelectedId(null)}
              onOpenSession={onOpenSession}
            />
          </div>
        </div>
      </div>

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
    </section>
  );
}
