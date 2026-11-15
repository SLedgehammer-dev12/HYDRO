import { cn } from "../../lib/utils";
import { num } from "../../lib/format";

export function RatioGauge({
  ratio,
  limit = 1.06,
  passed,
  title = "Vpa / Vp",
  valueLabel,
  thresholdLabel,
  className,
}: {
  ratio: number | null | undefined;
  limit?: number;
  passed?: boolean;
  title?: string;
  valueLabel?: string;
  thresholdLabel?: string;
  className?: string;
}) {
  const safeRatio = typeof ratio === "number" && Number.isFinite(ratio) ? Math.max(0, ratio) : 0;
  const max = limit * 1.15;
  const fraction = Math.min(safeRatio / max, 1);
  const thresholdFraction = limit / max;
  const arcLength = Math.PI * 80;
  const positive = passed ?? (safeRatio < limit);

  const angle = Math.PI * (1 - thresholdFraction);
  const tickX = 100 + 80 * Math.cos(angle);
  const tickY = 100 - 80 * Math.sin(angle);
  const tickX2 = 100 + 92 * Math.cos(angle);
  const tickY2 = 100 - 92 * Math.sin(angle);

  return (
    <div className={cn("relative", className)}>
      <svg viewBox="0 0 200 118" className="w-full" role="img" aria-label={`${title}: ${num(safeRatio, 6)}`}>
        <defs>
          <linearGradient id="ratio-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--chart-1)" />
            <stop offset="75%" stopColor="var(--chart-2)" />
            <stop offset="100%" stopColor={positive ? "var(--success)" : "var(--danger)"} />
          </linearGradient>
        </defs>
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth="13"
          strokeLinecap="round"
        />
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke={!positive ? "var(--danger)" : "url(#ratio-gradient)"}
          strokeWidth="13"
          strokeLinecap="round"
          strokeDasharray={`${Math.max(fraction * arcLength, 0.01)} ${arcLength}`}
        />
        <line
          x1={tickX}
          y1={tickY}
          x2={tickX2}
          y2={tickY2}
          stroke="var(--warning)"
          strokeWidth="2"
          strokeDasharray="3 2"
        />
        <circle cx={20} cy={100} r="2.5" fill="var(--text-faint)" />
        <circle cx={180} cy={100} r="2.5" fill="var(--text-faint)" />
        <text x="100" y="72" textAnchor="middle" className="fill-[var(--text)]" style={{ fontSize: 23, fontWeight: 600, fontFamily: "var(--font-mono)" }}>
          {num(safeRatio, 6)}
        </text>
        <text x="100" y="89" textAnchor="middle" className="fill-[var(--text-faint)]" style={{ fontSize: 9.5, letterSpacing: "0.08em" }}>
          {title}
        </text>
        <text x="22" y="114" className="fill-[var(--text-faint)]" style={{ fontSize: 9 }}>
          0
        </text>
        <text x="178" y="114" textAnchor="end" className="fill-[var(--text-faint)]" style={{ fontSize: 9 }}>
          {num(max, 2)}
        </text>
      </svg>
      <div className="-mt-1 flex items-center justify-between px-1 text-[10.5px]">
        <span className="text-[var(--text-faint)]">{valueLabel ?? "Fiili / teorik"}</span>
        <span className="font-mono text-[var(--warning)]">{thresholdLabel ?? `kabul ${num(limit, 2)}`}</span>
      </div>
    </div>
  );
}

export function MarginGauge({
  margin,
  tolerance = 0.3,
  passed,
  unit = "bar",
  className,
}: {
  margin: number | null | undefined;
  tolerance?: number;
  passed?: boolean;
  unit?: string;
  className?: string;
}) {
  const value = typeof margin === "number" && Number.isFinite(margin) ? margin : 0;
  const min = -0.4;
  const max = 0.6;
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const fraction = (clamp(value) - min) / (max - min);
  const toleranceFraction = (tolerance - min) / (max - min);
  const zeroFraction = (0 - min) / (max - min);
  const positive = passed ?? value <= tolerance;

  return (
    <div className={className}>
      <div className="relative h-8 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-2)]">
        <div
          className="absolute inset-y-0 left-0 bg-[var(--success-bg)]"
          style={{ width: `${toleranceFraction * 100}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 right-0 bg-[var(--danger-bg)]"
          style={{ left: `${toleranceFraction * 100}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 w-px bg-[var(--text-faint)]"
          style={{ left: `${zeroFraction * 100}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-[var(--warning)]"
          style={{ left: `${toleranceFraction * 100}%` }}
          title={`Kabul sınırı ${tolerance} ${unit}`}
          aria-hidden
        />
        <div
          className={cn(
            "absolute top-1/2 h-5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full",
            positive ? "bg-[var(--success)]" : "bg-[var(--danger)]",
          )}
          style={{ left: `${fraction * 100}%` }}
          aria-hidden
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9.5px] text-[var(--text-faint)]">
        <span>-0,4</span>
        <span className="text-[var(--warning)]">+{num(tolerance, 2)} {unit}</span>
        <span>+0,6</span>
      </div>
      <p className={cn("mt-1.5 text-[11px] font-semibold", positive ? "tone-pass" : "tone-fail")}>
        Marj {num(value, 3)} {unit} · {positive ? "kabul sınırı içinde" : "kabul sınırı dışında"}
      </p>
    </div>
  );
}

export function ProgressBar({
  value,
  max,
  tone = "info",
  className,
}: {
  value: number;
  max: number;
  tone?: "pass" | "info" | "warning" | "fail";
  className?: string;
}) {
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div
      className={cn("h-2 overflow-hidden rounded-full bg-[var(--surface-3)]", className)}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500",
          tone === "pass" && "bg-[var(--success)]",
          tone === "info" && "bg-[var(--primary)]",
          tone === "warning" && "bg-[var(--warning)]",
          tone === "fail" && "bg-[var(--danger)]",
        )}
        style={{ width: `${ratio * 100}%` }}
      />
    </div>
  );
}
