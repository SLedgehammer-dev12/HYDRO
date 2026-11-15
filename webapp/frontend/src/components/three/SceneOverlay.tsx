import { Droplets, Pause, Play, RotateCcw, Scissors, Tag } from "lucide-react";
import type {
  SceneData,
  SceneEquipment,
  SceneSegment,
} from "../../lib/scene";
import {
  EQUIPMENT_LABEL,
  colorForSegment,
  formatDiameter,
  formatDistance,
  formatPressure,
  formatUtilization,
  legendGradient,
  numberFormat0,
  numberFormat1,
  percentFormat,
  statusMeta,
  type CameraPreset,
  type ColorMode,
  type SceneRanges,
} from "./sceneModel";

const PRESETS: Array<{ preset: CameraPreset; label: string }> = [
  { preset: "overview", label: "Genel" },
  { preset: "profile", label: "Kot profili" },
  { preset: "pig", label: "Pig" },
  { preset: "equipment", label: "Vana/Pompa" },
  { preset: "top", label: "Kuş bakışı" },
];

const BUTTON_BASE =
  "inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 text-[10px] font-medium transition-colors " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan";

const BUTTON_IDLE =
  "border-line/80 bg-ink-900/70 text-mist-400 hover:border-cyan/40 hover:text-mist-100";
const BUTTON_ACTIVE = "border-cyan/60 bg-cyan/15 text-cyan";

interface PresetToolbarProps {
  preset: CameraPreset;
  onPreset: (preset: CameraPreset) => void;
  cutaway: boolean;
  onCutaway: () => void;
  flow: boolean;
  onFlow: () => void;
  labels: boolean;
  onLabels: () => void;
  hasPig: boolean;
  pigPlaying: boolean;
  onPigPlay: () => void;
  pigRate: number;
  onPigRate: () => void;
  onReset: () => void;
  reducedMotion: boolean;
}

