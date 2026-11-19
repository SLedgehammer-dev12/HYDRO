import { useEffect, useState } from "react";
import {
  Archive,
  CheckCircle2,
  CopyPlus,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  GitCompareArrows,
  Layers,
  RefreshCw,
  Ruler,
  Wand2,
} from "lucide-react";
import { Badge, StatusBadge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { KpiCard } from "../../components/ui/Card";
import { Modal } from "../../components/ui/Dialog";
import { CheckboxRow, FieldGrid, NumberField, SelectField, TextField } from "../../components/ui/Field";
import { EmptyState, InlineNotice } from "../../components/ui/State";
import {
  useCloneProject,
  useGenerateProjectSections,
  useProjectDataset,
  useSyncProjectForms,
} from "../../hooks/queries";
import { api, apiErrorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { downloadBlob } from "../../lib/report";
import type { DecisionStatus, Project, ProjectExportFormat } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";

type DataCenterTab = "overview" | "generate" | "sync" | "clone";

function overallBadge(overall: DecisionStatus | "KISMI") {
  if (overall === "KISMI") {
    return <Badge tone="warning">KISMI</Badge>;
  }
  return <StatusBadge status={overall} />;
}

export function ProjectDataCenterModal({
  open,
  project,
  onClose,
  onProjectCloned,
}: {
  open: boolean;
  project: Project | null;
  onClose: () => void;
  onProjectCloned?: (cloned: Project) => void;
}) {
  const pushToast = useAppStore((s) => s.pushToast);
  const backend = useAppStore((s) => s.backend);

  const [tab, setTab] = useState<DataCenterTab>("overview");
  const [busyDownload, setBusyDownload] = useState<string | null>(null);
  const [includeArchiveAttachments, setIncludeArchiveAttachments] = useState(true);

  const datasetQuery = useProjectDataset(project?.id ?? null, open);
  const generateSections = useGenerateProjectSections();
  const syncForms = useSyncProjectForms();
  const cloneProject = useCloneProject();

  // Toplu kesit üretimi formu
  const [startKpM, setStartKpM] = useState<number | null>(0);
  const [totalLengthM, setTotalLengthM] = useState<number | null>(24_000);
  const [maxSectionLenM, setMaxSectionLenM] = useState<number | null>(12_000);
  const [respectVolumeLimit, setRespectVolumeLimit] = useState(true);
  const [sectionPrefix, setSectionPrefix] = useState("K-");
  const [startIndex, setStartIndex] = useState<number | null>(1);
  const [odMm, setOdMm] = useState<number | null>(null);
  const [wtMm, setWtMm] = useState<number | null>(null);
  const [designPBar, setDesignPBar] = useState<number | null>(null);
  const [smysMpa, setSmysMpa] = useState<number | null>(null);
  const [testDate, setTestDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [createFormSlots, setCreateFormSlots] = useState(true);

  // Form eşitleme
  const [overwriteForms, setOverwriteForms] = useState(false);

  // Klonlama
  const [cloneName, setCloneName] = useState("");
  const [cloneCode, setCloneCode] = useState("");
  const [cloneMode, setCloneMode] = useState<"template" | "full">("template");

  useEffect(() => {
    if (!open || !project) return;
    setTab("overview");
    const d = project.defaults ?? {};
    setOdMm(d.outside_diameter_mm ?? null);
    setWtMm(d.wall_thickness_mm ?? null);
    setDesignPBar(d.design_pressure_bar ?? null);
    setSmysMpa(d.smys_mpa ?? null);
    setTotalLengthM(project.pipeline_length_m ?? 24_000);
    setStartIndex(Math.max(1, (project.section_count ?? 0) + 1));
    setCloneName(`${project.name} (Kopya)`);
    setCloneCode(project.code ? `${project.code}-C` : "");
  }, [open, project]);

  async function handleExport(fmt: ProjectExportFormat) {
    if (!project) return;
    setBusyDownload(fmt);
    try {
      const res = await api.exportProjectDataset(project.id, fmt);
      downloadBlob(res.blob, res.filename);
      pushToast("success", "Proje çıktısı indirildi", res.filename);
    } catch (error) {
      pushToast("error", "Dışa aktarım başarısız", apiErrorMessage(error));
    } finally {
      setBusyDownload(null);
    }
  }

  async function handleDownloadArchive() {
    if (!project) return;
    setBusyDownload("archive");
    try {
      const res = await api.downloadProjectArchive(project.id, includeArchiveAttachments);
      downloadBlob(res.blob, res.filename);
      pushToast("success", "Taşınabilir arşiv indirildi", res.filename);
    } catch (error) {
      pushToast("error", "Arşiv indirilemedi", apiErrorMessage(error));
    } finally {
      setBusyDownload(null);
    }
  }

  function submitGenerate() {
    if (!project || !totalLengthM || totalLengthM <= 0) {
      pushToast("warning", "Geçerli hat uzunluğu girin");
      return;
    }
    generateSections.mutate({
      projectId: project.id,
      payload: {
        start_kp_m: startKpM ?? 0,
        total_length_m: totalLengthM,
        max_section_length_m: maxSectionLenM ?? 12_000,
        respect_volume_limit: respectVolumeLimit,
        section_prefix: sectionPrefix.trim() || "K-",
        start_index: startIndex ?? 1,
        outside_diameter_mm: odMm,
        wall_thickness_mm: wtMm,
        design_pressure_bar: designPBar,
        smys_mpa: smysMpa,
        test_date: testDate || null,
        create_form_slots: createFormSlots,
      },
    });
  }

  function submitSync() {
    if (!project) return;
    syncForms.mutate({
      projectId: project.id,
      overwriteExisting: overwriteForms,
    });
  }

  function submitClone() {
    if (!project) return;
    cloneProject.mutate(
      {
        projectId: project.id,
        payload: {
          name: cloneName.trim() || null,
          code: cloneCode.trim() || null,
          mode: cloneMode,
        },
      },
      {
        onSuccess: (res) => {
          onProjectCloned?.(res.project);
          onClose();
        },
      },
    );
  }

  const dataset = datasetQuery.data;

  return (
    <Modal
      open={open}
      onClose={onClose}
      className="max-w-5xl"
      title={project ? `${project.name} · Proje Veri Merkezi` : "Proje Veri Merkezi"}
      description={
        project
          ? `${project.code || "kod yok"} · Tüm kesit sonuçlarını derleyin, Master Excel/PDF üretin, toplu KP kesiti oluşturun veya projeyi paketleyin.`
          : undefined
      }
      footer={
        <Button variant="ghost" onClick={onClose}>
          Kapat
        </Button>
      }
    >
      {backend !== "online" ? (
        <InlineNotice tone="warning" title="Çevrimdışı / Demo Modu" icon={Database}>
          Proje Veri Merkezi işlemleri yerel HYDRO veritabanı sunucusu çevrimiçi olduğunda
          kullanılabilir.
        </InlineNotice>
      ) : (
        <div className="space-y-4">
          <div className="seg-control" role="tablist" aria-label="Proje Veri Merkezi sekmeleri">
            {[
              { id: "overview" as const, label: "Veri Özeti & Dışa Aktarım" },
              { id: "generate" as const, label: "Toplu Kesit Üret" },
              { id: "sync" as const, label: "Form Metadata Eşitle" },
              { id: "clone" as const, label: "Projeyi Klonla" },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className="seg-btn"
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "overview" ? (
            datasetQuery.isLoading && !dataset ? (
              <div className="py-8 text-center text-xs text-[var(--text-muted)]">
                Proje veri seti derleniyor...
              </div>
            ) : dataset ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <KpiCard
                    label="Kesit / Boy"
                    value={num(dataset.summary.section_count, 0)}
                    unit="kesit"
                    hint={`Σ ${num(dataset.summary.total_length_m, 0)} m · ${num(dataset.summary.total_volume_m3, 1)} m³`}
                    icon={Ruler}
                  />
                  <KpiCard
                    label="KP Sürekliliği"
                    value={dataset.summary.continuity_ok ? "Uyumlu" : "Farklı"}
                    tone={dataset.summary.continuity_ok ? "pass" : "warning"}
                    hint={
                      dataset.summary.continuity_ok
                        ? "Ardışık KP zinciri eksiksiz"
                        : `${dataset.summary.continuity_gaps.length} kopukluk/boşluk`
                    }
                    icon={GitCompareArrows}
                  />
                  <KpiCard
                    label="Form Tamamlanma"
                    value={`%${num(dataset.summary.forms_completion_pct, 1)}`}
                    tone={dataset.summary.forms_completion_pct >= 100 ? "pass" : "info"}
                    hint={`${dataset.summary.forms_filled_total} / ${dataset.summary.forms_required_total} zorunlu`}
                    icon={FileText}
                  />
                  <KpiCard
                    label="Mühendislik Durumu"
                    value={`${dataset.summary.passed_count} / ${dataset.summary.section_count}`}
                    tone={dataset.summary.failed_count > 0 ? "fail" : dataset.summary.passed_count > 0 ? "pass" : "default"}
                    hint={`${dataset.summary.failed_count} başarısız · ${dataset.summary.pending_count} beklemede`}
                    icon={CheckCircle2}
                  />
                </div>

                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[12px] font-semibold text-[var(--text-soft)]">
                      Dışa Aktarım &amp; Taşınabilir Paket
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="primary"
                        icon={<FileSpreadsheet size={13} />}
                        loading={busyDownload === "xlsx"}
                        onClick={() => handleExport("xlsx")}
                      >
                        Master Excel (.xlsx)
                      </Button>
                      <Button
                        size="sm"
                        icon={<FileText size={13} />}
                        loading={busyDownload === "pdf"}
                        onClick={() => handleExport("pdf")}
                      >
                        Proje Özeti (.pdf)
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Download size={13} />}
                        loading={busyDownload === "csv"}
                        onClick={() => handleExport("csv")}
                      >
                        CSV
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Download size={13} />}
                        loading={busyDownload === "json"}
                        onClick={() => handleExport("json")}
                      >
                        JSON
                      </Button>
                      <Button
                        size="sm"
                        icon={<Archive size={13} />}
                        loading={busyDownload === "archive"}
                        onClick={handleDownloadArchive}
                      >
                        .hydroproj.zip İndir
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2">
                    <CheckboxRow
                      checked={includeArchiveAttachments}
                      onChange={setIncludeArchiveAttachments}
                      label="Taşınabilir arşiv (.hydroproj.zip) içine yüklenen form eklerini (PDF/görsel) dahil et"
                    />
                  </div>
                </div>

                {dataset.sections.length === 0 ? (
                  <EmptyState
                    title="Proje kesit tablosu boş"
                    description="Sağdaki 'Toplu Kesit Üret' sekmesinden KP bazlı kesitleri otomatik oluşturabilirsiniz."
                    icon={Layers}
                  />
                ) : (
                  <div className="table-wrap scroll-thin max-h-[320px] overflow-y-auto">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Kesit</th>
                          <th>KP Aralığı</th>
                          <th className="num">Boy (m)</th>
                          <th className="num">Hacim (m³)</th>
                          <th>Hava</th>
                          <th>Basınç</th>
                          <th className="num">Dew (°C)</th>
                          <th className="num">Form</th>
                          <th>Genel</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.sections.map((s) => (
                          <tr key={s.session_id}>
                            <td className="font-semibold text-[var(--text)]">{s.section_no}</td>
                            <td className="font-mono text-[11px]">
                              {s.start_kp || "—"} – {s.end_kp || "—"}
                            </td>
                            <td className="num">{num(s.length_m, 0)}</td>
                            <td className="num">{num(s.internal_volume_m3, 1)}</td>
                            <td>
                              <StatusBadge status={s.air_status} />
                            </td>
                            <td>
                              <StatusBadge status={s.pressure_status} />
                            </td>
                            <td className="num">{num(s.dew_point_c, 1)}</td>
                            <td className="num">
                              {s.forms_filled}/{s.forms_required}
                            </td>
                            <td>{overallBadge(s.overall_status)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : null
          ) : null}

          {tab === "generate" ? (
            <div className="space-y-3">
              <InlineNotice tone="info" title="4-NGTL Şartname Limitleri ile Kesit Bölme" icon={Wand2}>
                Bölüm uzunluğu en fazla 20.000 m ve internal su hacmi sınırı açıkken en fazla 12.500 m³
                olacak şekilde kesitler ve BOTAŞ form yuvaları otomatik üretilir.
              </InlineNotice>
              <FieldGrid cols={3}>
                <NumberField
                  label="Başlangıç KP"
                  unit="m"
                  value={startKpM}
                  onChange={setStartKpM}
                  min={0}
                />
                <NumberField
                  label="Toplam hat boyu"
                  unit="m"
                  value={totalLengthM}
                  onChange={setTotalLengthM}
                  min={10}
                  required
                />
                <NumberField
                  label="Azami kesit boyu"
                  unit="m"
                  value={maxSectionLenM}
                  onChange={setMaxSectionLenM}
                  min={100}
                  max={20_000}
                />
                <TextField
                  label="Kesit ön eki"
                  value={sectionPrefix}
                  onChange={setSectionPrefix}
                  placeholder="K-"
                />
                <NumberField
                  label="Başlangıç numarası"
                  value={startIndex}
                  onChange={setStartIndex}
                  min={1}
                  digits={0}
                />
                <TextField
                  label="Planlanan test tarihi"
                  type="date"
                  value={testDate}
                  onChange={setTestDate}
                />
                <NumberField
                  label="Dış çap (OD)"
                  unit="mm"
                  value={odMm}
                  onChange={setOdMm}
                  min={50}
                  placeholder="Proje varsayılanı"
                />
                <NumberField
                  label="Et kalınlığı (WT)"
                  unit="mm"
                  value={wtMm}
                  onChange={setWtMm}
                  min={1}
                  placeholder="Proje varsayılanı"
                />
                <NumberField
                  label="Dizayn basıncı"
                  unit="bar"
                  value={designPBar}
                  onChange={setDesignPBar}
                  min={1}
                  placeholder="Proje varsayılanı"
                />
              </FieldGrid>
              <FieldGrid cols={2}>
                <CheckboxRow
                  checked={respectVolumeLimit}
                  onChange={setRespectVolumeLimit}
                  label="İç su hacmi limitini (12.500 m³) otomatik uygula"
                  hint="Büyük çaplı borularda kesit boyunu hacim sınırına göre otomatik kısaltır."
                />
                <CheckboxRow
                  checked={createFormSlots}
                  onChange={setCreateFormSlots}
                  label="Her yeni kesit için BOTAŞ form yuvalarını hazırla"
                />
              </FieldGrid>
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  icon={<Wand2 size={14} />}
                  loading={generateSections.isPending}
                  onClick={submitGenerate}
                >
                  Toplu Kesitleri Oluştur
                </Button>
              </div>
            </div>
          ) : null}

          {tab === "sync" ? (
            <div className="space-y-3">
              <InlineNotice tone="info" title="Proje Bilgilerini Tüm BOTAŞ Formlarına İşle" icon={RefreshCw}>
                Seçili projenin yüklenici, müşavir, proje kodu, müşteri bilgileri ile her kesitin
                kendi KP aralığı, çap/et kalınlığı, hacim ve test basıncı bilgilerini tüm kesitlerin
                BOTAŞ form başlıklarına (`header`) yazar.
              </InlineNotice>
              <CheckboxRow
                checked={overwriteForms}
                onChange={setOverwriteForms}
                label="Mevcut dolu form başlıklarının üzerine yaz (boş bırakılırsa yalnızca eksik alanlar tamamlanır)"
              />
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  icon={<RefreshCw size={14} />}
                  loading={syncForms.isPending}
                  onClick={submitSync}
                >
                  Tüm Kesit Formlarını Eşitle
                </Button>
              </div>
            </div>
          ) : null}

          {tab === "clone" ? (
            <div className="space-y-3">
              <FieldGrid cols={3}>
                <TextField
                  label="Yeni proje adı"
                  value={cloneName}
                  onChange={setCloneName}
                  placeholder="Yeni Hat Faz-2"
                />
                <TextField
                  label="Yeni proje kodu"
                  value={cloneCode}
                  onChange={setCloneCode}
                  placeholder="PRJ-F2"
                />
                <SelectField
                  label="Klonlama kipi"
                  value={cloneMode}
                  onChange={(v) => setCloneMode(v === "full" ? "full" : "template")}
                  options={[
                    { value: "template", label: "Şablon (Geometri + KP + Boş Formlar)" },
                    { value: "full", label: "Tam Kopya (Sonuçlar + Zaman Serisi + Formlar)" },
                  ]}
                />
              </FieldGrid>
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  icon={<CopyPlus size={14} />}
                  loading={cloneProject.isPending}
                  onClick={submitClone}
                >
                  Projeyi Klonla
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}
