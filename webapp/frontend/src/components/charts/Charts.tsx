import { useId } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AppInputs, PressureProfileResponse, ResultBundle } from "../../lib/types";
import { num } from "../../lib/format";
import { PUMP_LABELS } from "../../lib/constants";

interface TooltipEntry {
  name?: string;
  value?: number | string | null;
  color?: string;
  dataKey?: string | number;
}

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: number | string;
  formatter?: (value: number, name: string) => string;
  labelFormatter?: (label: number | string) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-[var(--border-strong)] bg-[var(--surface-raised)] px-2.5 py-2 shadow-xl">
      {label !== undefined ? (
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
          {labelFormatter ? labelFormatter(label) : label}
        </p>
      ) : null}
      {payload.map((entry, index) => {
        const numeric = typeof entry.value === "number" ? entry.value : Number(entry.value ?? 0);
        return (
          <p key={index} className="flex items-center gap-1.5 text-[11px] text-[var(--text-soft)]">
            <span className="legend-dot" style={{ background: entry.color }} aria-hidden />
            <span>{entry.name}</span>
            <span className="ml-auto font-mono text-[var(--text)]">
              {formatter ? formatter(numeric, entry.name ?? "") : num(numeric, 2)}
            </span>
          </p>
        );
      })}
    </div>
  );
}

