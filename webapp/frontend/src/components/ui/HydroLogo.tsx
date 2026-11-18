import { useId } from "react";

export function HydroLogo({
  size = 36,
  decorative = true,
  className = "",
}: {
  size?: number;
  decorative?: boolean;
  className?: string;
}) {
  const uid = useId().replace(/:/g, "");
  const bgId = `${uid}-bg`;
  const flangeId = `${uid}-flange`;
  const waterId = `${uid}-water`;
  const boreId = `${uid}-bore`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      aria-hidden={decorative ? "true" : undefined}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "HYDRO Hidrostatik Test Platformu"}
    >
      <defs>
        <linearGradient id={bgId} x1="8" y1="6" x2="56" y2="58" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#131d33" />
          <stop offset="100%" stopColor="#070b14" />
        </linearGradient>
        <linearGradient id={flangeId} x1="12" y1="14" x2="48" y2="52" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#64748b" />
          <stop offset="50%" stopColor="#334155" />
          <stop offset="100%" stopColor="#1e293b" />
        </linearGradient>
        <linearGradient id={waterId} x1="28" y1="30" x2="28" y2="49" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
        <clipPath id={boreId}>
          <circle cx="29" cy="35" r="13.5" />
        </clipPath>
      </defs>

      <rect
        x="2"
        y="2"
        width="60"
        height="60"
        rx="14"
        fill={`url(#${bgId})`}
        stroke="#22d3ee"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <circle cx="29" cy="35" r="20.5" fill={`url(#${flangeId})`} stroke="#94a3b8" strokeWidth="1.4" />
      <circle cx="29" cy="35" r="16" fill="#0f172a" stroke="#475569" strokeWidth="1.2" />
      <circle cx="29" cy="35" r="13.5" fill="#070b14" />

      <circle cx="29" cy="16.8" r="1.35" fill="#cbd5e1" />
      <circle cx="44.8" cy="25.9" r="1.35" fill="#cbd5e1" />
      <circle cx="44.8" cy="44.1" r="1.35" fill="#cbd5e1" />
      <circle cx="29" cy="53.2" r="1.35" fill="#cbd5e1" />
      <circle cx="13.2" cy="44.1" r="1.35" fill="#cbd5e1" />
      <circle cx="13.2" cy="25.9" r="1.35" fill="#cbd5e1" />

      <g clipPath={`url(#${boreId})`}>
        <path d="M14 33.5 Q21.5 30 29 33.5 T44 33.5 V52 H14 Z" fill={`url(#${waterId})`} />
        <path d="M14 33.5 Q21.5 30 29 33.5 T44 33.5" stroke="#a5f3fc" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="24" cy="41.5" r="1.4" fill="#cffafe" fillOpacity="0.7" />
        <circle cx="33.5" cy="39" r="1.0" fill="#cffafe" fillOpacity="0.6" />
      </g>
      <circle cx="29" cy="35" r="13.5" stroke="#22d3ee" strokeOpacity="0.55" strokeWidth="1" />

      <circle cx="46.5" cy="18.5" r="11.5" fill="#0f172a" stroke="#e2e8f0" strokeWidth="1.8" />
      <circle cx="46.5" cy="18.5" r="9.2" fill="#070b14" />
      <path d="M39.8 22.8 A8 8 0 1 1 53.2 22.8" stroke="#475569" strokeWidth="2" strokeLinecap="round" />
      <path d="M47.8 10.6 A8 8 0 0 1 54.1 20.5" stroke="#34d399" strokeWidth="2.3" strokeLinecap="round" />
      <line x1="46.5" y1="18.5" x2="51.8" y2="14.2" stroke="#f8fafc" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="46.5" cy="18.5" r="1.9" fill="#22d3ee" />
    </svg>
  );
}
