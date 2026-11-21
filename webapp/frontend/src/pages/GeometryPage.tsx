import { useEffect, useId, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  ClipboardList,
  Database,
  GitCompareArrows,
  Layers,
  Mountain,
  Plus,
  Ruler,
  Trash2,
  Wand2,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionIdentityCard } from "../components/SectionIdentityCard";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { NumberField, SelectField, FieldGrid, ReadonlyValue } from "../components/ui/Field";
import { ConfirmDialog } from "../components/ui/Dialog";
import { InlineNotice, EmptyState } from "../components/ui/State";
import { ElevationProfileChart, UtilizationChart } from "../components/charts/LazyCharts";
import { SiteSurveyPanel } from "../components/geometry/SiteSurveyPanel";
import { FieldPage } from "./FieldPage";
import { useCatalog, useCalculateGeometry, useMeta } from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { PUMP_LABELS } from "../lib/constants";
import { fmt, formatInput, num, parseNumber } from "../lib/format";
import { computeGeometry, sectionsFromInputs } from "../lib/mock";
import { evaluateSegmentConsistency } from "../lib/kp";

function SegmentNumberCell({
  value,
  onChange,
  invalid,
  label,
}: {
  value: number | null;
  onChange: (value: number) => void;
  invalid?: boolean;
  label: string;
}) {
  const [text, setText] = useState(() => formatInput(value));
  useEffect(() => setText(formatInput(value)), [value]);

  const commit = () => {
    const parsed = parseNumber(text);
    if (parsed !== null && Number.isFinite(parsed)) onChange(parsed);
    setText(formatInput(value));
  };

  return (
    <input
      className="table-input"
      inputMode="decimal"
      aria-label={label}
      aria-invalid={invalid || undefined}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !event.nativeEvent.isComposing) {
          commit();
          (event.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}

function SegmentOptionalNumberCell({
  value,
  onChange,
  onInvalidChange,
  placeholder,
  label,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  onInvalidChange?: (isInvalid: boolean) => void;
  placeholder?: string;
  label: string;
}) {
  const [text, setText] = useState(() => formatInput(value));
  const [invalidInput, setInvalidInput] = useState(false);

  useEffect(() => {
    setText(formatInput(value));
    setInvalidInput(false);
    onInvalidChange?.(false);
    // Intentionally sync external resets only on store value change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const setValidity = (next: boolean) => {
    setInvalidInput(next);
    onInvalidChange?.(next);
  };

  const commit = () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setValidity(false);
      onChange(null);
      setText("");
      return;
    }
    const parsed = parseNumber(trimmed);
    if (parsed !== null && Number.isFinite(parsed) && parsed > 0) {
      setValidity(false);
      onChange(parsed);
      return;
    }
    setValidity(true);
  };

  return (
    <input
      className="table-input"
      inputMode="decimal"
      placeholder={placeholder}
      aria-label={label}
      aria-invalid={invalidInput || undefined}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        if (invalidInput) setValidity(false);
      }}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !event.nativeEvent.isComposing) {
          commit();
          (event.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}

export function GeometryPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const updateSegment = useAppStore((state) => state.updateSegment);
  const removeSegment = useAppStore((state) => state.removeSegment);
  const moveSegment = useAppStore((state) => state.moveSegment);
  const addSegment = useAppStore((state) => state.addSegment);
  const setSegments = useAppStore((state) => state.setSegments);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const { pipes, grades } = useCatalog();
  const { data: meta } = useMeta();
  const calculate = useCalculateGeometry();
  const [confirmClearSegments, setConfirmClearSegments] = useState(false);
  const [invalidSmysIds, setInvalidSmysIds] = useState<Record<string, boolean>>({});
  const segmentTableCaptionId = useId();

  const setRowSmysInvalid = (id: string, isInvalid: boolean) => {
    setInvalidSmysIds((prev) => {
      if (isInvalid) {
        return prev[id] ? prev : { ...prev, [id]: true };
      }
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const selectedPipe = pipes.find((pipe) => pipe.option_label === inputs.geometry_catalog.size_option);
  const scheduleOptions = selectedPipe?.schedules ?? [];

  const sections = sectionsFromInputs(inputs);
  const localGeometry = sections.length > 0 ? computeGeometry(sections) : null;
  const geometry = results.geometry ?? localGeometry;

  const odError =
    inputs.geometry.outside_diameter_mm !== null && inputs.geometry.outside_diameter_mm <= 0
      ? "Dış çap 0'dan büyük olmalı."
      : null;
  const wtError =
    inputs.geometry.wall_thickness_mm !== null &&
    inputs.geometry.outside_diameter_mm !== null &&
    inputs.geometry.wall_thickness_mm * 2 >= inputs.geometry.outside_diameter_mm
      ? "Et kalınlığı iç çapı sıfıra düşürecek kadar büyük olamaz (2·WT < OD)."
      : inputs.geometry.wall_thickness_mm !== null && inputs.geometry.wall_thickness_mm <= 0
        ? "Et kalınlığı 0'dan büyük olmalı."
        : null;
  const lengthWarning =
    inputs.geometry.length_m !== null && inputs.geometry.length_m > 20_000
      ? "Şartname limiti 20.000 m; bu uzunluk tek test bölümü için uygun değildir."
      : null;

  const profile = inputs.section_profile;
  const highestError =
    profile.highest_elevation_m !== null &&
    profile.lowest_elevation_m !== null &&
    profile.highest_elevation_m < profile.lowest_elevation_m
      ? "En yüksek kot, en düşük kottan küçük olamaz."
      : null;
  const startError =
    profile.start_elevation_m !== null &&
    profile.highest_elevation_m !== null &&
    profile.lowest_elevation_m !== null &&
    (profile.start_elevation_m < profile.lowest_elevation_m ||
      profile.start_elevation_m > profile.highest_elevation_m)
      ? "Başlangıç kotu, en düşük–en yüksek aralığında olmalı."
      : null;
  const endError =
    profile.end_elevation_m !== null &&
    profile.highest_elevation_m !== null &&
    profile.lowest_elevation_m !== null &&
    (profile.end_elevation_m < profile.lowest_elevation_m ||
      profile.end_elevation_m > profile.highest_elevation_m)
      ? "Bitiş kotu, en düşük–en yüksek aralığında olmalı."
      : null;

  function applyCatalog(sizeOption: string, scheduleOption?: string) {
    const pipe = pipes.find((item) => item.option_label === sizeOption);
    if (!pipe) return;
    const schedule =
      pipe.schedules.find((item) => item.label === scheduleOption) ?? pipe.schedules[0];
    patchInputs({
      geometry_catalog: {
        size_option: pipe.option_label,
        schedule_option: schedule?.label ?? "",
      },
      geometry: {
        outside_diameter_mm: pipe.outside_diameter_mm,
        ...(schedule ? { wall_thickness_mm: schedule.wall_thickness_mm } : {}),
      },
    });
  }

  const totalLength = geometry?.total_length_m ?? 0;
  const totalVolume = geometry?.internal_volume_m3 ?? 0;

  const segmentSmysAnalysis = useMemo(() => {
    const defaultSmys = profile.smys_mpa;
    const perRow = inputs.segments.map((segment) => {
      const customSmys =
        segment.smys_mpa !== null && segment.smys_mpa !== undefined && segment.smys_mpa > 0
          ? segment.smys_mpa
          : null;
      const effectiveSmys =
        customSmys ?? (defaultSmys !== null && defaultSmys > 0 ? defaultSmys : null);
      const od = segment.outside_diameter_mm;
      const wt = segment.wall_thickness_mm;
      const p100 =
        effectiveSmys !== null &&
        od !== null &&
        wt !== null &&
        od > 0 &&
        wt > 0 &&
        wt * 2 < od
          ? (20 * effectiveSmys * wt) / od
          : null;
      return { customSmys, effectiveSmys, p100 };
    });
    const validPressures = perRow
      .map((item) => item.p100)
      .filter((value): value is number => value !== null && Number.isFinite(value));
    const minPressure = validPressures.length > 0 ? Math.min(...validPressures) : null;
    return { perRow, minPressure };
  }, [inputs.segments, profile.smys_mpa]);

  /* Segment kontrolü: Σ Segment Uzunluğu == Section (ΔKP) ve istasyon/geometri doğruluğu */
  const segmentSummary = useMemo(
    () =>
      evaluateSegmentConsistency({
        segments: inputs.segments,
        sectionMeta: inputs.section_meta,
        fallbackLengthM: inputs.geometry.length_m,
      }),
    [inputs.segments, inputs.section_meta, inputs.geometry.length_m],
  );

  const segmentLengthTone =
    segmentSummary.status === "fail" ? "fail" : segmentSummary.status === "warning" ? "warning" : "pass";

  const hasInvalidSmys = inputs.segments.some((seg) => invalidSmysIds[seg.id]);
  const badgeSegmentMinSmys =
    profile.smys_mpa === null &&
    inputs.segments.length > 0 &&
    segmentSmysAnalysis.perRow.every((row) => row.effectiveSmys !== null)
      ? Math.min(...segmentSmysAnalysis.perRow.map((row) => row.effectiveSmys as number))
      : null;

  function validateGeometry() {
    if (hasInvalidSmys) {
      pushToast(
        "error",
        "Geçersiz segment SMYS değeri",
        "Segment tablosundaki SMYS (MPa) değerleri 0'dan büyük geçerli bir sayı olmalı veya boş bırakılmalıdır.",
      );
      return;
    }
    if (segmentSummary.status === "fail") {
      pushToast(
        "error",
        "Segment kontrolü engelleyici",
        segmentSummary.headline || "Segmentleri Section KP aralığıyla eşleştirin.",
      );
      return;
    }
    if (!sections.length) {
      pushToast("error", "Geometri eksik", "Önce dış çap, et kalınlığı ve uzunluk girin.");
      return;
    }
    if (wtError || odError) {
      pushToast("error", "Geometri doğrulanamadı", wtError ?? odError ?? "");
      return;
    }
    calculate.mutate(sections, {
      onSuccess: ({ data }) => {
        pushToast(
          "success",
          "Geometri doğrulandı",
          `${data.section_count} kesit · ${fmt.m(data.total_length_m, 0)} · ${fmt.m3Short(data.internal_volume_m3)}`,
        );
      },
      onError: (error) => {
        pushToast("error", "Geometri doğrulanamadı", error.message);
      },
    });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Geometri & Saha"
        title="Kesit, segmentler, kotlar ve saha profili"
        description="Segment listesi doluysa tek kesit alanları yok sayılır; hat, segmentlerin zincirleme toplamından hesaplanır."
        meta={
          <>
            <Badge tone={sections.length ? "pass" : "warning"}>
              {sections.length ? `${sections.length} kesit hazır` : "Kesit eksik"}
            </Badge>
            <Badge tone={segmentLengthTone}>
              {segmentSummary.hasSegments
                ? segmentSummary.badgeLabel
                : segmentSummary.status === "neutral"
                  ? "Tek tip boru modu"
                  : "Segment modu"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              {geometry ? `${fmt.m(totalLength, 0)} · ${fmt.m3Short(totalVolume)}` : "—"}
            </span>
          </>
        }
        actions={
          <>
            <Button size="lg" icon={<ArrowRight size={15} />} onClick={() => setTab("air")}>
              Hava testine geç
            </Button>
            <Button
              size="lg"
              variant="primary"
              icon={<CheckCircle2 size={15} />}
              loading={calculate.isPending}
              onClick={validateGeometry}
            >
              Geometriyi doğrula
            </Button>
          </>
        }
      />

      <SectionIdentityCard />

      <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
        <SectionCard
          title="Katalogdan seç"
          description="ASME B36.10 NPS ve schedule seçimi dış çap / et kalınlığını doldurur."
          icon={Database}
        >
          <FieldGrid cols={2}>
            <SelectField
              label="NPS / DN"
              value={inputs.geometry_catalog.size_option}
              onChange={(value) => applyCatalog(value)}
              options={pipes.map((pipe) => ({ value: pipe.option_label, label: pipe.option_label }))}
              placeholder="Boru çapı seçin"
              help={selectedPipe ? `OD ${fmt.mm(selectedPipe.outside_diameter_mm)} · DN ${selectedPipe.dn}` : "Listeden seçim opsiyoneldir"}
            />
            <SelectField
              label="Schedule / et kalınlığı"
              value={inputs.geometry_catalog.schedule_option}
              onChange={(value) => applyCatalog(inputs.geometry_catalog.size_option, value)}
              options={scheduleOptions.map((schedule) => ({
                value: schedule.label,
                label: schedule.label,
              }))}
              placeholder="Schedule seçin"
              disabled={scheduleOptions.length === 0}
              help={selectedPipe ? `${scheduleOptions.length} schedule seçeneği` : "Önce NPS seçin"}
            />
          </FieldGrid>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
            <p className="text-[10.5px] leading-relaxed text-[var(--text-faint)]">
              Seçim yalnızca tek kesit alanlarını doldurur; segment tablosunu değiştirmez.
            </p>
            <Button
              size="sm"
              icon={<Wand2 size={12} />}
              disabled={!selectedPipe}
              onClick={() => applyCatalog(inputs.geometry_catalog.size_option)}
            >
              Alanları doldur
            </Button>
          </div>
        </SectionCard>

        <SectionCard
          title="Tek kesit (segment yoksa)"
          description="Segment listesi boşken kullanılır. Türetilen değerler anlık güncellenir."
          icon={Ruler}
        >
          <FieldGrid cols={2}>
            <NumberField
              label="Dış çap (OD)"
              unit="mm"
              value={inputs.geometry.outside_diameter_mm}
              onChange={(value) => patchInputs({ geometry: { outside_diameter_mm: value } })}
              error={odError}
              min={1}
              max={5000}
              required
            />
            <NumberField
              label="Et kalınlığı (WT)"
              unit="mm"
              value={inputs.geometry.wall_thickness_mm}
              onChange={(value) => patchInputs({ geometry: { wall_thickness_mm: value } })}
              error={wtError}
              min={0.1}
              max={200}
              required
            />
            <NumberField
              label="Hat uzunluğu"
              unit="m"
              value={inputs.geometry.length_m}
              onChange={(value) => patchInputs({ geometry: { length_m: value } })}
              help="Şartname limiti 20.000 m"
              error={lengthWarning}
              min={0.1}
              required
              className="sm:col-span-2"
            />
          </FieldGrid>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <ResultTile
              label="İç yarıçap"
              value={localGeometry ? num(localGeometry.internal_radius_mm, 2) : "—"}
              unit="mm"
            />
            <ResultTile
              label="İç hacim"
              value={localGeometry ? num(localGeometry.internal_volume_m3, 1) : "—"}
              unit="m³"
            />
            <ResultTile
              label="0,884·ri/s"
              value={localGeometry ? num(localGeometry.elasticity_term, 3) : "—"}
              hint="Elastisite terimi"
            />
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title={`Segment tablosu (${inputs.segments.length})`}
        description="Her satır bir boru kesiti. İstasyonlar zincirleme türetilir; sıralama 3D sahneyi de belirler."
        icon={Layers}
        action={
          <>
            <Button size="sm" icon={<Plus size={12} />} onClick={addSegment}>
              Segment ekle
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Trash2 size={12} />}
              disabled={inputs.segments.length === 0}
              onClick={() => setConfirmClearSegments(true)}
            >
              Temizle
            </Button>
          </>
        }
        bodyClassName="pt-3"
      >
        {inputs.segments.length === 0 ? (
          <EmptyState
            title="Segment yok — tek kesit modu"
            description="Segment ekleyerek farklı çap ve et kalınlıklarından oluşan hattı modelleyebilirsiniz. Boş bırakırsanız yukarıdaki tek kesit kullanılır."
            icon={Layers}
            action={
              <Button size="sm" variant="primary" icon={<Plus size={12} />} onClick={addSegment}>
                İlk segmenti ekle
              </Button>
            }
          />
        ) : (
          <div
            tabIndex={0}
            role="region"
            aria-labelledby={segmentTableCaptionId}
            className="table-wrap scroll-thin"
          >
            <table className="data compact">
              <caption id={segmentTableCaptionId} className="sr-only">
                Boru segmentleri; çap, et kalınlığı, malzeme kalitesi, SMYS, uzunluk, 100% SMYS ve istasyon
              </caption>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">NPS</th>
                  <th scope="col">Schedule</th>
                  <th scope="col">Kalite</th>
                  <th scope="col" className="num">SMYS (MPa)</th>
                  <th scope="col" className="num">OD (mm)</th>
                  <th scope="col" className="num">WT (mm)</th>
                  <th scope="col" className="num">L (m)</th>
                  <th scope="col" className="num">100% SMYS (bar)</th>
                  <th scope="col" className="num">İstasyon (m)</th>
                  <th scope="col" className="num">Vt (m³)</th>
                  <th scope="col" className="num">KP Aralığı</th>
                  <th scope="col">Durum</th>
                  <th scope="col"><span className="sr-only">İşlemler</span></th>
                </tr>
              </thead>
              <tbody>
                {inputs.segments.map((segment, index) => {
                  const row = segmentSummary.rows[index];
                  const smysRow = segmentSmysAnalysis.perRow[index];
                  const p100 = smysRow?.p100 ?? null;
                  const isLimitingSegment =
                    inputs.segments.length >= 2 &&
                    p100 !== null &&
                    segmentSmysAnalysis.minPressure !== null &&
                    Math.abs(p100 - segmentSmysAnalysis.minPressure) < 1e-6;
                  const invalid =
                    segment.outside_diameter_mm !== null &&
                    segment.wall_thickness_mm !== null &&
                    segment.wall_thickness_mm * 2 >= segment.outside_diameter_mm;
                  const volume =
                    segment.outside_diameter_mm &&
                    segment.wall_thickness_mm &&
                    segment.length_m &&
                    segment.wall_thickness_mm * 2 < segment.outside_diameter_mm
                      ? Math.PI *
                        ((segment.outside_diameter_mm / 2 - segment.wall_thickness_mm) / 1000) ** 2 *
                        segment.length_m
                      : null;
                  const selectedGradeOption = segment.material_grade ?? "";
                  return (
                    <tr key={segment.id}>
                      <td className="font-mono text-[11px] text-[var(--text-faint)]">{index + 1}</td>
                      <td className="w-[104px] max-w-[104px]">
                        <input
                          className="table-input text-left font-sans"
                          aria-label={`Segment ${index + 1} NPS`}
                          title={segment.nps_label}
                          value={segment.nps_label}
                          onChange={(event) => updateSegment(segment.id, { nps_label: event.target.value })}
                        />
                      </td>
                      <td className="w-[112px] max-w-[112px]">
                        <input
                          className="table-input text-left font-sans"
                          aria-label={`Segment ${index + 1} schedule`}
                          title={segment.schedule_label}
                          value={segment.schedule_label}
                          onChange={(event) => updateSegment(segment.id, { schedule_label: event.target.value })}
                        />
                      </td>
                      <td className="min-w-[142px] max-w-[168px]">
                        <select
                          className="table-input text-left font-sans"
                          aria-label={`Segment ${index + 1} malzeme kalitesi`}
                          value={selectedGradeOption}
                          onChange={(event) => {
                            const val = event.target.value;
                            if (!val) {
                              updateSegment(segment.id, { material_grade: "", smys_mpa: null });
                              return;
                            }
                            const matched = grades.find((item) => item.option_label === val);
                            updateSegment(segment.id, {
                              material_grade: val,
                              smys_mpa: matched?.smys_mpa ?? segment.smys_mpa ?? null,
                            });
                          }}
                        >
                          <option value="">
                            {profile.smys_mpa
                              ? `Hat varsayılanı (${num(profile.smys_mpa, 0)})`
                              : "Hat varsayılanı"}
                          </option>
                          {selectedGradeOption &&
                          !grades.some((item) => item.option_label === selectedGradeOption) ? (
                            <option value={selectedGradeOption}>{selectedGradeOption}</option>
                          ) : null}
                          {grades.map((grade) => (
                            <option key={grade.option_label} value={grade.option_label}>
                              {grade.grade} ({grade.smys_mpa} MPa)
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="w-[82px] max-w-[90px]">
                        <SegmentOptionalNumberCell
                          label={`Segment ${index + 1} SMYS (MPa)`}
                          placeholder={profile.smys_mpa ? formatInput(profile.smys_mpa) : "—"}
                          value={segment.smys_mpa ?? null}
                          onInvalidChange={(isInvalid) => setRowSmysInvalid(segment.id, isInvalid)}
                          onChange={(value) => {
                            if (value === null) {
                              updateSegment(segment.id, { smys_mpa: null, material_grade: "" });
                              return;
                            }
                            const currentGrade = grades.find(
                              (item) => item.option_label === (segment.material_grade ?? ""),
                            );
                            const nextGrade =
                              currentGrade && Math.abs(currentGrade.smys_mpa - value) < 1e-6
                                ? segment.material_grade
                                : "";
                            updateSegment(segment.id, {
                              smys_mpa: value,
                              material_grade: nextGrade,
                            });
                          }}
                        />
                      </td>
                      <td>
                        <SegmentNumberCell
                          label={`Segment ${index + 1} dış çap`}
                          value={segment.outside_diameter_mm}
                          onChange={(value) => updateSegment(segment.id, { outside_diameter_mm: value })}
                          invalid={invalid}
                        />
                      </td>
                      <td>
                        <SegmentNumberCell
                          label={`Segment ${index + 1} et kalınlığı`}
                          value={segment.wall_thickness_mm}
                          onChange={(value) => updateSegment(segment.id, { wall_thickness_mm: value })}
                          invalid={invalid}
                        />
                      </td>
                      <td>
                        <SegmentNumberCell
                          label={`Segment ${index + 1} uzunluk`}
                          value={segment.length_m}
                          onChange={(value) => updateSegment(segment.id, { length_m: value })}
                        />
                      </td>
                      <td className="num">
                        <div className="flex items-center justify-end gap-1">
                          <span>{p100 !== null ? num(p100, 1) : "—"}</span>
                          {isLimitingSegment ? <Badge tone="warning">Limit</Badge> : null}
                        </div>
                      </td>
                      <td className="num text-[var(--text-faint)]">{num(segment.start_station_m, 0)}</td>
                      <td className="num">{volume !== null ? num(volume, 3) : "—"}</td>
                      <td className="num font-mono text-[10px]">
                        {row ? `${row.startKp} → ${row.endKp}` : "—"}
                      </td>
                      <td>
                        {row ? (
                          <Badge
                            tone={row.status === "fail" ? "fail" : row.status === "warning" ? "warning" : "pass"}
                          >
                            {row.status === "fail"
                              ? "HATA"
                              : row.status === "warning"
                                ? "UYARI"
                                : "OK"}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-faint)] text-[10px]">—</span>
                        )}
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-0.5">
                          <button
                            type="button"
                            className="btn btn-icon btn-sm"
                            aria-label={`Segment ${index + 1} yukarı taşı`}
                            disabled={index === 0}
                            onClick={() => moveSegment(segment.id, -1)}
                          >
                            <ArrowUp size={12} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-icon btn-sm"
                            aria-label={`Segment ${index + 1} aşağı taşı`}
                            disabled={index === inputs.segments.length - 1}
                            onClick={() => moveSegment(segment.id, 1)}
                          >
                            <ArrowDown size={12} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-icon btn-sm hover:text-[var(--danger)]"
                            aria-label={`Segment ${index + 1} sil`}
                            onClick={() => {
                              setRowSmysInvalid(segment.id, false);
                              removeSegment(segment.id);
                            }}
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={7} className="text-right text-[11px] font-semibold text-[var(--text-muted)]">
                    Toplam / Limit
                  </td>
                  <td className="num font-semibold">{num(totalLength, 2)}</td>
                  <td className="num text-[11px] font-semibold text-[var(--text-muted)]">
                    {segmentSmysAnalysis.minPressure !== null
                      ? num(segmentSmysAnalysis.minPressure, 1)
                      : "—"}
                  </td>
                  <td className="num">{num(totalLength, 0)}</td>
                  <td className="num font-semibold">{num(totalVolume, 3)}</td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
        {wtError ? <p className="mt-2 text-[11px] text-[var(--danger)]">{wtError}</p> : null}
        {hasInvalidSmys ? (
          <p role="alert" className="mt-2 text-[11px] text-[var(--danger)]">
            Bazı segmentlerde geçersiz SMYS değeri var. Segment SMYS (MPa) değerleri 0'dan büyük olmalı veya boş bırakılmalıdır.
          </p>
        ) : null}
        {segmentSummary.hasSegments && segmentSummary.issues.length > 0 ? (
          <div className="mt-3 space-y-1">
            <InlineNotice
              tone={segmentSummary.status === "fail" ? "danger" : "warning"}
              icon={GitCompareArrows}
              title={`Segment Denetimi: ${segmentSummary.headline}`}
            >
              {segmentSummary.issues.map((issue, i) => (
                <p key={`${issue}-${i}`} className="mt-1 text-[10.5px] leading-snug text-[var(--text-muted)]">
                  {issue}
                </p>
              ))}
            </InlineNotice>
          </div>
        ) : segmentSummary.hasSegments ? (
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[11.5px]">
            <CheckCircle2 size={13} className="tone-pass shrink-0" aria-hidden />
            <span className="text-[var(--text)]">
              {segmentSummary.headline}
              {segmentSummary.deltaLengthM !== null &&
                segmentSummary.deltaLengthM !== 0 &&
                segmentSummary.deltaLengthM !== null && (
                  <>
                    (ΔKP:{segmentSummary.deltaLengthM > 0 ? "+" : ""}{num(segmentSummary.deltaLengthM, 0)} m)
                  </>
                )}
            </span>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        title="Test bölümü profili"
        description="Kotlar, dizayn basıncı, malzeme ve Location Class basınç penceresini belirler."
        icon={Mountain}
        action={
          <Badge tone={profile.smys_mpa || badgeSegmentMinSmys !== null ? "pass" : "warning"}>
            {profile.smys_mpa
              ? `SMYS ${num(profile.smys_mpa, 0)} MPa`
              : badgeSegmentMinSmys !== null
                ? `Segment min ${num(badgeSegmentMinSmys, 0)} MPa`
                : "SMYS eksik"}
          </Badge>
        }
      >
        <FieldGrid cols={3}>
          <NumberField
            label="En yüksek nokta kotu"
            unit="m"
            value={profile.highest_elevation_m}
            onChange={(value) => patchInputs({ section_profile: { highest_elevation_m: value } })}
            error={highestError}
          />
          <NumberField
            label="En düşük nokta kotu"
            unit="m"
            value={profile.lowest_elevation_m}
            onChange={(value) => patchInputs({ section_profile: { lowest_elevation_m: value } })}
          />
          <NumberField
            label="Başlangıç kotu"
            unit="m"
            value={profile.start_elevation_m}
            onChange={(value) => patchInputs({ section_profile: { start_elevation_m: value } })}
            error={startError}
          />
          <NumberField
            label="Bitiş kotu"
            unit="m"
            value={profile.end_elevation_m}
            onChange={(value) => patchInputs({ section_profile: { end_elevation_m: value } })}
            error={endError}
          />
          <NumberField
            label="Dizayn basıncı"
            unit="bar"
            value={profile.design_pressure_bar}
            onChange={(value) => patchInputs({ section_profile: { design_pressure_bar: value } })}
            min={0.1}
          />
          <SelectField
            label="Malzeme kalitesi"
            value={inputs.material_grade}
            onChange={(value) => {
              const grade = grades.find((item) => item.option_label === value);
              patchInputs({
                material_grade: value,
                section_profile: { smys_mpa: grade?.smys_mpa ?? profile.smys_mpa },
              });
            }}
            options={grades.map((grade) => ({ value: grade.option_label, label: grade.option_label }))}
            placeholder="API 5L PSL2 kalite seçin"
            help="Hat varsayılanı; segment tablosunda farklı kalite girilmemişse kullanılır."
          />
          <ReadonlyValue
            label="SMYS"
            unit="MPa"
            value={profile.smys_mpa !== null ? num(profile.smys_mpa, 0) : "—"}
            hint="Kalite seçimiyle dolar."
          />
          <SelectField
            label="Location Class"
            value={inputs.location_class}
            onChange={(value) => patchInputs({ location_class: value })}
            options={(meta?.location_classes ?? []).map((rule) => ({
              value: rule.label,
              label: `${rule.label} · ×${rule.minimum_test_factor}`,
            }))}
            help="Test basıncı minimum faktörünü belirler."
          />
          <SelectField
            label="Pompa konumu"
            value={inputs.pump_location}
            onChange={(value) => patchInputs({ pump_location: value })}
            options={(meta?.pump_locations ?? ["Baslangic noktasi", "Bitis noktasi"]).map((value) => ({
              value,
              label: PUMP_LABELS[value] ?? value,
            }))}
            placeholder="Pompa konumu seçin"
          />
        </FieldGrid>
        {profile.highest_elevation_m !== null && profile.lowest_elevation_m !== null ? (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <ResultTile label="Kot farkı" value={num(profile.highest_elevation_m - profile.lowest_elevation_m, 0)} unit="m" />
            <ResultTile label="Dizayn" value={num(profile.design_pressure_bar, 1)} unit="bar" />
            <ResultTile
              label="Min test (×1,25)"
              value={profile.design_pressure_bar ? num(profile.design_pressure_bar * 1.25, 1) : "—"}
              unit="bar"
            />
            <ResultTile
              label="Uzunluk limiti"
              value={num(totalLength, 0)}
              unit="m"
              tone={totalLength > 20_000 ? "fail" : "pass"}
              hint="≤ 20.000 m"
            />
          </div>
        ) : null}
      </SectionCard>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <SectionCard title="Kot şeması" description="Pompa noktası sarı işaretle gösterilir." icon={Mountain}>
          <ElevationProfileChart inputs={inputs} height={240} />
        </SectionCard>
        <SectionCard title="Segment kullanımı" description="İzlenen basıncın 100% SMYS limitine oranı." icon={Layers}>
          {geometry || results.profile ? (
            <UtilizationChart
              results={{ ...results, geometry: geometry ?? undefined }}
              defaultSmysMpa={inputs.section_profile.smys_mpa}
              height={240}
            />
          ) : (
            <EmptyState title="Kullanım verisi yok" description="Önce geometriyi doğrulayın ve profil hesabını çalıştırın." icon={Layers} />
          )}
          <div className="mt-2 grid grid-cols-3 gap-2">
            <ResultTile label="Toplam uzunluk" value={num(totalLength, 0)} unit="m" />
            <ResultTile label="Toplam hacim" value={num(totalVolume, 3)} unit="m³" />
            <ResultTile
              label="Hacim limiti"
              value={`${num(totalVolume, 0)} / 12.500`}
              unit="m³"
              tone={totalVolume > 12_500 ? "fail" : "pass"}
            />
          </div>
        </SectionCard>
      </div>

      {!geometry ? (
        <InlineNotice tone="warning" title="Hesap için geometri gerekli" icon={ClipboardList}>
          Tek kesit veya en az bir geçerli segment girildiğinde toplamlar ve doğrulama etkinleşir.
        </InlineNotice>
      ) : null}

      <SiteSurveyPanel totalLength={totalLength} />

      <FieldPage embedded />

      <ConfirmDialog
        open={confirmClearSegments}
        title="Segment tablosu temizlensin mi?"
        message="Tüm boru segment satırları listeden kaldırılır; hesaplama tek kesit moduna döner."
        confirmLabel="Tümünü Temizle"
        danger
        onConfirm={() => {
          setInvalidSmysIds({});
          setSegments([]);
        }}
        onClose={() => setConfirmClearSegments(false)}
      />
    </div>
  );
}
