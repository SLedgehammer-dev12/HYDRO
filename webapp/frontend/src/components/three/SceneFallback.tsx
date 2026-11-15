import { useMemo } from "react";
import type { SceneData } from "../../lib/scene";
import { formatDistance, formatPressure, numberFormat0 } from "./sceneModel";

interface SceneFallbackProps {
  scene: SceneData;
  message: string;
}

/**
 * Equivalent 2D elevation profile for devices without WebGL (and as an error
 * fallback). It is deliberately dependency-free so it always renders.
 */
export default function SceneFallback({ scene, message }: SceneFallbackProps) {
  const paths = useMemo(() => {
    const segments = scene.segments;
    if (segments.length === 0) return [];
    const maxDistance = Math.max(...segments.map((segment) => segment.end_m), 1);
    const elevations = segments.flatMap((segment) => [
      segment.start_elevation_m,
      segment.end_elevation_m,
    ]);
    const minElevation = Math.min(...elevations);
    const maxElevation = Math.max(...elevations);
    const range = Math.max(1, maxElevation - minElevation);
    const x = (distance: number) => 54 + (distance / maxDistance) * 700;
    const y = (elevation: number) => 250 - ((elevation - minElevation) / range) * 190;
    return segments.map((segment) => ({
      id: segment.id,
      d: `M ${x(segment.start_m).toFixed(1)} ${y(segment.start_elevation_m).toFixed(
        1,
      )} L ${x(segment.end_m).toFixed(1)} ${y(segment.end_elevation_m).toFixed(1)}`,
      label: segment.label,
      color:
        segment.status === "fail"
          ? "#fb7185"
          : segment.status === "warning"
            ? "#f5b544"
            : "#34d399",
      start: segment.start_m,
    }));
  }, [scene.segments]);

  const maxDistance = Math.max(...scene.segments.map((segment) => segment.end_m), 0);
  const elevations = scene.segments.flatMap((segment) => [
    segment.start_elevation_m,
    segment.end_elevation_m,
  ]);
  const minElevation = elevations.length ? Math.min(...elevations) : 0;
  const maxElevation = elevations.length ? Math.max(...elevations) : 0;

  return (
    <div className="flex h-full w-full flex-col justify-center gap-3 bg-ink-950 p-6">
      <div role="img" aria-label={`Boru hattı kot profili: ${formatDistance(0)} – ${formatDistance(maxDistance)}`}>
        <svg viewBox="0 0 800 300" className="h-auto w-full" aria-hidden="true">
          {[0, 1, 2, 3].map((line) => (
            <line
              key={line}
              x1="54"
              x2="754"
              y1={70 + line * 60}
              y2={70 + line * 60}
              stroke="#1c2b42"
              strokeWidth="1"
            />
          ))}
          <line x1="54" y1="252" x2="754" y2="252" stroke="#2b425f" strokeWidth="1.5" />
          {paths.map((item) => (
            <path
              key={item.id}
              d={item.d}
              fill="none"
              stroke={item.color}
              strokeWidth="6"
              strokeLinecap="round"
            />
          ))}
          <text x="54" y="278" fill="#6b809c" fontSize="12" fontFamily="ui-monospace, monospace">
            {numberFormat0.format(minElevation)} m
          </text>
          <text x="754" y="278" fill="#6b809c" fontSize="12" textAnchor="end" fontFamily="ui-monospace, monospace">
            {numberFormat0.format(maxElevation)} m
          </text>
          <text x="54" y="36" fill="#8fa3bd" fontSize="12">
            {formatDistance(0)}
          </text>
          <text x="754" y="36" fill="#8fa3bd" fontSize="12" textAnchor="end">
            {formatDistance(maxDistance)}
          </text>
          {paths.map((item) => (
            <text
              key={`${item.id}-label`}
              x={54 + (item.start / Math.max(1, maxDistance)) * 700}
              y="60"
              fill="#6b809c"
              fontSize="11"
            >
              {item.label.split(" · ")[0]}
            </text>
          ))}
        </svg>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-mist-500">
        <span>
          {scene.segments.length} segment · {formatDistance(maxDistance)} hat
          {scene.segments[0]?.pressure_bar != null
            ? ` · ${formatPressure(scene.segments[0].pressure_bar)} izlenen basınç`
            : ""}
        </span>
        <span className="rounded border border-amber/40 bg-amber/10 px-2 py-1 text-amber">
          {message}
        </span>
      </div>
    </div>
  );
}
