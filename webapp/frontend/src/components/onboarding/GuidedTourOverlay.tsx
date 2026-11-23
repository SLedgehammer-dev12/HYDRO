import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Compass, Trash2, X } from "lucide-react";
import { api, apiErrorMessage } from "../../lib/api";
import { useAppStore } from "../../store/useAppStore";
import { Button } from "../ui/Button";
import { GUIDED_TOUR_STEPS } from "./tourSteps";

export function GuidedTourOverlay() {
  const tourActive = useAppStore((state) => state.tourActive);
  const tourStep = useAppStore((state) => state.tourStep);
  const tourSampleProjectId = useAppStore((state) => state.tourSampleProjectId);
  const setTab = useAppStore((state) => state.setTab);
  const setTourStep = useAppStore((state) => state.setTourStep);
  const endTour = useAppStore((state) => state.endTour);
  const resetSession = useAppStore((state) => state.resetSession);
  const pushToast = useAppStore((state) => state.pushToast);

  const queryClient = useQueryClient();
  const popoverRef = useRef<HTMLDialogElement>(null);
  const primaryActionRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [cleaningSample, setCleaningSample] = useState(false);

  const clampedIndex = Math.max(0, Math.min(tourStep, GUIDED_TOUR_STEPS.length - 1));
  const step = GUIDED_TOUR_STEPS[clampedIndex];
  const isFirst = clampedIndex === 0;
  const isLast = clampedIndex === GUIDED_TOUR_STEPS.length - 1;

  const closeAndReturnFocus = useCallback(() => {
    const el = popoverRef.current;
    if (el) {
      if ("hidePopover" in el && typeof el.hidePopover === "function") {
        try {
          if (el.matches(":popover-open")) el.hidePopover();
        } catch {
          el.removeAttribute("open");
        }
      } else {
        el.removeAttribute("open");
      }
    }
    endTour();
    const target = returnFocusRef.current;
    if (target && typeof target.focus === "function") {
      target.focus();
    }
  }, [endTour]);

  /* Adım değiştiğinde ilgili sekmeye geç ve hedef öğeyi CSS anchor + vurgu ile işaretle */
  useEffect(() => {
    if (!tourActive) return;
    setTab(step.tab);

    const anchorTarget = document.querySelector(step.targetSelector) as HTMLElement | null;
    if (anchorTarget) {
      anchorTarget.classList.add("tour-highlight-target");
      anchorTarget.style.setProperty("anchor-name", "--hydro-tour-anchor");
    }

    return () => {
      if (anchorTarget) {
        anchorTarget.classList.remove("tour-highlight-target");
        anchorTarget.style.removeProperty("anchor-name");
      }
    };
  }, [tourActive, step, setTab]);

  /* Popover açma ve odak yönlendirme (modern-web-guidance: popover="manual") */
  useEffect(() => {
    const el = popoverRef.current;
    if (!tourActive || !el) return;

    if (!returnFocusRef.current && document.activeElement instanceof HTMLElement) {
      returnFocusRef.current = document.activeElement;
    }

    if ("showPopover" in el && typeof el.showPopover === "function") {
      try {
        if (!el.matches(":popover-open")) {
          el.showPopover();
        }
      } catch {
        el.setAttribute("open", "");
      }
    } else {
      el.setAttribute("open", "");
    }

    const focusTimer = window.setTimeout(() => {
      primaryActionRef.current?.focus();
    }, 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAndReturnFocus();
      }
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [tourActive, clampedIndex, closeAndReturnFocus]);

  async function handleFinishAndDeleteSample() {
    if (!tourSampleProjectId) {
      closeAndReturnFocus();
      return;
    }
    setCleaningSample(true);
    try {
      await api.deleteProject(tourSampleProjectId);
      resetSession("Yeni Test Bölümü");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      pushToast("success", "Demo projesi temizlendi", "Kendi projenizle çalışmaya başlayabilirsiniz.");
      closeAndReturnFocus();
      setTab("projects");
    } catch (error) {
      pushToast("error", "Demo projesi silinemedi", apiErrorMessage(error));
    } finally {
      setCleaningSample(false);
    }
  }

  if (!tourActive) return null;

  return (
    <dialog
      ref={popoverRef}
      {...({ popover: "manual" } as Record<string, unknown>)}
      aria-labelledby="hydro-tour-title"
      className="hydro-tour-popover"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.14em] text-[var(--primary)]">
          <Compass size={13} aria-hidden />
          <span>Rehberli Demo Turu</span>
        </div>
        <button
          type="button"
          onClick={closeAndReturnFocus}
          className="rounded-md p-1 text-[var(--text-faint)] hover:bg-[var(--surface-3)] hover:text-[var(--text)]"
          aria-label="Rehberli turu kapat"
        >
          <X size={14} aria-hidden />
        </button>
      </div>

      <h3 id="hydro-tour-title" className="mt-1.5 text-sm font-bold text-[var(--text)]">
        {step.title}
      </h3>
      <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-soft)]">{step.description}</p>
      <p className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-[11px] text-[var(--text-muted)]">
        {step.hint}
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)] pt-2.5">
        <div className="flex items-center gap-1.5">
          {!isFirst ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<ArrowLeft size={12} />}
              onClick={() => setTourStep(clampedIndex - 1)}
            >
              Geri
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={closeAndReturnFocus}>
              Kapat
            </Button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {!isLast ? (
            <Button
              ref={primaryActionRef}
              size="sm"
              variant="primary"
              onClick={() => setTourStep(clampedIndex + 1)}
            >
              İleri ({clampedIndex + 2}/{GUIDED_TOUR_STEPS.length})
              <ArrowRight size={12} aria-hidden />
            </Button>
          ) : (
            <>
              {tourSampleProjectId ? (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={12} />}
                  loading={cleaningSample}
                  onClick={() => void handleFinishAndDeleteSample()}
                >
                  Örnek projeyi temizle ve bitir
                </Button>
              ) : null}
              <Button
                ref={primaryActionRef}
                size="sm"
                variant="primary"
                icon={<Check size={12} />}
                onClick={closeAndReturnFocus}
              >
                {tourSampleProjectId ? "Örnek projeyi tut ve bitir" : "Turu Bitir"}
              </Button>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}
