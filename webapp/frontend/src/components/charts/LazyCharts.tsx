import { Suspense, lazy, type ComponentProps } from "react";
import type * as ChartsModule from "./Charts";

const LazyElevationProfileChart = lazy(() =>
  import("./Charts").then((m) => ({ default: m.ElevationProfileChart })),
);
const LazyPressureWindowChart = lazy(() =>
  import("./Charts").then((m) => ({ default: m.PressureWindowChart })),
);
const LazyUtilizationChart = lazy(() =>
  import("./Charts").then((m) => ({ default: m.UtilizationChart })),
);
const LazyTrendChart = lazy(() =>
  import("./Charts").then((m) => ({ default: m.TrendChart })),
);

function ChartSkeleton({ height, className }: { height: number; className?: string }) {
  return (
    <div className={className} style={{ height }} aria-busy="true" aria-label="Grafik yükleniyor">
      <div className="h-full w-full rounded-xl border border-[var(--border)] bg-[var(--surface-2)]/60 animate-pulse" />
    </div>
  );
}

/** Lazy-loaded wrapper around ElevationProfileChart keeping Recharts out of the initial chunk. */
export function ElevationProfileChart(
  props: ComponentProps<typeof ChartsModule.ElevationProfileChart>,
) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 220} className={props.className} />}>
      <LazyElevationProfileChart {...props} />
    </Suspense>
  );
}

/** Lazy-loaded wrapper around PressureWindowChart keeping Recharts out of the initial chunk. */
export function PressureWindowChart(
  props: ComponentProps<typeof ChartsModule.PressureWindowChart>,
) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 230} className={props.className} />}>
      <LazyPressureWindowChart {...props} />
    </Suspense>
  );
}

/** Lazy-loaded wrapper around UtilizationChart keeping Recharts out of the initial chunk. */
export function UtilizationChart(
  props: ComponentProps<typeof ChartsModule.UtilizationChart>,
) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 200} className={props.className} />}>
      <LazyUtilizationChart {...props} />
    </Suspense>
  );
}

/** Lazy-loaded wrapper around TrendChart keeping Recharts out of the initial chunk. */
export function TrendChart(props: ComponentProps<typeof ChartsModule.TrendChart>) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 180} className={props.className} />}>
      <LazyTrendChart {...props} />
    </Suspense>
  );
}
