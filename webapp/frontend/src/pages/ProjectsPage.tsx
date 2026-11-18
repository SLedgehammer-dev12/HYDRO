import { Suspense, lazy, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Copy,
  FileCheck2,
  FileScan,
  FolderOpen,
  GitCompareArrows,
  Layers,
  Pencil,
  Plus,
  Rows3,
  Ruler,
  Trash2,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, KpiCard } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { ConfirmDialog, Modal } from "../components/ui/Dialog";
import { FieldGrid, NumberField, TextField } from "../components/ui/Field";
import { EmptyState, InlineNotice } from "../components/ui/State";
import { PlanProfileScanModal } from "../features/projects/PlanProfileScanModal";
import { SectionFormsModal } from "../features/projects/SectionFormsModal";
const PipelineScene = lazy(() => import("../components/three/PipelineScene"));
import {
  useCreateProject,
  useCreateSession,
  useDeleteProject,
  useDeleteSection,
  useDuplicateSession,
  useOpenSession,
  useProjectScene,
  useProjects,
  useSessions,
  useUpdateProject,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { createEmptyInputs } from "../lib/mock";
import { toApiInputs } from "../lib/normalize";
import {
  evaluateProjectKpContinuity,
  formatKp,
  formatKpLocation,
  normalizeKpText,
  parseKpMeters,
  resolveSectionMeta,
} from "../lib/kp";
import { dateTime, num, relativeTime } from "../lib/format";
import type {
  BotasFormCode,
  Project,
  SectionMeta,
  SessionListItem,
  SessionStatus,
} from "../lib/types";

interface ProjectForm {
  name: string;
  code: string;
  client: string;
  description: string;
}

interface SectionForm {
  section_no: string;
  start_kp: string;
  end_kp: string;
  description: string;
  test_date: string;
  notes: string;
}

const EMPTY_FORM: ProjectForm = { name: "", code: "", client: "", description: "" };

function statusTone(status: SessionStatus): "pass" | "info" | "pending" | "neutral" {
  if (status === "completed") return "pass";
  if (status === "active") return "info";
  if (status === "draft") return "pending";
  return "neutral";
}

function statusLabel(status: SessionStatus): string {
  if (status === "completed") return "Tamamlandı";
  if (status === "active") return "Aktif";
  if (status === "draft") return "Taslak";
  return "Arşiv";
}

function nextSectionNo(sections: SessionListItem[]): string {
  return `K-${String(sections.length + 1).padStart(2, "0")}`;
}

export function ProjectsPage() {
  const projectsQuery = useProjects();
  const projects = projectsQuery.data ?? [];

  const setTab = useAppStore((state) => state.setTab);
  const openForm = useAppStore((state) => state.openForm);
  const projectId = useAppStore((state) => state.projectId);
  const setProject = useAppStore((state) => state.setProject);
  const setSceneScope = useAppStore((state) => state.setSceneScope);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const markSaved = useAppStore((state) => state.markSaved);
  const pushToast = useAppStore((state) => state.pushToast);

  const createProject = useCreateProject();
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();
  const createSession = useCreateSession();
  const duplicateSession = useDuplicateSession();
  const deleteSession = useDeleteSection();
  const openSession = useOpenSession();

  const [selectedId, setSelectedId] = useState<string | null>(projectId);
  const selected = useMemo(
    () => projects.find((project) => project.id === (selectedId ?? projectId)) ?? projects[0] ?? null,
    [projects, selectedId, projectId],
  );
  const sectionsQuery = useSessions(selected?.id ?? null, { enabled: Boolean(selected) });
  const rawSections = selected ? (sectionsQuery.data ?? []) : [];

  /* Projeye ait tüm kesitler için ardışık KP sürekliliği denetimi */
  const kpContinuity = useMemo(
    () => evaluateProjectKpContinuity(rawSections),
    [rawSections],
  );

  const [sortKey, setSortKey] = useState<"kp" | "name" | "updated" | "status">("kp");
  const sections = useMemo(() => {
    const items = [...rawSections];
    const orderIndex = new Map(kpContinuity.orderedIds.map((id, idx) => [id, idx]));
    items.sort((a, b) => {
      if (sortKey === "kp") {
        return (orderIndex.get(a.id) ?? 0) - (orderIndex.get(b.id) ?? 0);
      }
      if (sortKey === "updated") return b.updated_at.localeCompare(a.updated_at);
      if (sortKey === "status") return a.status.localeCompare(b.status) || a.name.localeCompare(b.name);
      return a.name.localeCompare(b.name, "tr", { numeric: true });
    });
    return items;
  }, [rawSections, sortKey, kpContinuity.orderedIds]);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectForm>(EMPTY_FORM);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);
  const [deletingSection, setDeletingSection] = useState<SessionListItem | null>(null);
  const [formsModalSession, setFormsModalSession] = useState<SessionListItem | null>(null);

  /* Yeni kesit (section) oluşturma modal durumu */
  const [sectionDialogOpen, setSectionDialogOpen] = useState(false);
  const [sectionForm, setSectionForm] = useState<SectionForm>({
    section_no: "K-01",
    start_kp: "0+000",
    end_kp: "12+000",
    description: "",
    test_date: new Date().toISOString().slice(0, 10),
    notes: "",
  });

  /* Plan-Profil PDF/CAD çoklu pafta tarama ve taslak kesit üretimi modal durumu */
  const [scanDialogOpen, setScanDialogOpen] = useState(false);
  const [showProjectScene, setShowProjectScene] = useState(false);
  const projectSceneQuery = useProjectScene(
    selected?.id ?? null,
    showProjectScene && Boolean(selected),
  );

  /* Yeni kesit eklenirken bir önceki kesitin bitiş KP'sini bul */
  const lastOrderedSection = useMemo(() => {
    if (kpContinuity.orderedIds.length === 0) return null;
    const lastId = kpContinuity.orderedIds[kpContinuity.orderedIds.length - 1];
    return kpContinuity.byId[lastId] ?? null;
  }, [kpContinuity]);

  const modalStartM = parseKpMeters(sectionForm.start_kp);
  const modalEndM = parseKpMeters(sectionForm.end_kp);
  const modalSpanM = modalStartM !== null && modalEndM !== null ? modalEndM - modalStartM : null;
  const modalPrevEndM = lastOrderedSection?.endM ?? null;
  const modalDeltaFromPrevM =
    modalPrevEndM !== null && modalStartM !== null ? modalStartM - modalPrevEndM : null;
  const modalMatchesPrev =
    modalDeltaFromPrevM === null ? true : Math.abs(modalDeltaFromPrevM) <= 0.5;

  const totalSections = projects.reduce((sum, project) => sum + project.section_count, 0);

  function chooseProject(project: Project) {
    setSelectedId(project.id);
    setProject(project);
  }

  function openCreateProject() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEditProject(project: Project) {
    setEditing(project);
    setForm({
      name: project.name,
      code: project.code ?? "",
      client: project.client ?? "",
      description: project.description ?? "",
    });
    setDialogOpen(true);
  }

  function submitProject() {
    if (!form.name.trim()) {
      pushToast("warning", "Proje adı gerekli", "Proje adı boş olamaz.");
      return;
    }
    const payload = {
      name: form.name.trim(),
      code: form.code.trim(),
      client: form.client.trim(),
      description: form.description.trim(),
    };
    if (editing) {
      updateProject.mutate(
        { id: editing.id, patch: payload },
        {
          onSuccess: (project) => {
            setProject(project);
            setDialogOpen(false);
          },
        },
      );
    } else {
      createProject.mutate(payload, {
        onSuccess: (project) => {
          setSelectedId(project.id);
          setProject(project);
          setDialogOpen(false);
        },
      });
    }
  }

  function openSection(session: SessionListItem) {
    const project = projects.find((item) => item.id === session.project_id) ?? selected;
    if (project) setProject(project);
    openSession.mutate(session.id, {
      onSuccess: () => setTab("geometry"),
    });
  }

  function openSectionForms(session: SessionListItem, formCode?: BotasFormCode | string | null) {
    const project = projects.find((item) => item.id === session.project_id) ?? selected;
    if (project) setProject(project);
    const targetCode = (formCode || session.forms_summary?.first_issue_form_code || "test_data") as BotasFormCode;
    openSession.mutate(session.id, {
      onSuccess: () => openForm(targetCode),
    });
  }

  function openCreateSectionDialog() {
    if (!selected) return;
    /* Varsa son kesitin bitiş KP'sini yeni kesitin başlangıç KP'si olarak öner */
    const suggestedStartM = lastOrderedSection?.endM ?? 0;
    const suggestedEndM = suggestedStartM + 12_000;
    setSectionForm({
      section_no: nextSectionNo(rawSections),
      start_kp: formatKp(suggestedStartM),
      end_kp: formatKp(suggestedEndM),
      description: selected.name,
      test_date: new Date().toISOString().slice(0, 10),
      notes: "",
    });
    setSectionDialogOpen(true);
  }

  function submitCreateSection() {
    if (!selected) return;
    if (modalStartM === null || modalEndM === null) {
      pushToast(
        "warning",
        "KP bilgisi gerekli",
        "Başlangıç ve bitiş KP noktalarını girin (ör. 0+000 ve 12+000).",
      );
      return;
    }
    if (modalEndM <= modalStartM) {
      pushToast(
        "error",
        "Geçersiz KP aralığı",
        `Bitiş KP (${formatKp(modalEndM)}), başlangıç KP (${formatKp(modalStartM)}) değerinden büyük olmalıdır.`,
      );
      return;
    }

    const startFormatted = formatKp(modalStartM);
    const endFormatted = formatKp(modalEndM);
    const sectionNo = sectionForm.section_no.trim() || nextSectionNo(rawSections);
    const lengthM = Math.round((modalEndM - modalStartM) * 100) / 100;

    const inputs = createEmptyInputs();
    const meta: SectionMeta = {
      ...inputs.section_meta,
      section_no: sectionNo,
      description: sectionForm.description.trim() || selected.name,
      start_kp: startFormatted,
      end_kp: endFormatted,
      location: formatKpLocation(startFormatted, endFormatted),
      test_date: sectionForm.test_date || new Date().toISOString().slice(0, 10),
      test_type: "Hidrostatik test",
      notes: sectionForm.notes.trim(),
    };
    inputs.section_meta = meta;
    inputs.geometry.length_m = lengthM;

    const name = `${meta.section_no} · KP ${startFormatted}–${endFormatted} · ${selected.code || selected.name}`;
    createSession.mutate(
      { name, inputs: toApiInputs(inputs), projectId: selected.id },
      {
        onSuccess: ({ session }) => {
          setProject(selected);
          applySessionInputs(session.inputs);
          setSessionMeta({
            id: session.id,
            name: session.name,
            status: session.status,
            revision: session.revision,
          });
          markSaved(session.revision);
          setSectionDialogOpen(false);
          if (!modalMatchesPrev && lastOrderedSection) {
            pushToast(
              "warning",
              "KP süreklilik uyarısı",
              `${lastOrderedSection.sectionLabel} bitiş KP (${lastOrderedSection.endKp}) ile ${sectionNo} başlangıç KP (${startFormatted}) eşleşmiyor.`,
            );
          }
          setTab("geometry");
        },
      },
    );
  }

  function copySection(session: SessionListItem) {
    duplicateSession.mutate({
      id: session.id,
      name: `${session.name} (kopya)`,
    });
  }

  function openScanDialog() {
    if (!selected) return;
    setScanDialogOpen(true);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Projeler & Kesitler"
        title="Proje kayıtları ve kesit envanteri"
        description="Projeyi seçin, boru kesitlerini başlangıç/bitiş KP noktalarıyla kaydedin, ardışık KP sürekliliğini denetleyin ve istediğiniz kesiti yeniden açın."
        meta={
          <>
            <Badge tone="info">{projects.length} proje</Badge>
            <Badge tone="neutral">{totalSections} kesit</Badge>
            {selected ? <span className="chip">{selected.code || "kod yok"}</span> : null}
            {rawSections.length > 0 ? (
              <Badge tone={kpContinuity.status}>
                {kpContinuity.status === "pass"
                  ? "KP sürekliliği uygun"
                  : kpContinuity.status === "fail"
                    ? "KP uyuşmazlığı var"
                    : "KP eksik"}
              </Badge>
            ) : null}
          </>
        }
        actions={
          <>
            <Button size="lg" variant="ghost" icon={<Rows3 size={15} />} onClick={() => setTab("geometry")}>
              Geometri & Saha
            </Button>
            <Button size="lg" variant="primary" icon={<Plus size={15} />} onClick={openCreateProject}>
              Yeni proje
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard label="Proje" value={num(projects.length, 0)} icon={Building2} hint="Kayıtlı proje sayısı" />
        <KpiCard label="Toplam kesit" value={num(totalSections, 0)} icon={Layers} hint="Projelere bağlı kesitler" />
        <KpiCard
          label="Seçili proje"
          value={selected ? num(selected.section_count, 0) : "—"}
          unit={selected ? "kesit" : undefined}
          icon={FolderOpen}
          hint={selected?.name ?? "Proje seçin"}
          tone="info"
        />
        <KpiCard
          label="KP sürekliliği"
          value={
            rawSections.length === 0
              ? "—"
              : kpContinuity.status === "pass"
                ? "Uyumlu"
                : kpContinuity.status === "fail"
                  ? "Uyuşmazlık"
                  : "Eksik KP"
          }
          icon={GitCompareArrows}
          tone={
            rawSections.length === 0
              ? undefined
              : kpContinuity.status === "pass"
                ? "pass"
                : kpContinuity.status === "fail"
                  ? "fail"
                  : "warning"
          }
          hint={
            rawSections.length > 0
              ? `${rawSections.length} kesit kontrol edildi`
              : "Kesit eklendiğinde denetlenir"
          }
        />
        <KpiCard
          label="Σ Section (Boru hattı)"
          value={
            rawSections.length === 0 || kpContinuity.totalSectionsLengthM <= 0
              ? "—"
              : num(kpContinuity.totalSectionsLengthM, 0)
          }
          unit={rawSections.length > 0 && kpContinuity.totalSectionsLengthM > 0 ? "m" : undefined}
          icon={Ruler}
          tone={
            rawSections.length === 0 || kpContinuity.totalSectionsLengthM <= 0
              ? undefined
              : kpContinuity.sumMatchesPipeline
                ? "pass"
                : "warning"
          }
          hint={
            kpContinuity.pipelineSpanM !== null && kpContinuity.pipelineSpanM > 0
              ? kpContinuity.sumMatchesPipeline
                ? `Hat KP aralığı (${num(kpContinuity.pipelineSpanM, 0)} m) ile eşit`
                : `Hat aralığı (${num(kpContinuity.pipelineSpanM, 0)} m) fark: ${kpContinuity.totalSectionsLengthM - kpContinuity.pipelineSpanM > 0 ? "+" : ""}${num(kpContinuity.totalSectionsLengthM - kpContinuity.pipelineSpanM, 0)} m`
              : rawSections.length > 0
                ? `${rawSections.length} kesit uzunluğu toplamı`
                : "Kesit eklendiğinde toplanır"
          }
        />
      </div>

      {showProjectScene && selected ? (
        <SectionCard
          title={`${selected.name} · Birleşik 3D Proje Görünümü`}
          description="Projedeki tüm test bölümleri (ayrı paftalardan yüklenenler dahil) KP ekseninde uç uca birleştirilerek görüntülenir. İstediğiniz segmente tıklayarak bölümü açabilirsiniz."
          icon={Layers}
          action={
            <div className="flex flex-wrap items-center gap-2">
              {projectSceneQuery.data ? (
                <>
                  <Badge tone={projectSceneQuery.data.continuity_ok ? "pass" : "warning"}>
                    {projectSceneQuery.data.section_count} bölüm ·{" "}
                    {num(projectSceneQuery.data.total_length_m, 0)} m
                  </Badge>
                  <Badge tone={projectSceneQuery.data.continuity_ok ? "pass" : "warning"}>
                    {projectSceneQuery.data.continuity_ok ? "Tam KP Zinciri" : "KP Farkı Var"}
                  </Badge>
                </>
              ) : null}
              <Button
                size="sm"
                variant="primary"
                onClick={() => {
                  setProject(selected);
                  setSceneScope("project");
                  setTab("field");
                }}
              >
                Saha Sekmesinde Aç
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowProjectScene(false)}>
                Gizle
              </Button>
            </div>
          }
          bodyClassName="pt-2"
        >
          {projectSceneQuery.data &&
          !projectSceneQuery.data.continuity_ok &&
          projectSceneQuery.data.warnings?.length ? (
            <div className="mb-3">
              <InlineNotice tone="warning" title="Proje KP Sürekliliği Uyarısı">
                <ul className="list-disc space-y-0.5 pl-4 text-[11.5px]">
                  {projectSceneQuery.data.warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </InlineNotice>
            </div>
          ) : null}
          {projectSceneQuery.isLoading && !projectSceneQuery.data ? (
            <div className="flex min-h-[260px] items-center justify-center text-xs text-[var(--text-muted)]">
              Proje genelindeki test bölümleri 3D görünümde birleştiriliyor...
            </div>
          ) : projectSceneQuery.data && projectSceneQuery.data.segments.length > 0 ? (
            <div className="scene-shell">
              <Suspense
                fallback={
                  <div className="flex min-h-[460px] items-center justify-center text-xs text-[var(--text-muted)]">
                    3D saha görünümü yükleniyor...
                  </div>
                }
              >
                <PipelineScene
                  data={projectSceneQuery.data}
                  className="min-h-[460px]"
                  onOpenSession={(sid) =>
                    openSession.mutate(sid, {
                      onSuccess: () => {
                        setSceneScope("section");
                        setTab("field");
                      },
                    })
                  }
                />
              </Suspense>
            </div>
          ) : (
            <EmptyState
              title="3D sahne oluşturulamadı"
              description="Seçili projede 3D geometri oluşturacak kesit verisi henüz yok."
              icon={Layers}
            />
          )}
        </SectionCard>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <SectionCard
          title="Projeler"
          description="Seçim kesit listesini filtreler."
          icon={Building2}
          action={<Badge tone="neutral">{projects.length}</Badge>}
        >
          {projects.length === 0 ? (
            <EmptyState
              title="Henüz proje yok"
              description="İlk projeyi oluşturun; kesitler bu proje altında saklanır."
              icon={Building2}
              action={
                <Button variant="primary" size="sm" icon={<Plus size={13} />} onClick={openCreateProject}>
                  Yeni proje
                </Button>
              }
            />
          ) : (
            <div className="space-y-2" role="list">
              {projects.map((project) => {
                const active = project.id === selected?.id;
                return (
                  <button
                    key={project.id}
                    type="button"
                    role="listitem"
                    className={`w-full rounded-xl border p-3 text-left transition-colors ${
                      active
                        ? "border-[color-mix(in_srgb,var(--primary)_45%,var(--border))] bg-[var(--primary-soft)]"
                        : "border-[var(--border)] bg-[var(--surface-2)] hover:bg-[var(--surface-3)]"
                    }`}
                    onClick={() => chooseProject(project)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate text-[12.5px] font-semibold text-[var(--text)]">
                          {project.name}
                        </span>
                        <span className="mt-0.5 block truncate font-mono text-[10px] text-[var(--text-faint)]">
                          {project.code || "kod yok"} · {project.client || "müşteri yok"}
                        </span>
                      </span>
                      <Badge tone={active ? "info" : "neutral"}>{project.section_count}</Badge>
                    </div>
                    <span className="mt-2 flex items-center justify-between text-[10px] text-[var(--text-faint)]">
                      <span>{relativeTime(project.updated_at)}</span>
                      <span className="inline-flex items-center gap-1">
                        Aç <ArrowRight size={10} />
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </SectionCard>

        <div className="space-y-4">
          <SectionCard
            title={selected ? selected.name : "Kesitler"}
            description={
              selected
                ? selected.description || "Proje açıklaması girilmedi."
                : "Tüm kayıtlı kesitler."
            }
            icon={Layers}
            action={
              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  size="lg"
                  variant={showProjectScene ? "primary" : "default"}
                  icon={<Layers size={15} />}
                  disabled={!selected || rawSections.length === 0}
                  aria-pressed={showProjectScene}
                  onClick={() => setShowProjectScene((prev) => !prev)}
                >
                  3D Birleşik Proje Görünümü
                </Button>
                <Button
                  size="lg"
                  icon={<FileScan size={15} />}
                  disabled={!selected}
                  onClick={openScanDialog}
                >
                  Plan-Profil Paftalarından Taslak Üret
                </Button>
                <Button
                  size="lg"
                  variant="primary"
                  icon={<Plus size={15} />}
                  disabled={!selected}
                  onClick={openCreateSectionDialog}
                >
                  Yeni kesit
                </Button>
                {selected ? (
                  <>
                    <Button size="sm" variant="ghost" icon={<Pencil size={12} />} onClick={() => openEditProject(selected)}>
                      Düzenle
                    </Button>
                    <Button size="sm" variant="danger" icon={<Trash2 size={12} />} onClick={() => setDeletingProject(selected)}>
                      Sil
                    </Button>
                  </>
                ) : null}
              </div>
            }
          >
            {selected ? (
              <div className="mb-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                  <p className="eyebrow">Proje kodu</p>
                  <p className="mt-1 truncate font-mono text-[11.5px] text-[var(--text-soft)]">{selected.code || "—"}</p>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                  <p className="eyebrow">Müşteri</p>
                  <p className="mt-1 truncate text-[11.5px] text-[var(--text-soft)]">{selected.client || "—"}</p>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                  <p className="eyebrow">Son güncelleme</p>
                  <p className="mt-1 truncate text-[11.5px] text-[var(--text-soft)]">{dateTime(selected.updated_at)}</p>
                </div>
              </div>
            ) : null}

            {rawSections.length > 0 ? (
              <div className="mb-3">
                <InlineNotice
                  tone={
                    kpContinuity.status === "pass"
                      ? "success"
                      : kpContinuity.status === "fail"
                        ? "danger"
                        : "warning"
                  }
                  title="Ardışık kesit KP süreklilik kontrolü"
                  icon={GitCompareArrows}
                >
                  <p>{kpContinuity.headline}</p>
                  {kpContinuity.issues.length > 0 ? (
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px]">
                      {kpContinuity.issues.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                  ) : null}
                </InlineNotice>
              </div>
            ) : null}

            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10.5px] text-[var(--text-faint)]">
                {sections.length} kesit · sıralama:
              </span>
              <div className="seg-control" role="group" aria-label="Kesit sıralaması">
                {[
                  { key: "kp" as const, label: "KP sırası" },
                  { key: "name" as const, label: "Kesit no" },
                  { key: "updated" as const, label: "Güncelleme" },
                  { key: "status" as const, label: "Durum" },
                ].map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className="seg-btn"
                    aria-pressed={sortKey === option.key}
                    onClick={() => setSortKey(option.key)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {sections.length === 0 ? (
              <EmptyState
                title="Bu projede kesit yok"
                description="Yeni kesit oluşturarak başlangıç/bitiş KP noktalarını, geometriyi ve test kayıtlarını bu proje altında toplayın."
                icon={Layers}
                action={
                  <Button variant="primary" size="sm" icon={<Plus size={13} />} disabled={!selected} onClick={openCreateSectionDialog}>
                    Yeni kesit
                  </Button>
                }
              />
            ) : (
              <div className="table-wrap scroll-thin">
                <table className="data">
                  <caption>
                    {selected ? `${selected.code || selected.name} · kesitler` : "Tüm kesitler"}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Kesit</th>
                      <th scope="col" className="num">Başlangıç KP</th>
                      <th scope="col" className="num">Bitiş KP</th>
                      <th scope="col">KP Sürekliliği</th>
                      <th scope="col">Durum</th>
                      <th scope="col">Form Takibi</th>
                      <th scope="col" className="num">Rev.</th>
                      <th scope="col">Güncelleme</th>
                      <th scope="col">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sections.map((session) => {
                      const meta = resolveSectionMeta(session);
                      const check = kpContinuity.byId[session.id];
                      const fs = session.forms_summary;
                      const formTone = !fs
                        ? "neutral"
                        : fs.failed_forms.length > 0
                          ? "fail"
                          : fs.complete
                            ? "pass"
                            : "warning";
                      return (
                        <tr key={session.id}>
                          <td>
                            <span className="block max-w-[260px] truncate font-medium text-[var(--text)]">
                              {meta.section_no ? `${meta.section_no} · ` : ""}
                              {meta.description || session.name}
                            </span>
                            <span className="mt-0.5 block font-mono text-[9.5px] text-[var(--text-faint)]">
                              {session.name} · {session.id.slice(0, 8)}
                            </span>
                          </td>
                          <td className="num font-mono">
                            {check?.startKp || normalizeKpText(meta.start_kp) || "—"}
                          </td>
                          <td className="num font-mono">
                            {check?.endKp || normalizeKpText(meta.end_kp) || "—"}
                          </td>
                          <td>
                            {check ? (
                              <div className="space-y-0.5">
                                <Badge tone={check.tone}>{check.badgeLabel}</Badge>
                                <span className="block max-w-[230px] text-[10px] leading-snug text-[var(--text-muted)]">
                                  {check.prevCheck
                                    ? `Önceki (${check.prevCheck.prevLabel} bitiş ${check.prevCheck.prevEndKp}) → ${
                                        check.prevCheck.matched
                                          ? "eşleşiyor"
                                          : `${check.prevCheck.deltaM > 0 ? "+" : ""}${Math.round(check.prevCheck.deltaM)} m fark`
                                      }`
                                    : check.lengthM !== null
                                      ? `Uzunluk: ${num(check.lengthM, 0)} m`
                                      : check.detail}
                                </span>
                              </div>
                            ) : (
                              <span className="text-[10.5px] text-[var(--text-faint)]">—</span>
                            )}
                          </td>
                          <td>
                            <Badge tone={statusTone(session.status)}>{statusLabel(session.status)}</Badge>
                          </td>
                          <td>
                            {fs ? (
                              <div className="space-y-1">
                                <div className="flex flex-wrap items-center gap-1">
                                  <Badge tone={formTone}>
                                    {fs.filled_required} / {fs.required_total} Form
                                  </Badge>
                                  {fs.supplementary_filled > 0 ? (
                                    <Badge tone="info">+{fs.supplementary_filled} Ek</Badge>
                                  ) : null}
                                </div>
                                {fs.findings_counts &&
                                (fs.findings_counts.passed +
                                  fs.findings_counts.warning +
                                  fs.findings_counts.failed >
                                  0) ? (
                                  <div className="flex flex-wrap gap-1 font-mono text-[9.5px]">
                                    <span className="tone-pass">✓{fs.findings_counts.passed}</span>
                                    {fs.findings_counts.warning > 0 ? (
                                      <span className="tone-warning">!{fs.findings_counts.warning}</span>
                                    ) : null}
                                    {fs.findings_counts.failed > 0 ? (
                                      <span className="text-[var(--danger)]">✕{fs.findings_counts.failed}</span>
                                    ) : null}
                                  </div>
                                ) : null}
                                {fs.key_metrics?.air_excess_pct !== undefined &&
                                fs.key_metrics?.air_excess_pct !== null ? (
                                  <span className="block font-mono text-[9.5px] text-[var(--text-muted)]">
                                    Hava %{num(fs.key_metrics.air_excess_pct, 2)}
                                    {fs.key_metrics.pa_minus_pt_bar !== undefined &&
                                    fs.key_metrics.pa_minus_pt_bar !== null
                                      ? ` · ΔP ${num(fs.key_metrics.pa_minus_pt_bar, 2)}b`
                                      : ""}
                                  </span>
                                ) : fs.failed_forms.length > 0 ? (
                                  <span className="block text-[10px] font-medium text-[var(--danger)]">
                                    {fs.failed_forms.length} form başarısız
                                  </span>
                                ) : fs.missing_required > 0 ? (
                                  <span className="block text-[10px] text-[var(--text-muted)]">
                                    {fs.missing_required} zorunlu eksik
                                  </span>
                                ) : (
                                  <span className="block text-[10px] text-[var(--text-muted)]">
                                    Tüm formlar tamam
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-[10.5px] text-[var(--text-faint)]">0 / 11</span>
                            )}
                          </td>
                          <td className="num">{session.revision}</td>
                          <td>
                            <span className="block text-[11px] text-[var(--text-soft)]">{relativeTime(session.updated_at)}</span>
                            <span className="block text-[9.5px] text-[var(--text-faint)]">{dateTime(session.updated_at)}</span>
                          </td>
                          <td>
                            <div className="flex flex-wrap items-center gap-1">
                              <Button size="sm" variant="ghost" icon={<FolderOpen size={11} />} onClick={() => openSection(session)}>
                                Aç
                              </Button>
                              <Button size="sm" variant="primary" icon={<FileCheck2 size={11} />} onClick={() => openSectionForms(session)}>
                                Sıralı İncele
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => setFormsModalSession(session)}>
                                Özet
                              </Button>
                              <Button size="sm" variant="ghost" icon={<Copy size={11} />} onClick={() => copySection(session)}>
                                Kopyala
                              </Button>
                              <Button size="sm" variant="danger" icon={<Trash2 size={11} />} onClick={() => setDeletingSection(session)}>
                                Sil
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <InlineNotice tone="info" title="Kesit kimliği ve KP kontrolü">
            Yeni kesit eklenirken bir önceki kesitin bitiş KP noktası otomatik olarak başlangıç KP
            alanına önerilir; ayrıca Geometri &amp; Saha sayfasındaki “Kesit kimliği ve KP aralığı”
            kartından da istediğiniz zaman düzenlenebilir.
          </InlineNotice>
        </div>
      </div>

      <Modal
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? "Projeyi düzenle" : "Yeni proje"}
        description="Proje adı zorunludur; kod ve müşteri bilgisi isteğe bağlıdır."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              Vazgeç
            </Button>
            <Button
              variant="primary"
              loading={createProject.isPending || updateProject.isPending}
              onClick={submitProject}
            >
              {editing ? "Kaydet" : "Projeyi oluştur"}
            </Button>
          </>
        }
      >
        <FieldGrid cols={2}>
          <TextField
            label="Proje adı"
            value={form.name}
            onChange={(value) => setForm((current) => ({ ...current, name: value }))}
            placeholder="Doğu Hattı Hidrostatik Testi"
            required
            maxLength={200}
          />
          <TextField
            label="Proje kodu"
            value={form.code}
            onChange={(value) => setForm((current) => ({ ...current, code: value }))}
            placeholder="PRJ-DOGU-12"
            maxLength={64}
          />
          <TextField
            label="Müşteri"
            value={form.client}
            onChange={(value) => setForm((current) => ({ ...current, client: value }))}
            placeholder="BOTAŞ"
            maxLength={200}
          />
          <TextField
            label="Açıklama"
            value={form.description}
            onChange={(value) => setForm((current) => ({ ...current, description: value }))}
            placeholder="Kısa kapsam notu"
          />
        </FieldGrid>
      </Modal>

      <Modal
        open={sectionDialogOpen}
        onClose={() => setSectionDialogOpen(false)}
        title="Yeni boru kesiti (section) oluştur"
        description={
          selected
            ? `${selected.name} (${selected.code || "proje"}) altına başlangıç ve bitiş KP noktalarıyla yeni kesit kaydedilir.`
            : "Başlangıç ve bitiş KP noktalarını girin."
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setSectionDialogOpen(false)}>
              Vazgeç
            </Button>
            <Button
              variant="primary"
              loading={createSession.isPending}
              onClick={submitCreateSection}
            >
              Kesiti oluştur ve aç
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {lastOrderedSection && lastOrderedSection.endM !== null ? (
            <div
              className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-[11.5px] ${
                modalMatchesPrev
                  ? "border-[var(--success-border)] bg-[var(--success-bg)]"
                  : "border-[var(--warning-border)] bg-[var(--warning-bg)]"
              }`}
            >
              {modalMatchesPrev ? (
                <CheckCircle2 size={14} className="mt-0.5 shrink-0 tone-pass" aria-hidden />
              ) : (
                <AlertTriangle size={14} className="mt-0.5 shrink-0 tone-warning" aria-hidden />
              )}
              <div>
                <p className="font-medium">
                  {modalMatchesPrev
                    ? `Önceki kesit (${lastOrderedSection.sectionLabel}) bitiş KP noktası (${lastOrderedSection.endKp}) ile yeni kesitin başlangıç KP noktası eşleşiyor.`
                    : `KP uyuşmazlığı: Önceki kesit (${lastOrderedSection.sectionLabel}) bitiş KP noktası ${lastOrderedSection.endKp} iken yeni kesit başlangıç KP noktası ${
                        modalStartM !== null ? formatKp(modalStartM) : sectionForm.start_kp || "—"
                      } (${
                        modalDeltaFromPrevM !== null
                          ? `${modalDeltaFromPrevM > 0 ? "+" : ""}${Math.round(modalDeltaFromPrevM)} m fark`
                          : "geçersiz KP"
                      }).`}
                </p>
                {!modalMatchesPrev ? (
                  <button
                    type="button"
                    className="mt-1 text-[10.5px] font-semibold text-[var(--primary)] underline"
                    onClick={() =>
                      setSectionForm((current) => ({
                        ...current,
                        start_kp: lastOrderedSection.endKp,
                      }))
                    }
                  >
                    Başlangıç KP&apos;yi {lastOrderedSection.endKp} olarak eşitle
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          <FieldGrid cols={3}>
            <TextField
              label="Kesit no"
              value={sectionForm.section_no}
              onChange={(value) => setSectionForm((current) => ({ ...current, section_no: value }))}
              placeholder="K-01"
              required
              maxLength={40}
            />
            <TextField
              label="Başlangıç KP"
              value={sectionForm.start_kp}
              onChange={(value) => setSectionForm((current) => ({ ...current, start_kp: value }))}
              placeholder="0+000"
              required
              maxLength={40}
              help={modalStartM !== null ? `${formatKp(modalStartM)} (${num(modalStartM, 0)} m)` : "Ör: 0+000"}
            />
            <TextField
              label="Bitiş KP"
              value={sectionForm.end_kp}
              onChange={(value) => setSectionForm((current) => ({ ...current, end_kp: value }))}
              placeholder="12+000"
              required
              maxLength={40}
              help={
                modalEndM !== null
                  ? `${formatKp(modalEndM)} (${num(modalEndM, 0)} m)${
                      modalSpanM !== null && modalSpanM > 0 ? ` · ΔKP ${num(modalSpanM, 0)} m` : ""
                    }`
                  : "Ör: 12+000"
              }
            />
          </FieldGrid>

          <FieldGrid cols={2}>
            <TextField
              label="Kesit açıklaması"
              value={sectionForm.description}
              onChange={(value) => setSectionForm((current) => ({ ...current, description: value }))}
              placeholder="Bölüm 12–13 · Doğu Hattı"
              maxLength={200}
            />
            <TextField
              label="Test tarihi"
              type="date"
              value={sectionForm.test_date}
              onChange={(value) => setSectionForm((current) => ({ ...current, test_date: value }))}
            />
          </FieldGrid>

          <TextField
            label="Not"
            value={sectionForm.notes}
            onChange={(value) => setSectionForm((current) => ({ ...current, notes: value }))}
            placeholder="Kısa saha notu"
            maxLength={240}
          />
        </div>
      </Modal>

      <PlanProfileScanModal
        open={scanDialogOpen}
        onClose={() => setScanDialogOpen(false)}
        selected={selected}
        rawSections={rawSections}
      />

      <ConfirmDialog
        open={Boolean(deletingProject)}
        title="Proje silinsin mi?"
        message={
          <span>
            <strong>{deletingProject?.name}</strong> ile birlikte bu projeye bağlı tüm test
            bölümleri ve BOTAŞ form kayıtları da silinecek.
          </span>
        }
        confirmLabel="Projeyi sil"
        danger
        onConfirm={() => {
          if (deletingProject) deleteProject.mutate(deletingProject.id);
        }}
        onClose={() => setDeletingProject(null)}
      />

      <ConfirmDialog
        open={Boolean(deletingSection)}
        title="Kesit silinsin mi?"
        message={
          <span>
            <strong>{deletingSection?.name}</strong> arşivlenecek. Bu işlem geri alınabilir kayıt
            bırakır ancak kesit listede görünmez.
          </span>
        }
        confirmLabel="Kesiti sil"
        danger
        onConfirm={() => {
          if (deletingSection) deleteSession.mutate(deletingSection.id);
        }}
        onClose={() => setDeletingSection(null)}
      />

      <SectionFormsModal
        session={formsModalSession}
        onClose={() => setFormsModalSession(null)}
        onOpenSection={openSection}
        onOpenSectionForm={openSectionForms}
      />
    </div>
  );
}
