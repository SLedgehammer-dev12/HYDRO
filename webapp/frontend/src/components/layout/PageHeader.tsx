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
    <div className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {kicker ? (
          <p className="eyebrow flex items-center gap-2">
            <span className="h-px w-6 bg-[var(--primary)]" aria-hidden />
            {kicker}
          </p>
        ) : null}
        <h1 className="mt-1.5 text-[28px] font-bold leading-[1.12] tracking-[-0.03em] text-[var(--text)] text-balance sm:text-[34px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-[74ch] text-[13.5px] leading-relaxed text-[var(--text-soft)] sm:text-[14px]">{description}</p>
        ) : null}
        {meta ? <div className="mt-2.5 flex flex-wrap items-center gap-2">{meta}</div> : null}
      </div>
      {actions ? (
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2.5">{actions}</div>
      ) : null}
    </div>
  );
}
