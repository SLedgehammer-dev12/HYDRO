import { useMemo, useState } from "react";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Copy,
  FolderOpen,
  Layers,
  Pencil,
  Plus,
  Rows3,
  Trash2,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, KpiCard } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { ConfirmDialog, Modal } from "../components/ui/Dialog";
import { FieldGrid, TextField } from "../components/ui/Field";
import { EmptyState, InlineNotice } from "../components/ui/State";
import {
  useCreateProject,
  useCreateSession,
  useDeleteProject,
  useDeleteSection,
  useDuplicateSession,
  useOpenSession,
  useProjects,
  useSessions,
  useUpdateProject,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { createDefaultInputs } from "../lib/mock";
import { toApiInputs } from "../lib/normalize";
import { dateTime, num, relativeTime } from "../lib/format";
import type { Project, SectionMeta, SessionListItem, SessionStatus } from "../lib/types";

interface ProjectForm {
  name: string;
  code: string;
  client: string;
  description: string;
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
  const projectId = useAppStore((state) => state.projectId);
  const setProject = useAppStore((state) => state.setProject);
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
  const sectionsQuery = useSessions(selected?.id ?? null);
  const [sortKey, setSortKey] = useState<"name" | "updated" | "status">("name");
  const sections = useMemo(() => {
    const items = [...(sectionsQuery.data ?? [])];
    items.sort((a, b) => {
      if (sortKey === "updated") return b.updated_at.localeCompare(a.updated_at);
      if (sortKey === "status") return a.status.localeCompare(b.status) || a.name.localeCompare(b.name);
      return a.name.localeCompare(b.name, "tr");
    });
    return items;
  }, [sectionsQuery.data, sortKey]);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectForm>(EMPTY_FORM);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);
  const [deletingSection, setDeletingSection] = useState<SessionListItem | null>(null);

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

  function createSection() {
    if (!selected) return;
    const inputs = createDefaultInputs();
    const meta: SectionMeta = {
      ...inputs.section_meta,
      section_no: nextSectionNo(sections),
      description: selected.name,
      location: "",
      test_date: new Date().toISOString().slice(0, 10),
      test_type: "Hidrostatik test",
      notes: "",
    };
    inputs.section_meta = meta;
    const name = `${meta.section_no} · ${selected.code || selected.name}`;
    setProject(selected);
    applySessionInputs(inputs);
    createSession.mutate(
      { name, inputs: toApiInputs(inputs), projectId: selected.id },
      {
        onSuccess: ({ session }) => {
          setProject(selected);
          setSessionMeta({
            id: session.id,
            name: session.name,
            status: session.status,
            revision: session.revision,
          });
          markSaved(session.revision);
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

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Projeler & Kesitler"
        title="Proje kayıtları ve kesit envanteri"
        description="Projeyi seçin, kesitleri sıralayın ve istediğiniz kesiti yeniden açın. Kesit kimliği Geometri & Saha sayfasında düzenlenir."
        meta={
          <>
            <Badge tone="info">{projects.length} proje</Badge>
            <Badge tone="neutral">{totalSections} kesit</Badge>
            {selected ? <span className="chip">{selected.code || "kod yok"}</span> : null}
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon={<Rows3 size={14} />} onClick={() => setTab("geometry")}>
              Geometri & Saha
            </Button>
            <Button size="lg" variant="primary" icon={<Plus size={15} />} onClick={openCreateProject}>
              Yeni proje
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
          label="Aktif kesit"
          value={sections.find((item) => item.status === "active") ? "Var" : "—"}
          icon={CheckCircle2}
          hint={selected ? `${selected.code || "kod yok"} · ${sections.length} kayıt` : "Kesit seçilmedi"}
        />
      </div>

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
                <Button size="sm" variant="primary" icon={<Plus size={12} />} disabled={!selected} onClick={createSection}>
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

            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10.5px] text-[var(--text-faint)]">
                {sections.length} kesit · sıralama:
              </span>
              <div className="seg-control" role="group" aria-label="Kesit sıralaması">
                {[
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
                description="Yeni kesit oluşturarak geometri, hava içerik ve basınç değişim kayıtlarını bu proje altında toplayın."
                icon={Layers}
                action={
                  <Button variant="primary" size="sm" icon={<Plus size={13} />} disabled={!selected} onClick={createSection}>
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
                      <th scope="col">Durum</th>
                      <th scope="col" className="num">Rev.</th>
                      <th scope="col">Güncelleme</th>
                      <th scope="col">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sections.map((session) => (
                      <tr key={session.id}>
                        <td>
                          <span className="block max-w-[320px] truncate font-medium text-[var(--text)]">{session.name}</span>
                          <span className="mt-0.5 block font-mono text-[9.5px] text-[var(--text-faint)]">{session.id.slice(0, 8)}</span>
                        </td>
                        <td>
                          <Badge tone={statusTone(session.status)}>{statusLabel(session.status)}</Badge>
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
                            <Button size="sm" variant="ghost" icon={<Copy size={11} />} onClick={() => copySection(session)}>
                              Kopyala
                            </Button>
                            <Button size="sm" variant="danger" icon={<Trash2 size={11} />} onClick={() => setDeletingSection(session)}>
                              Sil
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <InlineNotice tone="info" title="Kesit kimliği">
            Kesit numarası, konum ve test tarihi Geometri & Saha sayfasındaki “Kesit kimliği”
            kartından düzenlenir. Kaydet düğmesi kesiti seçili projeye bağlar.
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

      <ConfirmDialog
        open={Boolean(deletingProject)}
        title="Proje silinsin mi?"
        message={
          <span>
            <strong>{deletingProject?.name}</strong> arşivlenecek. Projeye bağlı kesitler silinmez;
            proje bağlantıları kaldırılır.
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
    </div>
  );
}
