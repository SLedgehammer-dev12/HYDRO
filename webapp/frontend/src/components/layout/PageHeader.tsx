import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export function PageHeader({
  kicker,
  title,
  description,
  actions,
  meta,
  className,
}: {
  kicker?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        {kicker ? (
          <p className="eyebrow flex items-center gap-2">
            <span className="h-px w-6 bg-[var(--primary)]" aria-hidden />
            {kicker}
          </p>
        ) : null}
        <h1 className="mt-1 text-[22px] font-bold leading-[1.15] tracking-[-0.025em] text-[var(--text)] text-balance sm:text-[26px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-1 max-w-[68ch] text-[12.5px] leading-relaxed text-[var(--text-muted)]">{description}</p>
        ) : null}
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div> : null}
      </div>
      {actions ? (
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2.5">{actions}</div>
      ) : null}
    </div>
  );
}
