import { useId, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  FileScan,
  FileSpreadsheet,
  FolderOpen,
  Layers,
  Loader2,
  Plus,
  Ruler,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { SectionCard, KpiCard } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { FieldGrid, NumberField, SelectField, TextField } from "../../../components/ui/Field";
import { InlineNotice } from "../../../components/ui/State";
import {
  useCommitPlanProfile,
  useCreateProject,
  useProjects,
  useSessions,
} from "../../../hooks/queries";
import { api } from "../../../lib/api";
import { useAppStore } from "../../../store/useAppStore";
import { formatKp, mergePlanProfileScans, parseKpMeters, pickBestDetectedProjectName } from "../../../lib/kp";
import { num } from "../../../lib/format";
import type { DraftSectionItem, PlanProfileScanResponse } from "../../../lib/types";

type QueueStatus = "pending" | "scanning" | "done" | "error";

interface FileQueueItem {
  id: string;
  file: File;
  status: QueueStatus;
  sectionCount?: number;
  error?: string;
}

function fileKey(file: File): string {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function strategyLabel(strategy: PlanProfileScanResponse["strategy"]): string {
  if (strategy === "cad_profile") return "CAD Pafta Sınırları";
  if (strategy === "explicit") return "Açık Kesit Tanımları";
  return "Otomatik KP Bölme";
}

export default function PlanProfilePanel() {
  const queryClient = useQueryClient();
  const projectsQuery = useProjects();
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const activeProjectId = useAppStore((s) => s.projectId);
  const backend = useAppStore((s) => s.backend);
  const setProject = useAppStore((s) => s.setProject);
  const setTab = useAppStore((s) => s.setTab);
  const setSceneScope = useAppStore((s) => s.setSceneScope);
  const pushToast = useAppStore((s) => s.pushToast);

  const createProject = useCreateProject();
  const commitPlanProfile = useCommitPlanProfile();

  const [projectMode, setProjectMode] = useState<"existing" | "new">("existing");
  const [targetProjectId, setTargetProjectId] = useState<string>(activeProjectId ?? "");
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectCode, setNewProjectCode] = useState("");

  const [fileQueue, setFileQueue] = useState<FileQueueItem[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgressText, setScanProgressText] = useState("");
  const [scannedDoneCount, setScannedDoneCount] = useState(0);
  const [maxSectionLengthM, setMaxSectionLengthM] = useState<number>(12000);
  const [maxElevDiffM, setMaxElevDiffM] = useState<string>("");
  const [scanResult, setScanResult] = useState<PlanProfileScanResponse | null>(null);
  const [draftRows, setDraftRows] = useState<DraftSectionItem[]>([]);
  const [createdCount, setCreatedCount] = useState<number | null>(null);

  const fileInputId = useId();
  const appendInputId = useId();

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === (targetProjectId || activeProjectId)) ?? projects[0] ?? null,
    [projects, targetProjectId, activeProjectId],
  );
  const existingSessionsQuery = useSessions(selectedProject?.id ?? null);
  const existingSessions = existingSessionsQuery.data ?? [];

  function addFilesToQueue(files: FileList | File[] | null) {
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    if (incoming.length > 1) {
      incoming.sort((a, b) => a.name.localeCompare(b.name, "tr", { numeric: true }));
    }
    setFileQueue((prev) => {
      const seen = new Set(prev.map((item) => fileKey(item.file)));
      const next = [...prev];
      for (const file of incoming) {
        const key = fileKey(file);
        if (!seen.has(key)) {
          seen.add(key);
          next.push({ id: key, file, status: "pending" });
        }
      }
      return next;
    });
    setCreatedCount(null);
  }

  function removeFileFromQueue(id: string) {
    if (isScanning) return;
    setFileQueue((prev) => prev.filter((item) => item.id !== id));
    setCreatedCount(null);
  }

  function clearQueue() {
    if (isScanning) return;
    setFileQueue([]);
    setScanResult(null);
    setDraftRows([]);
    setCreatedCount(null);
    setScanProgressText("");
    setScannedDoneCount(0);
  }

  async function runScan() {
    if (fileQueue.length === 0) {
      pushToast("error", "Dosya seçilmedi", "Önce bir veya daha fazla Plan-Profil paftası seçin.");
      return;
    }
    setIsScanning(true);
    setCreatedCount(null);
    setScannedDoneCount(0);
    setFileQueue((prev) =>
      prev.map((item) => ({ ...item, status: "pending", sectionCount: undefined, error: undefined })),
    );

    const elevNum = maxElevDiffM.trim() ? Number(maxElevDiffM) : null;
    const validElev = elevNum && Number.isFinite(elevNum) && elevNum > 0 ? elevNum : null;

    const completedScans: PlanProfileScanResponse[] = [];
    for (let idx = 0; idx < fileQueue.length; idx += 1) {
      const item = fileQueue[idx];
      setScanProgressText(`Pafta taranıyor: ${idx + 1} / ${fileQueue.length} — ${item.file.name}`);
      setFileQueue((prev) =>
        prev.map((entry, eIdx) => (eIdx === idx ? { ...entry, status: "scanning" } : entry)),
      );

      try {
        const res = await api.scanPlanProfile({
          file: item.file,
          maxSectionLengthM,
          maxElevationDiffM: validElev,
        });
        completedScans.push(res);
        setFileQueue((prev) =>
          prev.map((entry, eIdx) =>
            eIdx === idx
              ? { ...entry, status: "done", sectionCount: res.draft_sections.length }
              : entry,
          ),
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Tarama hatası";
        setFileQueue((prev) =>
          prev.map((entry, eIdx) => (eIdx === idx ? { ...entry, status: "error", error: msg } : entry)),
        );
      }
      setScannedDoneCount(idx + 1);
    }

    setIsScanning(false);

    if (completedScans.length === 0) {
      setScanProgressText("Hiçbir pafta okunamadı.");
      pushToast("error", "Paftalar okunamadı", "Yüklenen paftaların hiçbiri çözümlenemedi.");
      return;
    }

    let targetExisting = projectMode === "existing" ? existingSessions : [];
    const allSim = completedScans.flatMap((s) => s.similar_projects ?? []);
    const exact = allSim.find((p) => p.exact_match || p.similarity >= 0.9);
    const detectedName = pickBestDetectedProjectName(
      completedScans.map((s) => s.detected_project_name),
    );

    if (exact) {
      setProjectMode("existing");
      setTargetProjectId(exact.id);
      setShowNewProject(false);
      if (exact.id !== selectedProject?.id && backend === "online") {
        try {
          const resp = await queryClient.fetchQuery({
            queryKey: ["sessions", exact.id],
            queryFn: async () => (await api.sessions(exact.id)).items,
          });
          targetExisting = resp;
        } catch {
          targetExisting = [];
        }
      }
    } else if (detectedName) {
      setNewProjectName(detectedName);
      if (allSim.length > 0) {
        setProjectMode("existing");
        setTargetProjectId(allSim[0].id);
        setShowNewProject(false);
        if (allSim[0].id !== selectedProject?.id && backend === "online") {
          try {
            const resp = await queryClient.fetchQuery({
              queryKey: ["sessions", allSim[0].id],
              queryFn: async () => (await api.sessions(allSim[0].id)).items,
            });
            targetExisting = resp;
          } catch {
            targetExisting = [];
          }
        }
      } else {
        setProjectMode("new");
        setShowNewProject(true);
        targetExisting = [];
      }
    }

    const { mergedScan, drafts } = mergePlanProfileScans(completedScans, targetExisting);
    setScanResult(mergedScan);
    setDraftRows(drafts);
    setScanProgressText(
      `${completedScans.length} / ${fileQueue.length} pafta tarandı · ${drafts.length} taslak test bölümü birleştirildi.`,
    );
    pushToast(
      "success",
      completedScans.length > 1 ? "Paftalar sırayla tarandı" : "Pafta tarandı",
      `${completedScans.length} paftadan toplam ${drafts.length} taslak test bölümü (${strategyLabel(mergedScan.strategy)}) çıkarıldı.`,
    );
  }

  function updateRow(index: number, patch: Partial<DraftSectionItem>) {
    setDraftRows((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row;
        const next = { ...row, ...patch };
        const sm = parseKpMeters(next.start_kp);
        const em = parseKpMeters(next.end_kp);
        if (sm !== null && em !== null) {
          next.start_m = sm;
          next.end_m = em;
          next.length_m = Math.max(0, Math.round((em - sm) * 100) / 100);
          if (
            (patch.start_kp !== undefined || patch.end_kp !== undefined) &&
            em > sm &&
            scanResult?.profile_points &&
            scanResult.profile_points.length >= 2
          ) {
            const globalPts = [...scanResult.profile_points].sort((a, b) => a.station_m - b.station_m);
            const interp = (target: number): number | null => {
              if (target <= globalPts[0].station_m) return globalPts[0].elevation_m;
              const last = globalPts[globalPts.length - 1];
              if (target >= last.station_m) return last.elevation_m;
              for (let k = 1; k < globalPts.length; k += 1) {
                const p0 = globalPts[k - 1];
                const p1 = globalPts[k];
                if (target <= p1.station_m) {
                  const span = p1.station_m - p0.station_m;
                  return span > 1e-6
                    ? p0.elevation_m + ((p1.elevation_m - p0.elevation_m) * (target - p0.station_m)) / span
                    : p1.elevation_m;
                }
              }
              return last.elevation_m;
            };
            const startEl = interp(sm);
            const endEl = interp(em);
            const sliced: Array<{ station_m: number; elevation_m: number }> = [];
            if (startEl !== null) sliced.push({ station_m: 0, elevation_m: Math.round(startEl * 100) / 100 });
            for (const pt of globalPts) {
              if (pt.station_m > sm && pt.station_m < em) {
                sliced.push({
                  station_m: Math.round((pt.station_m - sm) * 100) / 100,
                  elevation_m: Math.round(pt.elevation_m * 100) / 100,
                });
              }
            }
            if (endEl !== null) {
              sliced.push({
                station_m: Math.round((em - sm) * 100) / 100,
                elevation_m: Math.round(endEl * 100) / 100,
              });
            }
            if (sliced.length >= 2) {
              next.profile_points = sliced;
              next.start_elevation_m = sliced[0].elevation_m;
              next.end_elevation_m = sliced[sliced.length - 1].elevation_m;
              next.highest_elevation_m = Math.round(Math.max(...sliced.map((p) => p.elevation_m)) * 10) / 10;
              next.lowest_elevation_m = Math.round(Math.min(...sliced.map((p) => p.elevation_m)) * 10) / 10;
            }
          }
        }
        return next;
      }),
    );
  }

  function addEmptyRow() {
    const last = draftRows[draftRows.length - 1];
    const startKp = last ? last.end_kp : "0+000";
    const sm = parseKpMeters(startKp) ?? 0;
    const em = sm + 5000;
    const endKp = formatKp(em);
    setDraftRows((prev) => [
      ...prev,
      {
        section_no: `BÖLÜM ${prev.length + 1}`,
        start_kp: startKp,
        end_kp: endKp,
        start_m: sm,
        end_m: em,
        length_m: 5000,
        description: `Plan-Profil Taslak Kesit BÖLÜM ${prev.length + 1} (KP ${startKp} – ${endKp})`,
        start_elevation_m: null,
        end_elevation_m: null,
        highest_elevation_m: null,
        lowest_elevation_m: null,
        outside_diameter_mm: scanResult?.pipe_meta.outside_diameter_mm ?? null,
        wall_thickness_mm: scanResult?.pipe_meta.wall_thickness_mm ?? null,
        design_pressure_bar: scanResult?.pipe_meta.design_pressure_bar ?? null,
        material_grade: scanResult?.pipe_meta.material_grade ?? "",
        smys_mpa: scanResult?.pipe_meta.smys_mpa ?? null,
        prev_end_kp: last ? last.end_kp : null,
        continuity_ok: true,
        continuity_note: "Manuel eklendi",
      },
    ]);
  }

  function removeRow(index: number) {
    setDraftRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleCreateNewProject() {
    if (!newProjectName.trim()) {
      pushToast("error", "Proje adı gerekli", "Yeni proje için bir ad girin.");
      return;
    }
    if (draftRows.length > 0) {
      commitPlanProfile.mutate(
        {
          project_id: null,
          project_name: newProjectName.trim(),
          project_code: newProjectCode.trim() || null,
          sections: draftRows,
        },
        {
          onSuccess: (res) => {
            setCreatedCount(res.created_count + (res.updated_count ?? 0));
            setTargetProjectId(res.project.id);
            setProject(res.project);
            setShowNewProject(false);
            setProjectMode("existing");
            setNewProjectName("");
            setNewProjectCode("");
          },
          onError: (err) => {
            pushToast("error", "Kayıt başarısız", err.message);
          },
        },
      );
      return;
    }
    createProject.mutate(
      {
        name: newProjectName.trim(),
        code: newProjectCode.trim(),
        client: "",
        description: fileQueue.length
          ? `Plan-Profil paftalarından oluşturuldu: ${fileQueue.map((item) => item.file.name).join(", ")}`
          : "",
      },
      {
        onSuccess: (created) => {
          setTargetProjectId(created.id);
          setProject(created);
          setShowNewProject(false);
          setProjectMode("existing");
          setNewProjectName("");
          setNewProjectCode("");
          pushToast("success", "Proje oluşturuldu", `${created.name} hedef proje olarak seçildi.`);
        },
        onError: (err) => {
          pushToast("error", "Proje oluşturulamadı", err.message);
        },
      },
    );
  }

  function commitSectionsToProject() {
    if (draftRows.length === 0) {
      pushToast("error", "Kesit yok", "Oluşturulacak en az bir test bölümü olmalıdır.");
      return;
    }
    const useNewProject = projectMode === "new" || showNewProject;
    if (useNewProject) {
      if (!newProjectName.trim()) {
        pushToast("error", "Proje adı yok", "Yeni proje oluşturmak için proje adı girin.");
        return;
      }
    } else if (!selectedProject) {
      pushToast("error", "Hedef proje yok", "Önce kayıtlı bir proje seçin veya yeni proje oluşturun.");
      return;
    }

    commitPlanProfile.mutate(
      {
        project_id: useNewProject ? null : selectedProject?.id ?? null,
        project_name: useNewProject ? newProjectName.trim() : null,
        project_code: useNewProject && newProjectCode.trim() ? newProjectCode.trim() : null,
        sections: draftRows,
      },
      {
        onSuccess: (res) => {
          setCreatedCount(res.created_count + (res.updated_count ?? 0));
          setTargetProjectId(res.project.id);
          setProject(res.project);
          setShowNewProject(false);
          setProjectMode("existing");
        },
        onError: (err) => {
          pushToast("error", "Kayıt başarısız", err.message);
        },
      },
    );
  }

  const totalDraftLength = useMemo(
    () => draftRows.reduce((acc, row) => acc + (Number(row.length_m) || 0), 0),
    [draftRows],
  );
  const showSourceColumn = useMemo(
    () => fileQueue.length > 1 || draftRows.some((row) => Boolean(row.source_file)),
    [fileQueue.length, draftRows],
  );

  return (
    <div className="space-y-4">
      <SectionCard
        title="Plan-Profil Paftası Tarama ve Otomatik Bölüm (Section) Üretimi"
        description="AutoCAD / PDF plan-profil paftalarındaki KP ekseni, dikey bölüm sınırları (BÖLÜM 1..N) ve zemin kotlarını okur; her bölümü ayrı paftalarla da gelse sırayla tarayıp hedef projede birleştirir."
        icon={FileScan}
      >
        <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          {/* Sol: Çoklu dosya yükleme ve tarama parametreleri */}
          <div className="space-y-3">
            <div className="relative">
              <input
                id={fileInputId}
                type="file"
                multiple
                accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.tif,.tiff"
                className="visually-hidden"
                onChange={(e) => {
                  addFilesToQueue(e.target.files);
                  e.target.value = "";
                }}
              />
              <label
                htmlFor={fileInputId}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  addFilesToQueue(e.dataTransfer.files);
                }}
                className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-2)] px-4 py-5 text-center transition-colors hover:border-[var(--primary)] hover:bg-[var(--surface-3)] [input:focus-visible+&]:outline [input:focus-visible+&]:outline-2 [input:focus-visible+&]:outline-offset-2 [input:focus-visible+&]:outline-[var(--focus)]"
              >
                <Upload size={22} className="mb-2 text-[var(--primary)]" aria-hidden />
                <span className="text-[13px] font-medium text-[var(--text)]">
                  {fileQueue.length > 0
                    ? `${fileQueue.length} pafta seçildi (sürükleyip bırakarak veya tıklayarak ekleyebilirsiniz)`
                    : "Bir veya birden fazla Plan-Profil paftası (.pdf / .dwg / .dxf) seçin veya sürükleyin"}
                </span>
                <span className="mt-1 text-[11px] text-[var(--text-muted)]">
                  Her test bölümü ayrı paftadaysa tümünü birden veya sırayla ekleyebilirsiniz · dosya başına en fazla 500 MB.
                </span>
              </label>
            </div>

            {fileQueue.length > 0 ? (
              <div className="space-y-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold text-[var(--text)]">
                    Tarama Kuyruğu ({fileQueue.length} pafta)
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <input
                        id={appendInputId}
                        type="file"
                        multiple
                        accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.tif,.tiff"
                        className="visually-hidden"
                        disabled={isScanning}
                        onChange={(e) => {
                          addFilesToQueue(e.target.files);
                          e.target.value = "";
                        }}
                      />
                      <label
                        htmlFor={appendInputId}
                        className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-soft)] hover:border-[var(--primary)] hover:text-[var(--text)] [input:focus-visible+&]:outline [input:focus-visible+&]:outline-2 [input:focus-visible+&]:outline-offset-2 [input:focus-visible+&]:outline-[var(--focus)]"
                      >
                        <Plus size={12} aria-hidden />
                        Başka Pafta Ekle
                      </label>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={isScanning}
                      onClick={clearQueue}
                    >
                      Listeyi Temizle
                    </Button>
                  </div>
                </div>

                <ul className="max-h-40 space-y-1.5 overflow-y-auto scroll-thin pr-1">
                  {fileQueue.map((item, idx) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-1.5 text-[11.5px]"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <FileSpreadsheet size={13} className="shrink-0 text-[var(--text-muted)]" aria-hidden />
                        <span className="font-mono text-[10px] text-[var(--text-faint)]">#{idx + 1}</span>
                        <span className="truncate font-medium text-[var(--text)]" title={item.file.name}>
                          {item.file.name}
                        </span>
                        <span className="shrink-0 text-[10px] text-[var(--text-faint)]">
                          ({(item.file.size / 1024).toFixed(0)} KB)
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        {item.status === "scanning" ? (
                          <Badge tone="info">Taranıyor...</Badge>
                        ) : item.status === "done" ? (
                          <Badge tone="pass">{item.sectionCount ?? 0} bölüm</Badge>
                        ) : item.status === "error" ? (
                          <span title={item.error}>
                            <Badge tone="fail">Hata</Badge>
                          </span>
                        ) : (
                          <Badge tone="neutral">Bekliyor</Badge>
                        )}
                        <button
                          type="button"
                          disabled={isScanning}
                          onClick={() => removeFileFromQueue(item.id)}
                          aria-label={`${item.file.name} paftasını kaldır`}
                          className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger)] disabled:opacity-40"
                        >
                          <X size={12} aria-hidden />
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>

                {isScanning || scanProgressText ? (
                  <div className="space-y-1 pt-1" role="status" aria-live="polite">
                    {isScanning ? (
                      <progress
                        value={scannedDoneCount}
                        max={fileQueue.length}
                        className="h-1.5 w-full accent-[var(--primary)]"
                      />
                    ) : null}
                    <p className="text-[11px] text-[var(--text-muted)]">{scanProgressText}</p>
                  </div>
                ) : null}
              </div>
            ) : null}

            <FieldGrid cols={2}>
              <NumberField
                label="Yedek otomatik bölme sınırı (m)"
                value={maxSectionLengthM}
                onChange={(v) => setMaxSectionLengthM(v ?? 12000)}
                min={500}
                max={25000}
                step={500}
                help="Yalnızca paftada BÖLÜM / kesit sınırları yoksa devreye girer."
              />
              <TextField
                label="Maks. kot farkı sınırı (m, ops.)"
                value={maxElevDiffM}
                onChange={setMaxElevDiffM}
                placeholder="Ör: 150"
                help="Otomatik bölmede statik yük sınırı."
              />
            </FieldGrid>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="lg"
                variant="primary"
                icon={isScanning ? <Loader2 size={15} className="animate-spin" /> : <FileScan size={15} />}
                disabled={fileQueue.length === 0 || isScanning}
                onClick={() => void runScan()}
              >
                {isScanning
                  ? `Taranıyor (${scannedDoneCount}/${fileQueue.length})...`
                  : fileQueue.length > 1
                    ? `${fileQueue.length} Paftayı Sırayla Tara & Birleştir`
                    : "Paftayı Tara & Bölümleri Çıkar"}
              </Button>
            </div>
          </div>

          {/* Sağ: Hedef proje seçimi */}
          <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--text)]">
                <Building2 size={14} className="text-[var(--primary)]" />
                Hedef Proje
              </div>
              <Button
                size="sm"
                variant="ghost"
                icon={<Plus size={12} />}
                onClick={() => {
                  if (showNewProject || projectMode === "new") {
                    setShowNewProject(false);
                    setProjectMode("existing");
                  } else {
                    setShowNewProject(true);
                    setProjectMode("new");
                  }
                }}
              >
                {showNewProject || projectMode === "new" ? "Vazgeç" : "Yeni proje"}
              </Button>
            </div>

            {showNewProject || projectMode === "new" ? (
              <div className="space-y-2 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2.5">
                <TextField
                  label="Proje adı (yeni proje)"
                  value={newProjectName}
                  onChange={setNewProjectName}
                  placeholder="Ör: 10&quot; KAĞIZMAN DGBH"
                />
                <TextField
                  label="Proje kodu (opsiyonel)"
                  value={newProjectCode}
                  onChange={setNewProjectCode}
                  placeholder="Ör: KGZ-01"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={createProject.isPending || commitPlanProfile.isPending}
                    onClick={handleCreateNewProject}
                  >
                    {createProject.isPending || commitPlanProfile.isPending
                      ? "Oluşturuluyor..."
                      : draftRows.length > 0
                        ? `Projeyi + ${draftRows.length} Bölümü Oluştur`
                        : "Şimdi Oluştur ve Seç"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setShowNewProject(false);
                      setProjectMode("existing");
                    }}
                  >
                    Mevcut Projelerden Seç
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <SelectField
                  label="Bölümlerin ekleneceği proje"
                  value={selectedProject?.id ?? ""}
                  onChange={(val) => {
                    setProjectMode("existing");
                    setTargetProjectId(val);
                    const found = projects.find((p) => p.id === val);
                    if (found) setProject(found);
                  }}
                  options={
                    projects.length > 0
                      ? projects.map((p) => ({
                          value: p.id,
                          label: `${p.code ? `[${p.code}] ` : ""}${p.name} (${p.section_count} bölüm)`,
                        }))
                      : [{ value: "", label: "Kayıtlı proje bulunamadı — yeni oluşturun" }]
                  }
                />
                {selectedProject && draftRows.length > 0 ? (
                  <Button
                    size="sm"
                    variant="primary"
                    icon={
                      commitPlanProfile.isPending ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <CheckCircle2 size={13} />
                      )
                    }
                    disabled={commitPlanProfile.isPending}
                    onClick={commitSectionsToProject}
                  >
                    {commitPlanProfile.isPending
                      ? "Kaydediliyor..."
                      : `${selectedProject.name} Projesine ${draftRows.length} Bölümü Kaydet`}
                  </Button>
                ) : null}
              </div>
            )}

            {scanResult?.detected_project_name ? (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2.5 text-[11px]">
                <div className="flex flex-wrap items-center justify-between gap-1.5">
                  <span className="font-semibold text-[var(--text)]">
                    Paftadan Okunan Proje:
                  </span>
                  <Badge tone="pass">{scanResult.detected_project_name}</Badge>
                </div>
                {(scanResult.similar_projects ?? []).length > 0 ? (
                  <div className="mt-2 space-y-1">
                    <span className="block text-[10.5px] text-[var(--text-muted)]">
                      %70+ benzer kayıtlı projeler:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {(scanResult.similar_projects ?? []).map((cand) => (
                        <button
                          key={cand.id}
                          type="button"
                          onClick={() => {
                            setProjectMode("existing");
                            setShowNewProject(false);
                            setTargetProjectId(cand.id);
                          }}
                          className={`rounded-md border px-2 py-0.5 text-[10.5px] font-medium ${
                            projectMode === "existing" && targetProjectId === cand.id
                              ? "border-[var(--primary)] bg-[var(--surface-2)] text-[var(--text)]"
                              : "border-[var(--border)] text-[var(--text-muted)]"
                          }`}
                        >
                          {cand.name} (%{Math.round(cand.similarity_pct)})
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : scanResult ? (
              <InlineNotice tone="warning" title="Paftadan Proje Adı Okunamadı">
                Kayıtlı bir projeyi seçebilir veya “Yeni proje” ile yeni proje adı girerek bölümleri oluşturabilirsiniz.
              </InlineNotice>
            ) : null}

            <p className="text-[11px] leading-relaxed text-[var(--text-muted)]">
              Paftadan çıkarılan her <strong className="text-[var(--text)]">Test Bölümü (Section)</strong>, başlangıç/bitiş KP sınırları, zemin kotları ve her bölüm için <strong className="text-[var(--text)]">11 zorunlu BOTAŞ formu boş şablon slotu</strong> ile birlikte veritabanına kaydedilir.
            </p>
          </div>
        </div>
      </SectionCard>

      {scanResult ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Tarama Yöntemi"
              value={strategyLabel(scanResult.strategy)}
              icon={FileScan}
              tone="info"
              hint={scanResult.extraction_method}
            />
            <KpiCard
              label="Tespit Edilen Bölüm"
              value={num(draftRows.length, 0)}
              unit="section"
              icon={Layers}
              tone="pass"
              hint={`KP ${scanResult.min_kp} → ${scanResult.max_kp}`}
            />
            <KpiCard
              label="Toplam Uzunluk"
              value={num(totalDraftLength, 0)}
              unit="m"
              icon={Ruler}
              hint={`${scanResult.station_count} KP istasyonu · ${scanResult.elevation_point_count} kot noktası`}
            />
            <KpiCard
              label="KP Sürekliliği"
              value={scanResult.continuity_ok ? "Tam Zincir" : "Kontrol Gerekli"}
              icon={CheckCircle2}
              tone={scanResult.continuity_ok ? "pass" : "warning"}
              hint={
                scanResult.pipe_meta.outside_diameter_mm
                  ? `Tespit edilen çap: ${num(scanResult.pipe_meta.outside_diameter_mm, 1)} mm`
                  : "Bölüm sınırları ardışık eşleşti"
              }
            />
          </div>

          {scanResult.strategy === "cad_profile" || scanResult.strategy === "explicit" ? (
            <InlineNotice tone="info" title="Pafta Üzerindeki Gerçek Bölüm Sınırları Okundu">
              <p className="text-[11.5px]">
                Otomatik uzunluk bölmesi kullanılmadı; {draftRows.length} adet test bölümünün başlangıç ve bitiş KP noktaları doğrudan pafta sınırlarından çıkarıldı.
              </p>
            </InlineNotice>
          ) : null}

          {scanResult.warnings.length > 0 ? (
            <InlineNotice tone="warning" title="Tarama Notları">
              <ul className="list-disc pl-4 text-[11.5px]">
                {scanResult.warnings.map((w, idx) => (
                  <li key={`${w}-${idx}`}>{w}</li>
                ))}
              </ul>
            </InlineNotice>
          ) : null}

          {createdCount !== null ? (
            <InlineNotice tone="success" title={`${createdCount} Test Bölümü (Section) veritabanına kaydedildi`}>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  icon={<Layers size={13} />}
                  onClick={() => {
                    setSceneScope("project");
                    setTab("field");
                  }}
                >
                  Tüm Projeyi 3D Görünümde Aç
                </Button>
                <Button size="sm" variant="ghost" icon={<FolderOpen size={13} />} onClick={() => setTab("projects")}>
                  Projeler & Kesitler'de Görüntüle
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setTab("geometry")}>
                  Geometri & Saha'ya Geç
                </Button>
              </div>
            </InlineNotice>
          ) : null}

          <SectionCard
            title="Çıkarılan Test Bölümleri (Düzenlenebilir Taslak)"
            description="Kaydetmeden önce bölüm adlarını, KP sınırlarını veya açıklamaları düzenleyebilirsiniz."
            icon={Layers}
            action={
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="ghost" icon={<Plus size={13} />} onClick={addEmptyRow}>
                  Satır Ekle
                </Button>
                <Button
                  size="lg"
                  variant="primary"
                  icon={commitPlanProfile.isPending ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                  disabled={
                    draftRows.length === 0 ||
                    commitPlanProfile.isPending ||
                    ((projectMode === "new" || showNewProject) ? !newProjectName.trim() : !selectedProject)
                  }
                  onClick={commitSectionsToProject}
                >
                  {commitPlanProfile.isPending
                    ? "Oluşturuluyor..."
                    : `${draftRows.length} Bölümü + 11 Form Slotunu Oluştur`}
                </Button>
              </div>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[780px] border-collapse text-left text-[12px]">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
                    <th className="py-2 pr-3">Bölüm No</th>
                    <th className="py-2 pr-3">Başlangıç KP</th>
                    <th className="py-2 pr-3">Bitiş KP</th>
                    <th className="py-2 pr-3 text-right">Uzunluk (m)</th>
                    <th className="py-2 pr-3">Kot Aralığı (m)</th>
                    {showSourceColumn ? <th className="py-2 pr-3">Kaynak Pafta</th> : null}
                    <th className="py-2 pr-3">Açıklama</th>
                    <th className="py-2 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {draftRows.map((row, idx) => (
                    <tr key={`${idx}-${row.section_no}`} className="hover:bg-[var(--surface-2)]">
                      <td className="py-2 pr-3">
                        <input
                          type="text"
                          value={row.section_no}
                          aria-label={`Bölüm no satır ${idx + 1}`}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateRow(idx, { section_no: e.target.value })}
                          className="w-28 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 font-mono text-[12px] font-semibold"
                        />
                      </td>
                      <td className="py-2 pr-3">
                        <input
                          type="text"
                          value={row.start_kp}
                          aria-label={`Başlangıç KP satır ${idx + 1}`}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateRow(idx, { start_kp: e.target.value })}
                          className="w-24 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 font-mono text-[12px]"
                        />
                      </td>
                      <td className="py-2 pr-3">
                        <input
                          type="text"
                          value={row.end_kp}
                          aria-label={`Bitiş KP satır ${idx + 1}`}
                          autoCorrect="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          onChange={(e) => updateRow(idx, { end_kp: e.target.value })}
                          className="w-24 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 font-mono text-[12px]"
                        />
                      </td>
                      <td className="py-2 pr-3 text-right font-mono font-medium">
                        {num(row.length_m, 0)} m
                      </td>
                      <td className="py-2 pr-3 font-mono text-[11px] text-[var(--text-muted)]">
                        {row.lowest_elevation_m !== null && row.highest_elevation_m !== null ? (
                          <Badge tone="neutral">
                            {num(row.lowest_elevation_m, 1)} – {num(row.highest_elevation_m, 1)} m
                            {row.profile_points?.length ? ` · ${row.profile_points.length} nokta` : ""}
                          </Badge>
                        ) : (
                          "—"
                        )}
                      </td>
                      {showSourceColumn ? (
                        <td className="max-w-[160px] truncate py-2 pr-3 text-[11px] text-[var(--text-muted)]" title={row.source_file}>
                          {row.source_file || "—"}
                        </td>
                      ) : null}
                      <td className="py-2 pr-3">
                        <input
                          type="text"
                          value={row.description}
                          aria-label={`Açıklama satır ${idx + 1}`}
                          onChange={(e) => updateRow(idx, { description: e.target.value })}
                          className="w-full min-w-[200px] rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 text-[12px]"
                        />
                      </td>
                      <td className="py-2 text-right">
                        <button
                          type="button"
                          onClick={() => removeRow(idx)}
                          aria-label={`Satır ${idx + 1} (${row.section_no}) sil`}
                          className="rounded-lg p-1.5 text-[var(--text-muted)] hover:bg-[var(--danger-bg)] hover:text-[var(--danger-text)]"
                          title="Satırı sil"
                        >
                          <Trash2 size={14} aria-hidden />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!(projectMode === "new" || showNewProject) && !selectedProject ? (
              <div className="mt-3 flex items-center gap-2 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 text-[11.5px]">
                <AlertTriangle size={14} className="shrink-0 tone-warning" />
                <span>Kesitleri kaydetmek için sağ üstten bir hedef proje seçin veya yeni proje oluşturun.</span>
              </div>
            ) : null}
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
