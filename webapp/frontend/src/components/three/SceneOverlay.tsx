import {
  Droplets,
  Eye,
  MapPin,
  Pause,
  Play,
  RotateCcw,
  Scissors,
  Tag,
} from "lucide-react";
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
  type SceneViewMode,
  type VerticalScaleMode,
} from "./sceneModel";

const PRESETS: Array<{ preset: CameraPreset; label: string; detailOnly?: boolean }> = [
  { preset: "overview", label: "Genel" },
  { preset: "profile", label: "Kot profili" },
  { preset: "pig", label: "Pig", detailOnly: true },
  { preset: "equipment", label: "Vana/Pompa", detailOnly: true },
  { preset: "top", label: "Kuş bakışı" },
];

const VERTICAL_SCALES: Array<{ value: VerticalScaleMode; label: string }> = [
  { value: "auto", label: "Oto" },
  { value: "1x", label: "1×" },
  { value: "2x", label: "2×" },
  { value: "4x", label: "4×" },
];

const BUTTON_BASE =
  "inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 text-[11.5px] font-semibold transition-colors " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan";

const BUTTON_IDLE =
  "border-line/80 bg-ink-900/75 text-mist-200 hover:border-cyan/50 hover:text-mist-50";
const BUTTON_ACTIVE = "border-cyan/60 bg-cyan/15 text-cyan";

interface PresetToolbarProps {
  mode: SceneViewMode;
  preset: CameraPreset;
  onPreset: (preset: CameraPreset) => void;
  verticalScale: VerticalScaleMode;
  onVerticalScale: (scale: VerticalScaleMode) => void;
  translucentPipe: boolean;
  onTranslucentPipe: () => void;
  cutaway: boolean;
  onCutaway: () => void;
  flow: boolean;
  onFlow: () => void;
  labels: boolean;
  onLabels: () => void;
  hasLandmarks: boolean;
  landmarksVisible: boolean;
  onLandmarks: () => void;
  hasPig: boolean;
  pigPlaying: boolean;
  onPigPlay: () => void;
  pigRate: number;
  onPigRate: () => void;
  onReset: () => void;
  reducedMotion: boolean;
}

export function PresetToolbar({
  mode,
  preset,
  onPreset,
  verticalScale,
  onVerticalScale,
  translucentPipe,
  onTranslucentPipe,
  cutaway,
  onCutaway,
  flow,
  onFlow,
  labels,
  onLabels,
  hasLandmarks,
  landmarksVisible,
  onLandmarks,
  hasPig,
  pigPlaying,
  onPigPlay,
  pigRate,
  onPigRate,
  onReset,
  reducedMotion,
}: PresetToolbarProps) {
  const isOverview = mode === "overview";
  const visiblePresets = PRESETS.filter((item) => !isOverview || !item.detailOnly);

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
        {visiblePresets.map((item) => (
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
        <span className="ml-1 hidden px-1 text-[9px] uppercase tracking-[0.16em] text-mist-500 md:inline">
          Kot
        </span>
        <div role="group" aria-label="Dikey kot ölçeği" className="inline-flex gap-0.5">
          {VERTICAL_SCALES.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-label={`Dikey kot abartması: ${item.label}`}
              aria-pressed={verticalScale === item.value}
              className={`h-8 rounded-lg border px-2 text-[11px] font-semibold transition-colors ${
                verticalScale === item.value ? BUTTON_ACTIVE : BUTTON_IDLE
              }`}
              onClick={() => onVerticalScale(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1 border-t border-line/50 pt-1">
        {!isOverview ? (
          <>
            <button
              type="button"
              aria-label="Yarı saydam boru duvarını aç veya kapat"
              aria-pressed={translucentPipe}
              className={`${BUTTON_BASE} ${translucentPipe ? BUTTON_ACTIVE : BUTTON_IDLE}`}
              onClick={onTranslucentPipe}
            >
              <Eye size={13} aria-hidden />
              Saydam
            </button>
            <button
              type="button"
              aria-label="Kesit görünümünü aç veya kapat"
              aria-pressed={cutaway}
              className={`${BUTTON_BASE} ${cutaway ? BUTTON_ACTIVE : BUTTON_IDLE}`}
              onClick={onCutaway}
            >
              <Scissors size={13} aria-hidden />
              Kesit
            </button>
            <button
              type="button"
              aria-label="Akış animasyonunu aç veya kapat"
              aria-pressed={flow}
              className={`${BUTTON_BASE} ${flow ? BUTTON_ACTIVE : BUTTON_IDLE}`}
              onClick={onFlow}
            >
              <Droplets size={13} aria-hidden />
              Akış
            </button>
          </>
        ) : null}
        {hasLandmarks ? (
          <button
            type="button"
            aria-label="Pafta saha geçiş noktalarını aç veya kapat"
            aria-pressed={landmarksVisible}
            className={`${BUTTON_BASE} ${landmarksVisible ? BUTTON_ACTIVE : BUTTON_IDLE}`}
            onClick={onLandmarks}
          >
            <MapPin size={13} aria-hidden />
            Geçişler
          </button>
        ) : null}
        <button
          type="button"
          aria-label="Sahne etiketlerini aç veya kapat"
          aria-pressed={labels}
          className={`${BUTTON_BASE} ${labels ? BUTTON_ACTIVE : BUTTON_IDLE}`}
          onClick={onLabels}
        >
          <Tag size={13} aria-hidden />
          Etiket
        </button>
        {!isOverview && hasPig ? (
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
              {pigPlaying ? <Pause size={13} aria-hidden /> : <Play size={13} aria-hidden />}
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
          <RotateCcw size={13} aria-hidden />
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
            className={`rounded px-2.5 py-1 text-[11.5px] font-semibold ${
              mode === "pressure" ? "bg-cyan/15 text-cyan" : "text-mist-400 hover:text-mist-100"
            }`}
            onClick={() => onModeChange("pressure")}
          >
            Basınç
          </button>
          <button
            type="button"
            aria-label="Kullanım oranına göre renklendir"
            aria-pressed={mode === "utilization"}
            className={`rounded px-2.5 py-1 text-[11.5px] font-semibold ${
              mode === "utilization" ? "bg-cyan/15 text-cyan" : "text-mist-400 hover:text-mist-100"
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
  onOpenSession?: (sessionId: string) => void;
}

export function SelectionCard({ segment, equipment, onClose, onOpenSession }: SelectionCardProps) {
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
          {segment.grade ? (
            <>
              <dt className="text-mist-500">Kalite</dt>
              <dd className="truncate text-right text-mist-200" title={segment.grade}>
                {segment.grade}
              </dd>
            </>
          ) : null}
          {typeof segment.smys_mpa === "number" && Number.isFinite(segment.smys_mpa) ? (
            <>
              <dt className="text-mist-500">SMYS</dt>
              <dd className="text-right text-mist-200">
                {numberFormat1.format(segment.smys_mpa)} MPa
              </dd>
            </>
          ) : null}
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
      {segment?.session_id && onOpenSession ? (
        <button
          type="button"
          onClick={() => onOpenSession(segment.session_id!)}
          className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-cyan/50 bg-cyan/15 px-2.5 py-1.5 text-[11px] font-semibold text-cyan transition-colors hover:bg-cyan/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan"
        >
          Bu Test Bölümünü Aç
        </button>
      ) : null}
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