function useGradientId(prefix: string): string {
  return `${prefix}-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
}

export interface ElevationPoint {
  station: number;
  elevation: number;
}

export function elevationPoints(inputs: AppInputs): ElevationPoint[] {
  const total = inputs.segments.reduce((sum, segment) => sum + (segment.length_m ?? 0), 0) ||
    (inputs.geometry.length_m ?? 0);
  if (total <= 0) return [];
  const highest = inputs.section_profile.highest_elevation_m ?? 0;
  const lowest = inputs.section_profile.lowest_elevation_m ?? 0;
  const start = inputs.section_profile.start_elevation_m ?? lowest;
  const end = inputs.section_profile.end_elevation_m ?? highest;
  return [
    { station: 0, elevation: start },
    { station: total * 0.33, elevation: highest },
    { station: total * 0.68, elevation: lowest },
    { station: total, elevation: end },
  ];
}

export function ElevationProfileChart({
  inputs,
  className,
  height = 220,
}: {
  inputs: AppInputs;
  className?: string;
  height?: number;
}) {
  const gradient = useGradientId("elev");
  const data = elevationPoints(inputs);
  const total = data[data.length - 1]?.station ?? 0;
  const pumpAtStart = !inputs.pump_location.includes("Bitis") && !inputs.pump_location.includes("Bitiş");
  const pumpElevation = pumpAtStart ? data[0]?.elevation : data[data.length - 1]?.elevation;

  if (data.length === 0) {
    return (
      <div className={className} style={{ height }}>
        <div className="grid h-full place-items-center rounded-xl border border-dashed border-[var(--border)] text-[11.5px] text-[var(--text-faint)]">
          Kot verisi girilmedi
        </div>
      </div>
    );
  }

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 16, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.42} />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--grid-line)" vertical={false} />
          <XAxis
            dataKey="station"
            type="number"
            domain={[0, total]}
            tickFormatter={(value: number) => `${num(value / 1000, 1)} km`}
            tick={{ fontSize: 10, fill: "var(--text-faint)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            domain={["dataMin - 25", "dataMax + 25"]}
            tickFormatter={(value: number) => num(value, 0)}
            tick={{ fontSize: 10, fill: "var(--text-faint)" }}
            axisLine={false}
            tickLine={false}
            width={52}
            unit=" m"
          />
          <Tooltip
            content={
              <ChartTooltip
                labelFormatter={(label) => `İstasyon ${num(Number(label), 0)} m`}
                formatter={(value) => `${num(value, 2)} m`}
              />
            }
          />
          <Area
            type="monotone"
            dataKey="elevation"
            name="Kot"
            stroke="var(--chart-1)"
            strokeWidth={2}
            fill={`url(#${gradient})`}
            isAnimationActive={false}
          />
          {pumpElevation !== undefined ? (
            <ReferenceDot
              x={pumpAtStart ? 0 : total}
              y={pumpElevation}
              r={4.5}
              fill="var(--warning)"
              stroke="var(--surface)"
              strokeWidth={2}
              ifOverflow="extendDomain"
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PressureWindowChart({
  inputs,
  profile,
  height = 230,
  className,
}: {
  inputs: AppInputs;
  profile?: PressureProfileResponse;
  height?: number;
  className?: string;
}) {
  const total =
    profile?.total_length_m ??
    (inputs.segments.reduce((sum, segment) => sum + (segment.length_m ?? 0), 0) ||
      inputs.geometry.length_m ||
      0);
  const min = profile?.selected_window.minimum_required_pressure_bar;
  const max = profile?.selected_window.maximum_allowable_pressure_bar;
  const monitored = profile?.monitored_pressure_bar ?? inputs.field.monitored_pressure_bar;
  const pumpAtStart = !inputs.pump_location.includes("Bitis") && !inputs.pump_location.includes("Bitiş");
  const data = [
    { station: 0, label: "Başlangıç", monitored: monitored ?? null },
    { station: total * 0.5, label: "Orta", monitored: monitored ?? null },
    { station: total, label: "Bitiş", monitored: monitored ?? null },
  ];
  const yMax = Math.max(max ?? 0, monitored ?? 0, 120);
  const yDomainMax = Math.ceil((yMax * 1.08) / 20) * 20;

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 16, left: -18, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid-line)" vertical={false} />
          <XAxis
            dataKey="station"
            type="number"
            domain={[0, total || 1]}
            tickFormatter={(value: number) => `${num(value / 1000, 1)} km`}
            tick={{ fontSize: 10, fill: "var(--text-faint)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(value: number) => num(value, 0)}
            tick={{ fontSize: 10, fill: "var(--text-faint)" }}
            axisLine={false}
            tickLine={false}
            width={46}
            domain={[0, yDomainMax]}
          />
          <Tooltip
            content={
              <ChartTooltip
                labelFormatter={(label) => `İstasyon ${num(Number(label), 0)} m`}
                formatter={(value) => `${num(value, 2)} bar`}
              />
            }
          />
          {min !== undefined && max !== undefined ? (
            <ReferenceArea
              y1={min}
              y2={max}
              fill="var(--success)"
              fillOpacity={0.09}
              stroke="var(--success-border)"
              strokeWidth={0.5}
            />
          ) : null}
          {min !== undefined ? (
            <ReferenceLine
              y={min}
              stroke="var(--chart-3)"
              strokeDasharray="4 3"
              label={{ value: "min", position: "insideTopLeft", fill: "var(--chart-3)", fontSize: 10 }}
            />
          ) : null}
          {max !== undefined ? (
            <ReferenceLine
              y={max}
              stroke="var(--chart-4)"
              strokeDasharray="4 3"
              label={{ value: "max", position: "insideBottomLeft", fill: "var(--chart-4)", fontSize: 10 }}
            />
          ) : null}
          {monitored !== undefined && monitored !== null ? (
            <ReferenceLine
              y={monitored}
              stroke="var(--chart-1)"
              strokeWidth={1.6}
              label={{
                value: `izlenen ${num(monitored, 0)}`,
                position: "insideTopRight",
                fill: "var(--chart-1)",
                fontSize: 10,
              }}
            />
          ) : null}
          <Line
            type="monotone"
            dataKey="monitored"
            name="İzlenen basınç"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={{ r: 2 }}
            isAnimationActive={false}
          />
          <ReferenceDot
            x={pumpAtStart ? 0 : total}
            y={monitored ?? min ?? 0}
            r={5}
            fill="var(--warning)"
            stroke="var(--surface)"
            strokeWidth={2}
            ifOverflow="extendDomain"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 px-1 text-[10px] text-[var(--text-faint)]">
        Pompa: {PUMP_LABELS[inputs.pump_location] ?? inputs.pump_location ?? "—"} · yeşil bant kabul
        penceresi (min–max)
      </p>
    </div>
  );
}

export function UtilizationChart({
  results,
  height = 200,
  className,
}: {
  results: ResultBundle;
  height?: number;
  className?: string;
}) {
  const maxPressure = results.profile?.maximum_allowable_pressure_at_low_point_bar ?? 193.55;
  const pressure =
    results.profile?.monitored_pressure_bar ?? results.pressure?.actual_pressure_change_bar;
  const segments = results.geometry?.sections ?? [];
  const data = segments.map((segment, index) => {
    const utilization = pressure && maxPressure > 0 ? Math.min((pressure / maxPressure) * 100, 160) : 0;
    return {
      name: `Seg ${index + 1}`,
      utilization,
      label: `${num(segment.outside_diameter_mm, 1)} / ${num(segment.wall_thickness_mm, 2)} mm`,
    };
  });

  if (data.length === 0) {
    return (
      <div className={className} style={{ height }}>
        <div className="grid h-full place-items-center rounded-xl border border-dashed border-[var(--border)] text-[11.5px] text-[var(--text-faint)]">
          Segment verisi yok
        </div>
      </div>
    );
  }

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid-line)" horizontal={false} />
          <XAxis
            type="number"
            domain={[0, 130]}
            tickFormatter={(value: number) => `${value}%`}
            tick={{ fontSize: 9, fill: "var(--text-faint)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={44}
            tick={{ fontSize: 9.5, fill: "var(--text-faint)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={
              <ChartTooltip
                formatter={(value) => `${num(value, 1)}%`}
                labelFormatter={(label) => `Segment ${String(label).replace("Seg ", "")}`}
              />
            }
          />
          <ReferenceLine x={100} stroke="var(--danger)" strokeDasharray="3 3" />
          <Bar dataKey="utilization" name="Kullanım" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  entry.utilization > 100
                    ? "var(--danger)"
                    : entry.utilization > 85
                      ? "var(--warning)"
                      : "var(--success)"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({
  pressure,
  temperature,
  height = 180,
  className,
}: {
  pressure: number;
  temperature: number;
  height?: number;
  className?: string;
}) {
  const data = Array.from({ length: 13 }).map((_, index) => ({
    hour: `${String((index * 2) % 24).padStart(2, "0")}:00`,
    pressure: Number((pressure - 0.9 + Math.sin(index / 2) * 0.7 + index * 0.04).toFixed(3)),
    temperature: Number((temperature - 0.6 + Math.cos(index / 2.6) * 0.35).toFixed(2)),
  }));

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid-line)" vertical={false} />
          <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "var(--text-faint)" }} axisLine={false} tickLine={false} interval={2} />
          <YAxis yAxisId="left" tick={{ fontSize: 9, fill: "var(--text-faint)" }} axisLine={false} tickLine={false} width={44} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 9, fill: "var(--text-faint)" }} axisLine={false} tickLine={false} width={34} />
          <Tooltip content={<ChartTooltip formatter={(value) => num(value, 2)} />} />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="pressure"
            name="Basınç (bar)"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="temperature"
            name="Sıcaklık (°C)"
            stroke="var(--chart-3)"
            strokeWidth={1.6}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