export function PresetToolbar({
  preset,
  onPreset,
  cutaway,
  onCutaway,
  flow,
  onFlow,
  labels,
  onLabels,
  hasPig,
  pigPlaying,
  onPigPlay,
  pigRate,
  onPigRate,
  onReset,
  reducedMotion,
}: PresetToolbarProps) {
  return (
    <div className="pointer-events-auto flex w-full max-w-full flex-col gap-1 rounded-xl border border-line/70 bg-ink-950/85 p-1.5 shadow-lg backdrop-blur-[2px] sm:w-auto sm:max-w-[calc(100vw-2rem)]">
      <div
        role="group"
        aria-label="Kamera ön ayarları"
        className="flex flex-wrap items-center gap-1"
      >
        <span className="hidden px-1 text-[9px] uppercase tracking-[0.16em] text-mist-500 sm:inline">
          Kamera
        </span>
        {PRESETS.map((item) => (
          <button
            key={item.preset}
            type="button"
            aria-label={`Kamera ön ayarı: ${item.label}`}
            aria-pressed={preset === item.preset}
            className={`${BUTTON_BASE} ${preset === item.preset ? BUTTON_ACTIVE : BUTTON_IDLE}`}
            onClick={() => onPreset(item.preset)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1 border-t border-line/50 pt-1">
        <button
          type="button"
          aria-label="Kesit görünümünü aç veya kapat"
          aria-pressed={cutaway}
          className={`${BUTTON_BASE} ${cutaway ? BUTTON_ACTIVE : BUTTON_IDLE}`}
          onClick={onCutaway}
        >          <Scissors size={12} aria-hidden />
          Kesit
        </button>
        <button
          type="button"
          aria-label="Akış animasyonunu aç veya kapat"
          aria-pressed={flow}
          className={`${BUTTON_BASE} ${flow ? BUTTON_ACTIVE : BUTTON_IDLE}`}
          onClick={onFlow}
        >
          <Droplets size={12} aria-hidden />
          Akış
        </button>
        <button
          type="button"
          aria-label="Sahne etiketlerini aç veya kapat"
          aria-pressed={labels}
          className={`${BUTTON_BASE} ${labels ? BUTTON_ACTIVE : BUTTON_IDLE}`}
          onClick={onLabels}
        >
          <Tag size={12} aria-hidden />
          Etiket
        </button>
        {hasPig ? (
          <>
            <button
              type="button"
              aria-label={pigPlaying ? "Pig animasyonunu duraklat" : "Pig animasyonunu oynat"}
              aria-pressed={pigPlaying}
              disabled={reducedMotion}
              title={
                reducedMotion
                  ? "Hareket azaltma açık; pig sabit konumda gösterilir."
                  : "Pig'i hat boyunca görsel olarak hareket ettir."
              }
              className={`${BUTTON_BASE} ${
                pigPlaying ? BUTTON_ACTIVE : BUTTON_IDLE
              } disabled:cursor-not-allowed disabled:opacity-50`}
              onClick={onPigPlay}
            >
              {pigPlaying ? <Pause size={12} aria-hidden /> : <Play size={12} aria-hidden />}
              Pig
            </button>
            <button
              type="button"
              aria-label={`Pig animasyon hızı: ${pigRate}×. Değiştirmek için tıkla.`}
              disabled={reducedMotion}
              className={`${BUTTON_BASE} ${BUTTON_IDLE} numeric disabled:cursor-not-allowed disabled:opacity-50`}
              onClick={onPigRate}
            >
              {pigRate}×
            </button>
          </>
        ) : null}
        <button
          type="button"
          aria-label="Sahneyi sıfırla: kamera, kesit ve katmanlar varsayılana döner"
          className={`${BUTTON_BASE} ${BUTTON_IDLE}`}
          onClick={onReset}
        >
          <RotateCcw size={12} aria-hidden />
          Sıfırla
        </button>
      </div>
    </div>
  );
}

interface SceneLegendProps {
  mode: ColorMode;
  onModeChange: (mode: ColorMode) => void;
  ranges: SceneRanges;
}

export function SceneLegend({ mode, onModeChange, ranges }: SceneLegendProps) {
  const min = mode === "pressure" ? ranges.pressure.min : 0;
  const max = mode === "pressure" ? ranges.pressure.max : 1;
  const mid = (min + max) / 2;
  const format = (value: number) =>
    mode === "pressure"
      ? `${numberFormat1.format(value)} bar`
      : percentFormat.format(value);

  return (
    <div className="pointer-events-auto w-[228px] max-w-full rounded-xl border border-line/70 bg-ink-950/85 p-2 shadow-lg">
      <div className="flex items-center justify-between gap-1">
        <span className="text-[9px] uppercase tracking-[0.16em] text-mist-500">Lejant</span>
        <div role="group" aria-label="Renk modu" className="flex gap-1">
          <button
            type="button"
            aria-label="Basınca göre renklendir"
            aria-pressed={mode === "pressure"}
            className={`rounded px-1.5 py-0.5 text-[9px] ${
              mode === "pressure" ? "bg-cyan/15 text-cyan" : "text-mist-500 hover:text-mist-200"
            }`}
            onClick={() => onModeChange("pressure")}
          >
            Basınç
          </button>
          <button
            type="button"
            aria-label="Kullanım oranına göre renklendir"
            aria-pressed={mode === "utilization"}
            className={`rounded px-1.5 py-0.5 text-[9px] ${
              mode === "utilization" ? "bg-cyan/15 text-cyan" : "text-mist-500 hover:text-mist-200"
            }`}
            onClick={() => onModeChange("utilization")}
          >
            Kullanım
          </button>
        </div>
      </div>
      <div
        className="mt-1.5 h-2 rounded-full border border-black/30"
        style={{ backgroundImage: legendGradient() }}
        role="presentation"
      />
      <div className="numeric mt-1 flex justify-between text-[9px] text-mist-500">
        <span>{format(min)}</span>
        <span>{format(mid)}</span>
        <span>{format(max)}</span>
      </div>
      <p className="mt-1 hidden text-[9px] leading-snug text-mist-500 sm:block">
        Yeşil güvenli, amber izleme, kırmızı sınır üstü. Veri yoksa segment gri kalır.
      </p>
    </div>
  );
}

interface SelectionCardProps {
  segment: SceneSegment | null;
  equipment: SceneEquipment | null;
  onClose: () => void;
}

export function SelectionCard({ segment, equipment, onClose }: SelectionCardProps) {
  if (!segment && !equipment) return null;
  const meta = statusMeta(segment?.status ?? equipment?.status);
  const title = segment?.label ?? equipment?.label ?? "";

  return (
    <div className="pointer-events-auto w-[248px] max-w-full rounded-xl border border-line/80 bg-ink-950/90 p-2.5 shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[9px] uppercase tracking-[0.16em] text-mist-500">
            {segment ? "Segment" : equipment ? EQUIPMENT_LABEL[equipment.type] : ""}
          </p>
          <p className="text-[12px] font-semibold text-mist-100">{title}</p>
        </div>
        <button
          type="button"
          aria-label="Seçimi kapat"
          className="-mr-1 -mt-1 grid h-6 w-6 place-items-center rounded text-mist-500 hover:bg-line/50 hover:text-mist-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-cyan"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      {segment ? (
        <dl className="numeric mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
          <dt className="text-mist-500">İstasyon</dt>
          <dd className="text-right text-mist-200">
            {formatDistance(segment.start_m)} – {formatDistance(segment.end_m)}
          </dd>
          <dt className="text-mist-500">Kot</dt>
          <dd className="text-right text-mist-200">
            {numberFormat1.format(segment.start_elevation_m)} →{" "}
            {numberFormat1.format(segment.end_elevation_m)} m
          </dd>
          <dt className="text-mist-500">Basınç</dt>
          <dd className="text-right text-mist-200">{formatPressure(segment.pressure_bar)}</dd>
          <dt className="text-mist-500">Kullanım</dt>
          <dd className="text-right text-mist-200">{formatUtilization(segment.utilization)}</dd>
          <dt className="col-span-2 mt-1 text-mist-500">{formatDiameter(segment)}</dt>
        </dl>
      ) : null}

      {equipment ? (
        <dl className="numeric mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
          <dt className="text-mist-500">İstasyon</dt>
          <dd className="text-right text-mist-200">{formatDistance(equipment.distance_m)}</dd>
          <dt className="text-mist-500">Kot</dt>
          <dd className="text-right text-mist-200">
            {numberFormat1.format(equipment.elevation_m)} m
          </dd>
        </dl>
      ) : null}

      <p className="mt-2 flex items-center gap-1.5 border-t border-line/50 pt-1.5 text-[10px] text-mist-400">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${meta.dot}`} />
        {meta.label}
      </p>
    </div>
  );
}

interface SceneDataTableProps {
  id: string;
  scene: SceneData;
  mode: ColorMode;
  ranges: SceneRanges;
}

export function SceneDataTable({ id, scene, mode, ranges }: SceneDataTableProps) {
  return (
    <div className="border-t border-line/70 bg-ink-950/95">
      <div className="max-h-[220px] overflow-auto">
        <table id={id} tabIndex={-1} className="w-full min-w-[760px] border-collapse text-left text-[11px]">
          <caption className="px-3 py-2 text-left text-[10px] uppercase tracking-[0.16em] text-mist-500">
            Saha verisi (3D sahnenin erişilebilir alternatifi)
          </caption>
          <thead className="sticky top-0 bg-ink-900 text-[10px] uppercase tracking-wide text-mist-500">
            <tr>
              <th scope="col" className="px-3 py-1.5 font-medium">Segment</th>
              <th scope="col" className="px-3 py-1.5 font-medium">İstasyon</th>
              <th scope="col" className="px-3 py-1.5 font-medium">Kot (m)</th>
              <th scope="col" className="px-3 py-1.5 font-medium">OD / WT (mm)</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">Basınç</th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">Kullanım</th>
              <th scope="col" className="px-3 py-1.5 font-medium">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/40 text-mist-200">
            {scene.segments.map((segment) => {
              const meta = statusMeta(segment.status);
              const swatch = colorForSegment(segment, mode, ranges).getStyle();
              return (
                <tr key={segment.id} className="hover:bg-line/20">
                  <th scope="row" className="px-3 py-1.5 font-medium text-mist-200">
                    <span
                      className="mr-1.5 inline-block h-2 w-2 rounded-sm align-middle"
                      style={{ backgroundColor: swatch }}
                    />
                    {segment.label}
                  </th>
                  <td className="numeric px-3 py-1.5">
                    {formatDistance(segment.start_m)} – {formatDistance(segment.end_m)}
                  </td>
                  <td className="numeric px-3 py-1.5">
                    {numberFormat1.format(segment.start_elevation_m)} →{" "}
                    {numberFormat1.format(segment.end_elevation_m)}
                  </td>
                  <td className="numeric px-3 py-1.5">
                    {numberFormat1.format(segment.outside_diameter_mm)} /{" "}
                    {numberFormat1.format(segment.wall_thickness_mm)}
                  </td>
                  <td className="numeric px-3 py-1.5 text-right">
                    {formatPressure(segment.pressure_bar)}
                  </td>
                  <td className="numeric px-3 py-1.5 text-right">
                    {formatUtilization(segment.utilization)}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`inline-block h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                      {meta.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {scene.equipment.length > 0 ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line/40 px-3 py-2 text-[10px] text-mist-500">
          <span className="uppercase tracking-[0.16em]">Ekipman</span>
          {scene.equipment.map((item) => (
            <span key={item.id} className="inline-flex items-center gap-1">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: statusMeta(item.status).color }}
              />
              {item.label}
              <span className="numeric text-mist-500">· {formatDistance(item.distance_m)}</span>
            </span>
          ))}
        </div>
      ) : null}
      <p className="border-t border-line/40 px-3 py-1.5 text-[9px] text-mist-500">
        Toplam hat {formatDistance(scene.segments[scene.segments.length - 1]?.end_m ?? 0)} ·{" "}
        {numberFormat0.format(scene.segments.length)} segment · ölçek dikey olarak abartılıdır.
      </p>
    </div>
  );
}
