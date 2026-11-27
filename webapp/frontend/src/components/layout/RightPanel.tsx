import { useEffect, useRef } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDashed, FileText, Sigma, X } from "lucide-react";
import { geometryForInputs } from "../../lib/mock";
import { fmt, formatCoefficientState, num } from "../../lib/format";
import { BOTAS_FORM_BY_CODE, CHECK_DEFINITIONS } from "../../lib/constants";
import { useSessionForms } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import type { BotasFormCode } from "../../lib/types";
import { Badge, CoefficientBadge } from "../ui/Badge";
import { IconButton } from "../ui/Button";
import { ProgressBar } from "../ui/Gauge";

export function RightPanel() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const sessionId = useAppStore((state) => state.sessionId);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const rightDrawerOpen = useAppStore((state) => state.rightDrawerOpen);
  const setRightDrawerOpen = useAppStore((state) => state.setRightDrawerOpen);
  const setTab = useAppStore((state) => state.setTab);
  const openForm = useAppStore((state) => state.openForm);
  const drawerRef = useRef<HTMLDialogElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(min-width: 1536px)");
    const onMediaChange = () => {
      if (mq.matches) setRightDrawerOpen(false);
    };
    if (mq.matches && rightDrawerOpen) setRightDrawerOpen(false);
    mq.addEventListener("change", onMediaChange);
    return () => mq.removeEventListener("change", onMediaChange);
  }, [rightDrawerOpen, setRightDrawerOpen]);

  useEffect(() => {
    const dialog = drawerRef.current;
    if (!dialog) return;
    if (rightDrawerOpen) {
      previousFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
    } else if (typeof dialog.close === "function" && dialog.open) {
      dialog.close();
    }
  }, [rightDrawerOpen]);

  useEffect(() => {
    const dialog = drawerRef.current;
    if (!dialog) return;
    const onClose = () => {
      dialog.returnValue = "";
      setRightDrawerOpen(false);
      const prev = previousFocusRef.current;
      previousFocusRef.current = null;
      if (prev && prev.isConnected) {
        window.setTimeout(() => prev.focus(), 0);
      }
    };
    dialog.addEventListener("close", onClose);

    let cleanupFallback: (() => void) | undefined;
    if (typeof HTMLDialogElement !== "undefined" && !("closedBy" in HTMLDialogElement.prototype)) {
      let pressedOutside = false;
      const outside = (e: PointerEvent) => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      const onPointerDown = (e: PointerEvent) => {
        pressedOutside = e.target === dialog && outside(e);
      };
      const onPointerUp = (e: PointerEvent) => {
        if (pressedOutside && e.target === dialog && outside(e) && dialog.open) {
          dialog.close();
        }
        pressedOutside = false;
      };
      dialog.addEventListener("pointerdown", onPointerDown);
      dialog.addEventListener("pointerup", onPointerUp);
      cleanupFallback = () => {
        dialog.removeEventListener("pointerdown", onPointerDown);
        dialog.removeEventListener("pointerup", onPointerUp);
      };
    }

    return () => {
      dialog.removeEventListener("close", onClose);
      cleanupFallback?.();
    };
  }, [rightDrawerOpen, setRightDrawerOpen]);

  const { data: formsPayload } = useSessionForms(sessionId);
  const formsSummary = formsPayload?.summary;
  const firstMissingCode = formsPayload?.missing_required_forms?.[0]?.form_code as BotasFormCode | undefined;
  const issueCode = (formsSummary?.first_issue_form_code as BotasFormCode | undefined) || firstMissingCode || "test_data";

  const geometry = results.geometry ?? geometryForInputs(inputs);
  const checked = CHECK_DEFINITIONS.filter((check) => inputs.checks[check.key]).length;
  const airCoeff = results.coefficients?.airA;
  const pressureB = results.coefficients?.pressureB;

  const isMissingNumber = (value: number | null | undefined): boolean =>
    value === null || value === undefined || !Number.isFinite(value);

  const missing: string[] = [];
  if (!geometry) missing.push("Geometri: dış çap, et kalınlığı ve uzunluk gerekli.");
  if (isMissingNumber(inputs.air.actual_added_water_m3))
    missing.push("Hava: fiili ilave su (Vpa) girilmedi.");
  if (isMissingNumber(inputs.pressure.delta_t_c))
    missing.push("Basınç: ΔT girilmedi.");
  if (isMissingNumber(inputs.pressure.actual_pressure_change_bar))
    missing.push("Basınç: Pa girilmedi.");
  const hasAllSegmentSmys =
    inputs.segments.length > 0 &&
    inputs.segments.every(
      (s) => typeof s.smys_mpa === "number" && Number.isFinite(s.smys_mpa) && s.smys_mpa > 0,
    );
  if (isMissingNumber(inputs.section_profile.smys_mpa) && !hasAllSegmentSmys)
    missing.push("Profil: malzeme kalitesi / SMYS seçilmedi.");

  const formProgressTone = formsSummary?.failed_forms?.length
    ? "fail"
    : formsSummary?.complete
      ? "pass"
      : "info";

  const navigateTab = (nextTab: Parameters<typeof setTab>[0]) => {
    setTab(nextTab);
    setRightDrawerOpen(false);
  };

  const navigateForm = (code: BotasFormCode) => {
    openForm(code);
    setRightDrawerOpen(false);
  };

  const panelContent = (
    <div className="space-y-3">
      <div className="panel p-3.5">
        <div className="flex items-center justify-between">
          <p className="eyebrow">Canlı Özet</p>
          <span className="chip">{results.source === "live" ? "doğrulandı" : "ön hesap"}</span>
        </div>

        <div className="mt-3 space-y-2">
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2 text-left hover:border-[var(--border-strong)]"
            onClick={() => navigateTab("geometry")}
          >
            <span className="text-[11px] text-[var(--text-muted)]">Geometri</span>
            <span className="font-mono text-[11px] text-[var(--text-soft)]">
              {geometry ? `${geometry.section_count} kesit` : "—"}
            </span>
          </button>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <p className="text-[11px] uppercase tracking-wide text-[var(--text-faint)]">Uzunluk</p>
              <p className="mt-0.5 font-mono text-[12px]">{geometry ? fmt.m(geometry.total_length_m, 0) : "—"}</p>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <p className="text-[11px] uppercase tracking-wide text-[var(--text-faint)]">Hacim</p>
              <p className="mt-0.5 font-mono text-[12px]">{geometry ? fmt.m3Short(geometry.internal_volume_m3) : "—"}</p>
            </div>
          </div>
        </div>

        <div className="mt-3 border-t border-[var(--border)] pt-2.5">
          <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
            <Sigma size={11} aria-hidden /> Katsayılar
          </p>
          <div className="mt-1.5 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-[var(--text-muted)]">A · hava</span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono text-[11px]">{airCoeff ? num(airCoeff.a_micro_per_bar, 4) : "—"}</span>
                <CoefficientBadge state={airCoeff?.state ?? "empty"} />
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-[var(--text-muted)]">B · basınç</span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono text-[11px]">{pressureB ? num(pressureB.b_micro_per_c, 3) : "—"}</span>
                <CoefficientBadge state={pressureB ? "reference" : "empty"} />
              </span>
            </div>
          </div>
          <button
            type="button"
            className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-semibold text-[var(--primary)] hover:underline"
            onClick={() => navigateTab("coefficients")}
          >
            A/B hazırla <ArrowRight size={11} />
          </button>
        </div>

        <div className="mt-3 border-t border-[var(--border)] pt-2.5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
              <FileText size={11} aria-hidden /> BOTAŞ Form Dosyası
            </p>
            <span className="font-mono text-[11px] text-[var(--text-muted)]">
              {formsSummary?.filled_required ?? 0}/{formsSummary?.required_total ?? 11}
            </span>
          </div>
          <ProgressBar
            value={formsSummary?.filled_required ?? 0}
            max={formsSummary?.required_total ?? 11}
            tone={formProgressTone}
            className="mt-1.5"
          />
          <button
            type="button"
            className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-semibold text-[var(--primary)] hover:underline"
            onClick={() => navigateForm(issueCode)}
          >
            {formsSummary?.first_issue_form_code
              ? `Bulgulu form (${BOTAS_FORM_BY_CODE[formsSummary.first_issue_form_code as BotasFormCode]?.shortCode ?? "—"})`
              : firstMissingCode
                ? `Sıradaki eksik (${BOTAS_FORM_BY_CODE[firstMissingCode]?.shortCode ?? "—"})`
                : "Form dosyasını aç"}{" "}
            <ArrowRight size={11} />
          </button>
        </div>

        <div className="mt-3 border-t border-[var(--border)] pt-2.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
              Saha kontrolü
            </p>
            <span className="font-mono text-[11px] text-[var(--text-muted)]">
              {checked}/{CHECK_DEFINITIONS.length}
            </span>
          </div>
          <ProgressBar value={checked} max={CHECK_DEFINITIONS.length} tone={checked === 11 ? "pass" : "info"} className="mt-1.5" />
          <button
            type="button"
            className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-semibold text-[var(--primary)] hover:underline"
            onClick={() => navigateTab("geometry")}
          >
            Checklist’i aç <ArrowRight size={11} />
          </button>
        </div>
      </div>

      <div className="panel p-3.5">
        <p className="eyebrow">Uyarılar</p>
        {missing.length === 0 ? (
          <div className="mt-2 flex items-start gap-2 text-[11px] text-[var(--text-muted)]">
            <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
            Zorunlu alanlar tamam görünüyor. Değerlendirme yapmadan önce birimleri kontrol edin.
          </div>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {missing.slice(0, 4).map((item) => (
              <li key={item} className="flex items-start gap-1.5 text-[11px] leading-snug text-[var(--text-muted)]">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 tone-warning" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel-soft p-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
          <CircleDashed size={11} aria-hidden /> Sıradaki adım
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
          {!geometry
            ? "Geometriyi tamamlayın."
            : inputs.pressure.b_micro_per_c === null
              ? "B katsayısını hazırlayın."
              : !results.air
                ? "Hava içerik testini değerlendirin."
                : !results.pressure
                  ? "Basınç değişim testini değerlendirin."
                  : "Raporu önizleyip dışa aktarın."}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Badge tone={inputs.material_grade || hasAllSegmentSmys ? "pass" : "warning"}>
            {inputs.material_grade || hasAllSegmentSmys ? "Malzeme seçili" : "Malzeme eksik"}
          </Badge>
          <Badge tone={formatCoefficientState(airCoeff?.state) === "BEKLİYOR" ? "pending" : "pass"}>
            A {formatCoefficientState(airCoeff?.state)}
          </Badge>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {rightPanelOpen ? (
        <aside className="hidden w-[292px] shrink-0 2xl:block">
          <div className="sticky top-[92px] max-h-[calc(100dvh-108px)] overflow-y-auto pb-6 pr-0.5 scroll-thin">
            {panelContent}
          </div>
        </aside>
      ) : null}

      {rightDrawerOpen ? (
        <dialog
          ref={drawerRef}
          aria-label="Canlı özet paneli"
          {...({ closedby: "any" } as Record<string, unknown>)}
          className="drawer-dialog-right drawer-dialog-narrow 2xl:hidden"
        >
          <div className="flex h-full flex-col bg-[var(--canvas)]">
            <header className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-soft)]">
                Canlı Özet
              </span>
              <IconButton
                label="Canlı özet panelini kapat"
                onClick={() => {
                  if (typeof drawerRef.current?.close === "function" && drawerRef.current.open) {
                    drawerRef.current.close();
                  } else {
                    setRightDrawerOpen(false);
                  }
                }}
              >
                <X size={16} aria-hidden />
              </IconButton>
            </header>
            <div className="flex-1 overflow-y-auto p-3.5 scroll-thin">{panelContent}</div>
          </div>
        </dialog>
      ) : null}
    </>
  );
}
