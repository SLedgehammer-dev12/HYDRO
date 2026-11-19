import { useEffect, useId, useMemo, useRef, useState } from "react";
import { CellInput } from "../features/forms/FormTablePrimitives";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Calculator,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FilePlus2,
  FileScan,
  FolderKanban,
  Info,
  Save,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import { BOTAS_FORM_BY_CODE, BOTAS_FORM_NAV_ITEMS } from "../lib/constants";
import { dateTime, num } from "../lib/format";
import type { BotasFormCode, FormFinding, SectionFormRecord } from "../lib/types";
import {
  useScanSessionForm,
  useSessionForms,
  useUpdateSessionForm,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { FormBodyEditor } from "../features/forms/FormBodyEditor";
import { AirPage } from "./AirPage";
import { PressurePage } from "./PressurePage";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { SectionCard } from "../components/ui/Card";
import { Modal } from "../components/ui/Dialog";
import { InlineNotice } from "../components/ui/State";

function statusMeta(status: SectionFormRecord["status"] | string) {
  if (status === "passed") return { tone: "pass" as const, label: "Uygun" };
  if (status === "failed") return { tone: "fail" as const, label: "Hatalı / Bulgu" };
  if (status === "warning") return { tone: "warning" as const, label: "İnceleme / Uyarı" };
  if (status === "filled") return { tone: "info" as const, label: "Dolduruldu" };
  return { tone: "neutral" as const, label: "Boş" };
}

function findingTone(status: FormFinding["status"]) {
  if (status === "passed") return "pass" as const;
  if (status === "failed") return "fail" as const;
  if (status === "warning") return "warning" as const;
  return "info" as const;
}

function findingLabel(status: FormFinding["status"]) {
  if (status === "passed") return "Uygun";
  if (status === "failed") return "Uygun Değil";
  if (status === "warning") return "Uyarı";
  return "Bilgi";
}

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function asStr(obj: Record<string, unknown>, key: string): string {
  const val = obj[key];
  return val === null || val === undefined ? "" : String(val);
}

function parseMaybeNum(raw: string): number | null {
  const t = raw.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function SectionFormPage() {
  const sessionId = useAppStore((state) => state.sessionId);
  const sessionName = useAppStore((state) => state.sessionName);
  const projectName = useAppStore((state) => state.projectName);
  const backend = useAppStore((state) => state.backend);
  const activeFormCode = useAppStore((state) => state.activeFormCode);
  const openForm = useAppStore((state) => state.openForm);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const formsQuery = useSessionForms(sessionId);
  const updateForm = useUpdateSessionForm();
  const scanForm = useScanSessionForm();

  const spec = BOTAS_FORM_BY_CODE[activeFormCode] ?? BOTAS_FORM_NAV_ITEMS[0];
  const currentIndex = BOTAS_FORM_NAV_ITEMS.findIndex((i) => i.code === spec.code);
  const prevSpec = BOTAS_FORM_NAV_ITEMS[(currentIndex - 1 + BOTAS_FORM_NAV_ITEMS.length) % BOTAS_FORM_NAV_ITEMS.length];
  const nextSpec = BOTAS_FORM_NAV_ITEMS[(currentIndex + 1) % BOTAS_FORM_NAV_ITEMS.length];

  const payload = formsQuery.data;
  const formRecord = useMemo(
    () => payload?.forms.find((f) => f.form_code === spec.code) ?? null,
    [payload, spec.code],
  );
  const mergedHeader = useMemo(() => asObj(payload?.merged_header), [payload]);
  const calculations = useMemo(() => asObj(payload?.calculations) as Record<string, Record<string, unknown>>, [payload]);

  const [draftDate, setDraftDate] = useState("");
  const [draftData, setDraftData] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);
  const [showDetailCalc, setShowDetailCalc] = useState(false);
  const [pendingNavCode, setPendingNavCode] = useState<BotasFormCode | null>(null);

  const uploadInputId = useId();
  const appendUploadInputId = useId();

  function requestNavigate(nextCode: BotasFormCode) {
    if (nextCode === spec.code) return;
    if (dirty && !isDemoOrOffline) {
      setPendingNavCode(nextCode);
      return;
    }
    openForm(nextCode);
  }

  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const loadedTargetRef = useRef<string | null>(null);
  const saveHandlerRef = useRef<() => void>(() => {});

  useEffect(() => {
    saveHandlerRef.current = () => handleSave();
  });

  useEffect(() => {
    function onGlobalSave() {
      saveHandlerRef.current();
    }
    window.addEventListener("hydro:save", onGlobalSave);
    return () => window.removeEventListener("hydro:save", onGlobalSave);
  }, []);

  /* Form veya kesit değişince sunucudaki güncel veriyi forma yükle */
  useEffect(() => {
    const targetKey = `${sessionId}::${spec.code}`;
    const contextChanged = loadedTargetRef.current !== targetKey;
    if (!contextChanged && dirtyRef.current) {
      return;
    }
    loadedTargetRef.current = targetKey;
    const ext = formRecord?.extracted_data ? structuredClone(formRecord.extracted_data) : {};
    setDraftDate(formRecord?.form_date || "");
    setDraftData(ext);
    setDirty(false);
    if (contextChanged) {
      setShowDetailCalc(false);
      setPendingNavCode(null);
    }
  }, [sessionId, spec.code, formRecord?.revision, formRecord?.updated_at]);

  /* Alt + Sol/Sağ Ok ile formlar arasında hızlı geçiş */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) {
        return;
      }
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        if (dirty) setPendingNavCode(prevSpec.code);
        else openForm(prevSpec.code);
      } else if (e.altKey && e.key === "ArrowRight") {
        e.preventDefault();
        if (dirty) setPendingNavCode(nextSpec.code);
        else openForm(nextSpec.code);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openForm, prevSpec.code, nextSpec.code, dirty]);

  const issueForms = useMemo(
    () => (payload?.forms ?? []).filter((f) => f.form_code !== spec.code && (f.status === "failed" || f.status === "warning")),
    [payload, spec.code],
  );
  const nextIssueForm = useMemo(() => {
    if (issueForms.length === 0) return null;
    const after = issueForms.find((f) => (f.order ?? 99) > spec.order);
    return after ?? issueForms[0];
  }, [issueForms, spec.order]);

  const hdr = asObj(draftData.header);
  const sig = asObj(draftData.signatures);
  const findings = formRecord?.findings ?? [];
  const relatedCheckpoints = (payload?.checkpoints ?? []).filter((cp) =>
    cp.source_forms.includes(spec.code),
  );
  const stMeta = statusMeta(formRecord?.status ?? "empty");
  const isDemoOrOffline = backend !== "online" || !sessionId || sessionId.startsWith("demo-");

  function setHeaderField(key: string, value: unknown) {
    setDraftData((prev) => ({
      ...prev,
      header: { ...asObj(prev.header), [key]: value },
    }));
    setDirty(true);
  }

  function applySectionHeaderToForm() {
    setDraftData((prev) => {
      const cur = asObj(prev.header);
      const next = { ...cur };
      for (const k of [
        "section_no",
        "start_kp",
        "end_kp",
        "length_m",
        "section_volume_m3",
        "outside_diameter_mm",
        "inside_diameter_mm",
        "wall_thickness_mm",
        "design_pressure_bar",
        "test_pressure_bar",
        "smys_mpa",
        "pump_location",
      ]) {
        if ((next[k] === undefined || next[k] === null || next[k] === "") && mergedHeader[k] !== undefined && mergedHeader[k] !== null) {
          next[k] = mergedHeader[k];
        }
      }
      return { ...prev, header: next };
    });
    setDirty(true);
  }

  function handleSave(onSaved?: () => void) {
    if (isDemoOrOffline) {
      pushToast("warning", "Sunucu veya aktif kesit yok", "Formu veritabanına kaydetmek için Projeler & Kesitler ekranından bir kesit seçin.");
      return;
    }
    updateForm.mutate(
      {
        sessionId: sessionId!,
        formCode: spec.code,
        payload: {
          form_date: draftDate,
          extracted_data: draftData,
          overwrite_session_inputs: true,
        },
      },
      {
        onSuccess: () => {
          setDirty(false);
          onSaved?.();
        },
      },
    );
  }

  async function handleUploadFormFiles(
    fileList: FileList | null,
    mode: "replace" | "append" = "replace",
  ) {
    const files = Array.from(fileList ?? []);
    if (files.length === 0) return;
    if (isDemoOrOffline) {
      pushToast("warning", "Aktif kesit seçili değil", "Önce Projeler & Kesitler sayfasından bir proje kesiti açın.");
      return;
    }
    if (mode === "append" && dirty) {
      try {
        await updateForm.mutateAsync({
          sessionId: sessionId!,
          formCode: spec.code,
          payload: {
            form_date: draftDate,
            extracted_data: draftData,
            overwrite_session_inputs: true,
          },
        });
        setDirty(false);
      } catch {
        return;
      }
    }
    scanForm.mutate({
      sessionId: sessionId!,
      formCode: spec.code,
      files,
      overwrite: true,
      mode,
    });
  }

  return (
    <div className="space-y-4">
      {/* Üst Sıralı Form Gezinme Çubuğu */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-3.5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5 min-w-0">
            <Button
              size="sm"
              variant="ghost"
              icon={<ArrowLeft size={13} />}
              onClick={() => requestNavigate(prevSpec.code)}
              title={`Önceki: ${prevSpec.shortCode} ${prevSpec.shortTitle} (Alt+←)`}
            >
              {prevSpec.shortCode}
            </Button>

            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[11px] font-bold text-[var(--primary)]">
                  Form {spec.order} / {BOTAS_FORM_NAV_ITEMS.length} · {spec.botasCode}
                </span>
                <Badge tone={spec.required ? "info" : "neutral"}>
                  {spec.required ? "Zorunlu" : "Ek Form"}
                </Badge>
                <Badge tone={stMeta.tone}>{stMeta.label}</Badge>
                {formRecord && formRecord.pages.length > 1 ? (
                  <Badge tone="neutral">Sayfalar: {formRecord.pages.length}</Badge>
                ) : null}
                {dirty ? <Badge tone="warning">Kaydedilmedi</Badge> : null}
              </div>
              <h1 className="truncate text-base font-bold tracking-tight text-[var(--text)]">
                {spec.title}
              </h1>
              <p className="text-[11px] text-[var(--text-muted)]">
                {projectName || "Proje seçilmedi"} · {payload?.section_no || sessionName}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => requestNavigate(nextSpec.code)}
              title={`Sonraki: ${nextSpec.shortCode} ${nextSpec.shortTitle} (Alt+→)`}
            >
              <span>{nextSpec.shortCode}</span>
              <ArrowRight size={13} aria-hidden />
            </Button>

            {nextIssueForm ? (
              <Button
                size="sm"
                variant="ghost"
                icon={<AlertTriangle size={13} className="text-[var(--warning)]" />}
                onClick={() => requestNavigate(nextIssueForm.form_code as BotasFormCode)}
              >
                Sonraki Bulgulu ({BOTAS_FORM_BY_CODE[nextIssueForm.form_code]?.shortCode ?? nextIssueForm.botas_code})
              </Button>
            ) : null}

            <div className="relative flex flex-wrap items-center gap-2">
              <div className="relative">
                <input
                  id={uploadInputId}
                  name="files"
                  type="file"
                  multiple
                  accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.xls,.xlsx"
                  className="visually-hidden peer"
                  disabled={scanForm.isPending}
                  onChange={(e) => {
                    void handleUploadFormFiles(e.target.files, "replace");
                    e.target.value = "";
                  }}
                />
                <label
                  htmlFor={uploadInputId}
                  title="Tek veya birden fazla sayfa dosyası (.pdf, .jpg, .png, .xlsx) seçebilirsiniz"
                  className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] px-3 text-xs font-semibold text-[var(--text-soft)] transition-colors hover:border-[var(--primary)] hover:text-[var(--text)] peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--primary)] peer-focus-visible:ring-offset-1"
                >
                  <FileScan size={13} aria-hidden />
                  {scanForm.isPending ? "Taranıyor..." : "Doküman Tara"}
                </label>
              </div>

              {formRecord && formRecord.status !== "empty" ? (
                <div className="relative">
                  <input
                    id={appendUploadInputId}
                    name="append_files"
                    type="file"
                    multiple
                    accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.xls,.xlsx"
                    className="visually-hidden peer"
                    disabled={scanForm.isPending}
                    onChange={(e) => {
                      void handleUploadFormFiles(e.target.files, "append");
                      e.target.value = "";
                    }}
                  />
                  <label
                    htmlFor={appendUploadInputId}
                    title="Yeni sayfadaki satırları, notları ve imzaları mevcut form verileriyle birleştirir"
                    className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--primary-border)] bg-[var(--primary-soft)] px-3 text-xs font-semibold text-[var(--primary)] transition-colors hover:bg-[var(--primary)] hover:text-white peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--primary)] peer-focus-visible:ring-offset-1"
                  >
                    <FilePlus2 size={13} aria-hidden />
                    Devam Sayfası Ekle
                  </label>
                </div>
              ) : null}
            </div>

            <Button
              size="sm"
              variant="primary"
              icon={<Save size={13} />}
              loading={updateForm.isPending}
              onClick={() => handleSave()}
            >
              Kaydet &amp; Kontrol Et
            </Button>
          </div>
        </div>

        {/* 16 Form Sıralı İlerleme Noktaları */}
        <div className="mt-3 flex flex-wrap items-center gap-1 border-t border-[var(--border)] pt-2.5">
          {BOTAS_FORM_NAV_ITEMS.map((item) => {
            const rec = payload?.forms.find((f) => f.form_code === item.code);
            const isActive = item.code === spec.code;
            const st = rec?.status ?? "empty";
            const dotCls =
              st === "passed"
                ? "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success)]"
                : st === "failed"
                  ? "border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger)]"
                  : st === "warning"
                    ? "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning)]"
                    : st === "filled"
                      ? "border-[var(--primary-border)] bg-[var(--primary-soft)] text-[var(--primary)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-faint)]";
            return (
              <button
                key={item.code}
                type="button"
                onClick={() => requestNavigate(item.code)}
                title={`${item.shortCode} — ${item.title}`}
                className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold transition-all ${dotCls} ${
                  isActive ? "ring-2 ring-[var(--primary)] ring-offset-1 ring-offset-[var(--surface)]" : "opacity-85 hover:opacity-100"
                }`}
              >
                {item.shortCode}
              </button>
            );
          })}
        </div>
      </div>

      {/* 020 & 022 İçin Detay Hesaplama Geçiş Bandı */}
      {spec.hasDetailCalc ? (
        <div className="rounded-xl border border-[var(--primary-border)] bg-[color-mix(in_srgb,var(--primary-soft)_55%,var(--surface))] px-4 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs">
              <Calculator size={15} className="text-[var(--primary)]" aria-hidden />
              <span className="font-semibold text-[var(--text)]">
                {spec.hasDetailCalc === "air"
                  ? "Bu form Hava İçerik Testi hesap motoruyla doğrudan bağlantılıdır."
                  : "Bu form Basınç Değişim Testi hesap motoruyla doğrudan bağlantılıdır."}
              </span>
            </div>
            <Button
              size="sm"
              variant={showDetailCalc ? "primary" : "ghost"}
              icon={showDetailCalc ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              onClick={() => setShowDetailCalc((v) => !v)}
            >
              {showDetailCalc
                ? "Detay Hesaplamayı Gizle"
                : spec.hasDetailCalc === "air"
                  ? "Detay Hesaplamaları Göster (Hava İçerik Testi)"
                  : "Detay Hesaplamaları Göster (Basınç Değişim Testi)"}
            </Button>
          </div>
        </div>
      ) : null}

      {isDemoOrOffline ? (
        <InlineNotice tone="warning" title="Çevrimdışı / Demo Modu">
          Formları kalıcı veritabanına kaydetmek ve OCR taraması yapmak için önce{" "}
          <button
            type="button"
            onClick={() => setTab("projects")}
            className="font-semibold text-[var(--primary)] underline"
          >
            Projeler &amp; Kesitler
          </button>{" "}
          sayfasından sunucudaki bir proje kesitini açın veya Test Raporu Kontrolü (OCR) üzerinden yükleyin.
        </InlineNotice>
      ) : null}

      {/* 020 / 022 Detay Hesaplama Paneli (Açıldığında tam mevcut sayfayı gömer) */}
      {spec.hasDetailCalc && showDetailCalc ? (
        <div className="rounded-2xl border border-[var(--primary-border)] bg-[var(--surface)] p-4">
          {spec.hasDetailCalc === "air" ? <AirPage embedded /> : <PressurePage embedded />}
        </div>
      ) : null}

      {formsQuery.isLoading && !payload && !isDemoOrOffline ? (
        <div
          className="grid gap-4 2xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,1fr)]"
          aria-busy="true"
          aria-label="Form yükleniyor"
        >
          <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="skeleton h-16 w-full" />
            <div className="grid grid-cols-3 gap-2">
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
            </div>
            <div className="skeleton h-52 w-full" />
          </div>
          <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="skeleton h-10 w-full" />
            <div className="skeleton h-28 w-full" />
            <div className="skeleton h-28 w-full" />
          </div>
        </div>
      ) : (
      /* Ana İki Sütunlu BOTAŞ Formu + Şartname Kontrolleri */
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,1fr)]">
        {/* Sol Sütun: Resmî BOT-FRM Form Sayfası */}
        <div className="min-w-0 overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] shadow-sm">
          {/* 3 Sütunlu Resmî BOTAŞ Başlık Bloğu */}
          <div className="grid border-b border-[var(--border-strong)] bg-[var(--surface-2)] md:grid-cols-[180px_minmax(0,1fr)_220px]">
            <div className="flex flex-col justify-center border-b border-[var(--border)] px-3.5 py-2.5 sm:border-b-0 sm:border-r">
              <span className="text-xs font-extrabold tracking-wide text-[var(--text)]">BOTAŞ</span>
              <span className="text-[10px] text-[var(--text-muted)]">
                Boru Hatları ile Petrol Taşıma A.Ş.
              </span>
            </div>
            <div className="flex flex-col justify-center px-3.5 py-2.5 text-center">
              <span className="font-mono text-[10px] font-bold tracking-wider text-[var(--primary)]">
                {spec.botasCode}
              </span>
              <span className="text-sm font-extrabold uppercase tracking-tight text-[var(--text)]">
                {spec.title}
              </span>
              <span className="mt-0.5 truncate text-[11px] text-[var(--text-soft)]">
                Proje: {asStr(hdr, "project_name") || projectName || "—"}
              </span>
            </div>
            <div className="flex flex-col justify-center gap-1 border-t border-[var(--border)] px-3.5 py-2.5 sm:border-l sm:border-t-0">
              <label className="text-[10px] text-[var(--text-muted)]">
                Yüklenici Firma:
                <input
                  type="text"
                  value={asStr(hdr, "contractor_name")}
                  placeholder="Yüklenici adı"
                  onChange={(e) => setHeaderField("contractor_name", e.target.value)}
                  className="mt-0.5 h-6 w-full rounded border border-[var(--border)] bg-[var(--canvas)] px-2 text-[11px] text-[var(--text)]"
                />
              </label>
              <label className="text-[10px] text-[var(--text-muted)]">
                Form Tarihi:
                <input
                  type="text"
                  value={draftDate}
                  placeholder="GG.AA.YYYY"
                  onChange={(e) => {
                    setDraftDate(e.target.value);
                    setDirty(true);
                  }}
                  className="mt-0.5 h-6 w-full rounded border border-[var(--border)] bg-[var(--canvas)] px-2 font-mono text-[11px] text-[var(--text)]"
                />
              </label>
            </div>
          </div>

          {/* Ortak BOTAŞ Üst Bilgi Bloğu (Test Bölüm No, Çap, Boy, Hacim, Başlıklar) */}
          <div className="border-b border-[var(--border)] bg-[var(--canvas)] px-3.5 py-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                Ortak Form Bilgileri &amp; Test Kesit Kimliği
              </span>
              <button
                type="button"
                onClick={applySectionHeaderToForm}
                className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-[var(--primary)] hover:underline"
              >
                <Sparkles size={11} aria-hidden /> Eksik alanları test kesitinden tamamla
              </button>
            </div>

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["section_no", "Test Bölüm No", false],
                ["length_m", "Test Bölüm Boyu (m)", true],
                ["section_volume_m3", "Test Bölüm Hacmi (m³)", true],
                ["outside_diameter_mm", "Boru Dış Çapı (mm)", true],
                ["inside_diameter_mm", "Boru İç Çapı (mm)", true],
                ["wall_thickness_mm", "Boru Et Kalınlığı (mm)", true],
                ["head_1_location", "1. Başlık Yeri / KP", false],
                ["head_2_location", "2. Başlık Yeri / KP", false],
              ].map(([key, label, isNumeric]) => {
                const k = String(key);
                const own = asStr(hdr, k);
                const inherited = mergedHeader[k] !== undefined && mergedHeader[k] !== null ? String(mergedHeader[k]) : "";
                return (
                  <label key={k} className="block rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5">
                    <span className="block text-[9.5px] font-medium text-[var(--text-muted)]">{label}</span>
                    <CellInput
                      type={isNumeric ? "number" : "text"}
                      align={isNumeric ? "right" : "left"}
                      ariaLabel={String(label)}
                      value={own}
                      placeholder={inherited || "—"}
                      onChange={(val) => setHeaderField(k, isNumeric ? parseMaybeNum(val) : val)}
                      className="mt-0.5 h-7 w-full"
                    />
                  </label>
                );
              })}
            </div>
          </div>

          {/* Forma Özgü Tablolar & Parametreler */}
          <div className="p-3.5">
            <FormBodyEditor
              formCode={spec.code}
              draft={draftData}
              onChange={(next) => {
                setDraftData(next);
                setDirty(true);
              }}
              calculations={calculations}
              mergedHeader={mergedHeader}
            />
          </div>

          {/* Açıklamalar ve Müteahhit / BOTAŞ İmza Bloğu */}
          <div className="space-y-3 border-t border-[var(--border)] bg-[var(--surface-2)] p-3.5">
            <label className="block">
              <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                Açıklamalar / Saha Notları
              </span>
              <textarea
                rows={2}
                value={asStr(draftData, "notes")}
                onChange={(e) => {
                  setDraftData((prev) => ({ ...prev, notes: e.target.value }));
                  setDirty(true);
                }}
                placeholder="Form üzerindeki saha açıklamalarını veya inceleme notlarını buraya girebilirsiniz..."
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--canvas)] p-2 text-xs text-[var(--text)] focus:border-[var(--primary)] focus:outline-none"
              />
            </label>

            <div className="grid gap-3 border-t border-[var(--border)] pt-3 sm:grid-cols-2">
              <label className="block rounded-lg border border-[var(--border)] bg-[var(--canvas)] p-2.5">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase text-[var(--text-muted)]">
                  <span>Müteahhit / Yüklenici Adı-Soyadı</span>
                  <Badge tone={asStr(sig, "contractor_name") ? "pass" : "neutral"}>
                    {asStr(sig, "contractor_name") ? "İmzalı" : "Boş"}
                  </Badge>
                </div>
                <input
                  type="text"
                  value={asStr(sig, "contractor_name")}
                  placeholder="Adı-Soyadı"
                  onChange={(e) => {
                    setDraftData((prev) => ({
                      ...prev,
                      signatures: {
                        ...asObj(prev.signatures),
                        contractor_name: e.target.value,
                        contractor_signed: Boolean(e.target.value.trim()),
                      },
                    }));
                    setDirty(true);
                  }}
                  className="mt-1 h-7 w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-xs text-[var(--text)]"
                />
              </label>

              <label className="block rounded-lg border border-[var(--border)] bg-[var(--canvas)] p-2.5">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase text-[var(--text-muted)]">
                  <span>BOTAŞ Kontrol Adı-Soyadı</span>
                  <Badge tone={asStr(sig, "botas_name") ? "pass" : "neutral"}>
                    {asStr(sig, "botas_name") ? "İmzalı" : "Boş"}
                  </Badge>
                </div>
                <input
                  type="text"
                  value={asStr(sig, "botas_name")}
                  placeholder="Adı-Soyadı"
                  onChange={(e) => {
                    setDraftData((prev) => ({
                      ...prev,
                      signatures: {
                        ...asObj(prev.signatures),
                        botas_name: e.target.value,
                        botas_signed: Boolean(e.target.value.trim()),
                      },
                    }));
                    setDirty(true);
                  }}
                  className="mt-1 h-7 w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-xs text-[var(--text)]"
                />
              </label>
            </div>
          </div>
        </div>

        {/* Sağ Sütun: Otomatik Şartname Kontrolleri ve Bulgular */}
        <div className="space-y-4">
          <SectionCard
            title="Şartname Kontrolleri & Bulgular"
            description="4-NGTL 0-GN-P-002-5007 R4 kurallarına göre form bazlı otomatik doğrulama sonuçları."
            icon={ShieldAlert}
            action={<Badge tone={stMeta.tone}>{stMeta.label}</Badge>}
          >
            {formRecord?.status === "empty" ? (
              <InlineNotice tone="info" title="Form henüz taranmadı veya doldurulmadı" icon={Info}>
                Sol taraftaki tablolara elle veri girip “Kaydet &amp; Kontrol Et” düğmesine basabilir ya da
                yukarıdan “Bu Forma Doküman Tara” ile taranmış PDF / görsel / Excel yükleyebilirsiniz.
              </InlineNotice>
            ) : findings.length === 0 ? (
              <InlineNotice tone="info" title="Ek bulgu kaydı yok">
                Form kaydedildiğinde tüm hesaplama ve şartname kuralları burada sıralanır.
              </InlineNotice>
            ) : (
              <div className="space-y-2.5">
                {findings.map((fd) => {
                  const Icon =
                    fd.status === "passed"
                      ? CheckCircle2
                      : fd.status === "failed"
                        ? XCircle
                        : fd.status === "warning"
                          ? AlertTriangle
                          : Info;
                  const boxCls =
                    fd.status === "passed"
                      ? "border-[var(--success-border)] bg-[color-mix(in_srgb,var(--success-bg)_45%,transparent)]"
                      : fd.status === "failed"
                        ? "border-[var(--danger-border)] bg-[color-mix(in_srgb,var(--danger-bg)_55%,transparent)]"
                        : fd.status === "warning"
                          ? "border-[var(--warning-border)] bg-[color-mix(in_srgb,var(--warning-bg)_50%,transparent)]"
                          : "border-[var(--border)] bg-[var(--surface-2)]";

                  return (
                    <div key={fd.code} className={`rounded-xl border p-3 ${boxCls}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2">
                          <Icon size={15} className="mt-0.5 shrink-0" aria-hidden />
                          <span className="text-xs font-bold text-[var(--text)]">{fd.title}</span>
                        </div>
                        <Badge tone={findingTone(fd.status)}>{findingLabel(fd.status)}</Badge>
                      </div>
                      <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--text-soft)]">
                        {fd.message}
                      </p>
                      {fd.expected || fd.actual ? (
                        <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10px] text-[var(--text-muted)]">
                          {fd.expected ? <span>Beklenen: {fd.expected}</span> : null}
                          {fd.actual ? <span>Gerçekleşen: {fd.actual}</span> : null}
                        </div>
                      ) : null}
                      <span className="mt-1.5 block font-mono text-[9.5px] text-[var(--text-faint)]">
                        {fd.ref}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {relatedCheckpoints.length > 0 ? (
              <div className="mt-4 space-y-2 border-t border-[var(--border)] pt-3">
                <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  İlgili Bölüm Kontrol Noktaları
                </span>
                {relatedCheckpoints.map((cp) => (
                  <div
                    key={cp.key}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-[11px]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-[var(--text)]">{cp.label}</span>
                      <Badge
                        tone={
                          cp.status === "passed"
                            ? "pass"
                            : cp.status === "failed"
                              ? "fail"
                              : cp.status === "warning"
                                ? "warning"
                                : "neutral"
                        }
                      >
                        Madde {cp.ref}
                      </Badge>
                    </div>
                    {cp.message ? (
                      <p className="mt-1 text-[var(--text-soft)]">{cp.message}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Kaynak Doküman & İzlenebilirlik" icon={FolderKanban}>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
                <span className="block text-[9.5px] uppercase text-[var(--text-faint)]">Kaynak Dosya</span>
                <span className="mt-0.5 block truncate font-medium text-[var(--text)]" title={formRecord?.source_filename || ""}>
                  {formRecord?.source_filename || "Elle / henüz taranmadı"}
                </span>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
                <span className="block text-[9.5px] uppercase text-[var(--text-faint)]">Sayfalar / Rev.</span>
                <span className="mt-0.5 block font-mono text-[var(--text)]">
                  {formRecord?.pages.length ? `s. ${formRecord.pages.join(", ")}` : "—"} · rev.{formRecord?.revision ?? 0}
                </span>
              </div>
              <div className="col-span-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2">
                <span className="block text-[9.5px] uppercase text-[var(--text-faint)]">Son Güncelleme</span>
                <span className="mt-0.5 block font-mono text-[var(--text)]">
                  {formRecord?.updated_at ? dateTime(formRecord.updated_at) : "Henüz kaydedilmedi"}
                </span>
              </div>
            </div>

            {payload?.summary ? (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[11px]">
                <span className="text-[var(--text-soft)]">
                  Bölüm Özeti:{" "}
                  <strong className="text-[var(--text)]">
                    {payload.summary.filled_required}/{payload.summary.required_total} Form
                  </strong>
                  {payload.summary.findings_counts ? (
                    <>
                      {" · "}
                      {num(payload.summary.findings_counts.passed, 0)} uygun,{" "}
                      {num(payload.summary.findings_counts.warning, 0)} uyarı,{" "}
                      {num(payload.summary.findings_counts.failed, 0)} hata
                    </>
                  ) : null}
                </span>
                <Button size="sm" variant="ghost" onClick={() => setTab("projects")}>
                  Kesitlere Dön
                </Button>
              </div>
            ) : null}
          </SectionCard>
        </div>
      </div>
      )}

      <Modal
        open={Boolean(pendingNavCode)}
        onClose={() => setPendingNavCode(null)}
        title="Kaydedilmemiş Form Değişiklikleri"
        description="Bu formdaki düzenlemeler henüz veritabanına kaydedilmedi."
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingNavCode(null)}>
              Vazgeç
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                const target = pendingNavCode;
                setPendingNavCode(null);
                setDirty(false);
                if (target) openForm(target);
              }}
            >
              Kaydetmeden Geç
            </Button>
            <Button
              variant="primary"
              icon={<Save size={13} />}
              loading={updateForm.isPending}
              onClick={() => {
                const target = pendingNavCode;
                handleSave(() => {
                  setPendingNavCode(null);
                  if (target) openForm(target);
                });
              }}
            >
              Kaydet ve Geç
            </Button>
          </>
        }
      >
        <p className="text-xs leading-relaxed text-[var(--text-soft)]">
          <strong>
            {spec.shortCode} — {spec.title}
          </strong>{" "}
          formundan ayrılmadan önce değişiklikleri kaydedip şartname kontrollerini yenilemek ister
          misiniz?
        </p>
      </Modal>
    </div>
  );
}
