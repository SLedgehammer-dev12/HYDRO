import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  FileWarning,
  FolderOpen,
  Layers,
  Loader2,
  Plus,
  ShieldAlert,
} from "lucide-react";
import { SectionCard } from "../../../components/ui/Card";
import { Badge, type Tone } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Dialog";
import { SelectField, TextField } from "../../../components/ui/Field";
import { InlineNotice } from "../../../components/ui/State";
import { useOpenSession, useProjects, useSessions } from "../../../hooks/queries";
import { CHECK_DEFINITIONS } from "../../../lib/constants";
import { num } from "../../../lib/format";
import { parseKpMeters } from "../../../lib/kp";
import type { SessionListItem } from "../../../lib/types";
import { useAppStore } from "../../../store/useAppStore";
import { commitOcrDossier, toOcrApiError } from "../ocrApi";
import type {
  DossierCommitResponse,
  DossierConflictItem,
  DossierFormEntry,
  DossierSection,
  OcrDossierView,
} from "../types";

interface Props {
  analysisId: string;
  dossier: OcrDossierView;
  onCommitted?: (res: DossierCommitResponse) => void;
}

function normSecToken(raw: string | undefined): string {
  const s = (raw ?? "")
    .toLowerCase()
    .replace(/[öÖ]/g, "o")
    .replace(/[üÜ]/g, "u")
    .replace(/[çÇ]/g, "c")
    .replace(/[ğĞ]/g, "g")
    .replace(/[şŞ]/g, "s")
    .replace(/[ıİ]/g, "i")
    .replace(/\b(?:test|bolum(?:u)?|section|kesit|paket|no)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  if (/^\d+\s*[a-z]?$/.test(s)) return s.replace(/\s+/g, "").replace(/^0+(\d)/, "$1");
  return s.replace(/\s+/g, "");
}

function findMatchedExistingSession(
  sec: DossierSection,
  sessions: SessionListItem[],
  claimedIds?: Set<string>,
): SessionListItem | null {
  const secKey = normSecToken(sec.section_no);
  for (const sess of sessions) {
    if (claimedIds?.has(sess.id)) continue;
    const k1 = normSecToken(sess.section_meta?.section_no);
    const k2 = normSecToken(sess.name.split("·")[0]);
    if (secKey && (k1 === secKey || k2 === secKey)) return sess;
  }
  const sM = parseKpMeters(sec.header.start_kp as string | undefined);
  const eM = parseKpMeters(sec.header.end_kp as string | undefined);
  if (sM !== null && eM !== null && eM > sM) {
    for (const sess of sessions) {
      if (claimedIds?.has(sess.id)) continue;
      const ssM = parseKpMeters(sess.section_meta?.start_kp);
      const seM = parseKpMeters(sess.section_meta?.end_kp);
      if (ssM !== null && seM !== null && Math.abs(ssM - sM) <= 5 && Math.abs(seM - eM) <= 5) {
        return sess;
      }
    }
  }
  return null;
}

function formStatusMeta(status: DossierFormEntry["status"]): { label: string; tone: Tone } {
  switch (status) {
    case "passed":
      return { label: "Başarılı", tone: "pass" };
    case "failed":
      return { label: "Başarısız", tone: "fail" };
    case "warning":
      return { label: "İnceleme", tone: "warning" };
    case "filled":
      return { label: "Dolu", tone: "info" };
    default:
      return { label: "Boş", tone: "neutral" };
  }
}

function checkStatusMeta(status: string | undefined): { label: string; tone: Tone } {
  switch (status) {
    case "passed":
      return { label: "Uygun", tone: "pass" };
    case "failed":
      return { label: "Uygun Değil", tone: "fail" };
    case "warning":
      return { label: "Kontrol Gerekli", tone: "warning" };
    default:
      return { label: "Veri Bekliyor", tone: "neutral" };
  }
}

export default function DossierPanel({ analysisId, dossier, onCommitted }: Props) {
  const queryClient = useQueryClient();
  const projectsQuery = useProjects();
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const openSession = useOpenSession();

  const setProject = useAppStore((s) => s.setProject);
  const setTab = useAppStore((s) => s.setTab);
  const pushToast = useAppStore((s) => s.pushToast);

  const similarProjects = useMemo(
    () => dossier.similar_projects ?? [],
    [dossier.similar_projects],
  );

  const [projectMode, setProjectMode] = useState<"existing" | "new">(() =>
    similarProjects.length > 0 ? "existing" : "new",
  );
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => similarProjects[0]?.id ?? "",
  );
  const [newProjectName, setNewProjectName] = useState<string>(
    () => dossier.detected_project_name ?? "",
  );
  const [newProjectCode, setNewProjectCode] = useState<string>("");

  const [selectedSections, setSelectedSections] = useState<Set<string>>(
    () => new Set(dossier.sections.map((s) => s.section_no)),
  );
  const [activeSectionNo, setActiveSectionNo] = useState<string>(
    () => dossier.sections[0]?.section_no ?? "",
  );
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [serverConflicts, setServerConflicts] = useState<DossierConflictItem[] | null>(null);
  const [commitModalOpen, setCommitModalOpen] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const [commitSuccess, setCommitSuccess] = useState<DossierCommitResponse | null>(null);

  useEffect(() => {
    setSelectedSections(new Set(dossier.sections.map((s) => s.section_no)));
    setActiveSectionNo(dossier.sections[0]?.section_no ?? "");
    setConfirmOverwrite(false);
    setServerConflicts(null);
    setCommitModalOpen(true);
    setCommitError(null);
    setCommitSuccess(null);
    setNewProjectCode("");

    if (similarProjects.length > 0) {
      setProjectMode("existing");
      setSelectedProjectId(similarProjects[0].id);
    } else {
      setProjectMode("new");
      setSelectedProjectId("");
      setNewProjectName(dossier.detected_project_name ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  useEffect(() => {
    if (projectMode === "existing" && !selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projectMode, selectedProjectId, projects]);

  const targetProjectSessionsQuery = useSessions(
    projectMode === "existing" && selectedProjectId ? selectedProjectId : null,
  );
  const existingSessionMatchMap = useMemo(() => {
    const map = new Map<string, SessionListItem>();
    if (projectMode !== "existing" || !selectedProjectId) return map;
    const list = targetProjectSessionsQuery.data ?? [];
    const claimed = new Set<string>();
    for (const sec of dossier.sections) {
      const hit = findMatchedExistingSession(sec, list, claimed);
      if (hit) {
        claimed.add(hit.id);
        map.set(sec.section_no, hit);
      }
    }
    return map;
  }, [projectMode, selectedProjectId, targetProjectSessionsQuery.data, dossier.sections]);

  const activeSection = useMemo(
    () =>
      dossier.sections.find((s) => s.section_no === activeSectionNo) ??
      dossier.sections[0] ??
      null,
    [dossier.sections, activeSectionNo],
  );

  const previewConflicts = useMemo(() => {
    if (projectMode !== "existing" || !selectedProjectId) return [];
    const list = dossier.project_conflicts?.[selectedProjectId] ?? [];
    return list.filter((item) => selectedSections.has(item.section_no));
  }, [projectMode, selectedProjectId, dossier.project_conflicts, selectedSections]);

  const activeConflicts = serverConflicts ?? previewConflicts;

  useEffect(() => {
    setConfirmOverwrite(false);
    setServerConflicts(null);
    setCommitError(null);
  }, [projectMode, selectedProjectId, selectedSections]);

  function toggleSectionSelection(sectionNo: string) {
    setSelectedSections((prev) => {
      const next = new Set(prev);
      if (next.has(sectionNo)) {
        next.delete(sectionNo);
      } else {
        next.add(sectionNo);
      }
      return next;
    });
  }

  async function handleCommit() {
    if (selectedSections.size === 0) {
      setCommitError("Kayıt için en az bir test bölümü seçmelisiniz.");
      return;
    }
    if (projectMode === "existing" && !selectedProjectId) {
      setCommitError("Lütfen kayıtlı bir proje seçin veya yeni proje oluşturun.");
      return;
    }
    if (projectMode === "new" && !newProjectName.trim()) {
      setCommitError("Yeni proje adı boş bırakılamaz.");
      return;
    }
    if (activeConflicts.length > 0 && !confirmOverwrite) {
      setCommitError(
        "Aynı test bölümünde daha önce doldurulmuş formlar var. Devam etmek için üzerine yazma onay kutusunu işaretleyin.",
      );
      return;
    }

    setSubmitting(true);
    setCommitError(null);
    try {
      const res = await commitOcrDossier(analysisId, {
        target_project_id: projectMode === "existing" ? selectedProjectId : null,
        create_new_project: projectMode === "new",
        new_project_name: projectMode === "new" ? newProjectName.trim() : null,
        new_project_code: projectMode === "new" && newProjectCode.trim() ? newProjectCode.trim() : null,
        overwrite_filled: confirmOverwrite,
        selected_sections: Array.from(selectedSections),
      });

      const createdList = Array.isArray(res.created_sections) ? res.created_sections : [];
      const updatedList = Array.isArray(res.updated_sections) ? res.updated_sections : [];
      const normalizedRes: DossierCommitResponse = {
        ...res,
        created_sections: createdList,
        updated_sections: updatedList,
      };
      setCommitSuccess(normalizedRes);
      setCommitModalOpen(false);
      setServerConflicts(null);
      setProject(res.project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["session-forms"] });
      void queryClient.invalidateQueries({ queryKey: ["project-scene"] });
      const activeSid = useAppStore.getState().sessionId;
      for (const secItem of createdList.concat(updatedList)) {
        void queryClient.invalidateQueries({ queryKey: ["session", secItem.session_id] });
        void queryClient.invalidateQueries({ queryKey: ["results", secItem.session_id] });
        if (activeSid && secItem.session_id === activeSid) {
          void openSession.mutateAsync(activeSid).catch(() => {});
        }
      }
      pushToast(
        "success",
        "Hakediş & Test Formları Kaydedildi",
        `${res.project.name}: ${res.saved_forms_count} form işlendi (${createdList.length} yeni kesit, ${updatedList.length} güncellenen kesit).`,
      );
      onCommitted?.(normalizedRes);
    } catch (error) {
      const apiErr = toOcrApiError(error);
      if (apiErr.code === "duplicate_filled_forms") {
        const rawConflicts = apiErr.details?.conflicts;
        if (Array.isArray(rawConflicts)) {
          setServerConflicts(rawConflicts as DossierConflictItem[]);
        }
        setCommitError(
          apiErr.message ||
            "Seçili test bölümlerinde daha önce doldurulmuş formlar mevcut. Üzerine yazmak için onay verin.",
        );
      } else {
        setCommitError(apiErr.message);
      }
      pushToast("error", "Kayıt tamamlanamadı", apiErr.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOpenCommittedSession(sessionId: string) {
    try {
      await openSession.mutateAsync(sessionId);
      setTab("geometry");
    } catch {
      // toast handled by hook
    }
  }

  return (
    <>
      <SectionCard
        title={`Çoklu Test Bölümü & BOTAŞ Form Analizi (${dossier.sections_count} Bölüm)`}
        description="Taranan dokümandaki tüm test bölümleri ayrıştırıldı, 11 zorunlu BOTAŞ formu ile eksik belgeler belirlendi, hesaplamalar ve 11 operasyon kontrol noktası otomatik değerlendirildi."
        icon={Layers}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{dossier.page_count} Sayfa</Badge>
            {dossier.blank_template_pages.length > 0 ? (
              <Badge tone="neutral">{dossier.blank_template_pages.length} Boş Şablon Atlandı</Badge>
            ) : null}
            <Button
              size="sm"
              variant="primary"
              icon={<Building2 size={14} />}
              onClick={() => setCommitModalOpen(true)}
            >
              Proje &amp; Bölüm Kayıt Penceresini Aç
            </Button>
          </div>
        }
      >
      <div className="space-y-4">
        {/* 1. Proje Eşleştirme & Seçim Kartı */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Building2 size={16} className="text-[var(--primary)]" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text)]">
                Proje Eşleştirme ve Kayıt Hedefi
              </h3>
            </div>
            {dossier.detected_project_name ? (
              <Badge tone="pass">Algılanan Proje: {dossier.detected_project_name}</Badge>
            ) : (
              <Badge tone="warning">Proje Adı Dokümandan Okunamadı</Badge>
            )}
          </div>

          {!dossier.detected_project_name ? (
            <div className="mt-2.5">
              <InlineNotice tone="warning" title="Dokümandan Proje Adı Çıkarılamadı">
                Lütfen aşağıdaki listeden mevcut bir projeyi seçin veya yeni proje oluşturarak devam edin.
              </InlineNotice>
            </div>
          ) : null}

          {similarProjects.length > 0 ? (
            <div className="mt-3 space-y-2">
              <p className="text-[11px] font-medium text-[var(--text-soft)]">
                %70 ve üzeri benzerlikte bulunan kayıtlı projeler (kayıt hedefi olarak seçebilirsiniz):
              </p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {similarProjects.map((cand) => {
                  const chosen = projectMode === "existing" && selectedProjectId === cand.id;
                  return (
                    <button
                      key={cand.id}
                      type="button"
                      onClick={() => {
                        setProjectMode("existing");
                        setSelectedProjectId(cand.id);
                      }}
                      className={`flex flex-col rounded-lg border p-2.5 text-left transition-colors ${
                        chosen
                          ? "border-[var(--primary)] bg-[var(--surface-1)] ring-1 ring-[var(--primary)]"
                          : "border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-semibold text-[var(--text)]">
                          {cand.name}
                        </span>
                        <Badge tone={cand.similarity >= 0.9 ? "pass" : "info"}>
                          %{Math.round(cand.similarity_pct)}
                        </Badge>
                      </div>
                      <span className="mt-1 text-[10.5px] text-[var(--text-muted)]">
                        {cand.code ? `Kod: ${cand.code} · ` : ""}
                        {cand.section_count} kayıtlı kesit
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-[var(--border)] pt-3 text-xs">
            <label className="inline-flex cursor-pointer items-center gap-2 font-medium text-[var(--text)]">
              <input
                type="radio"
                name={`dossier-mode-${analysisId}`}
                checked={projectMode === "existing"}
                onChange={() => setProjectMode("existing")}
              />
              Mevcut kayıtlı projeye kaydet / ekle
            </label>
            <label className="inline-flex cursor-pointer items-center gap-2 font-medium text-[var(--text)]">
              <input
                type="radio"
                name={`dossier-mode-${analysisId}`}
                checked={projectMode === "new"}
                onChange={() => setProjectMode("new")}
              />
              Yeni proje olarak kaydet
            </label>
          </div>

          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {projectMode === "existing" ? (
              <SelectField
                label="Kayıtlı proje seçin"
                value={selectedProjectId}
                onChange={setSelectedProjectId}
                options={
                  projects.length > 0
                    ? projects.map((p) => ({
                        value: p.id,
                        label: `${p.code ? `[${p.code}] ` : ""}${p.name} (${p.section_count} bölüm)`,
                      }))
                    : [{ value: "", label: "Kayıtlı proje yok — yeni proje oluşturun" }]
                }
              />
            ) : (
              <>
                <TextField
                  label="Yeni proje adı"
                  value={newProjectName}
                  onChange={setNewProjectName}
                  placeholder="Ör: 14&quot; ERCİŞ PATNOS DGBH YAPIM İŞİ PROJESİ"
                  required
                />
                <TextField
                  label="Proje kodu (opsiyonel)"
                  value={newProjectCode}
                  onChange={setNewProjectCode}
                  placeholder="Ör: ERC-01"
                />
              </>
            )}
          </div>
        </div>

        {/* 2. Dolu Form Üzerine Yazma Uyarısı */}
        {activeConflicts.length > 0 ? (
          <div className="rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] p-4">
            <div className="flex items-start gap-2.5">
              <AlertTriangle size={18} className="mt-0.5 shrink-0 text-[var(--warning)]" />
              <div className="flex-1 space-y-2">
                <h4 className="text-xs font-bold text-[var(--warning)]">
                  Aynı Test Bölümünde Önceden Kaydedilmiş Dolu Formlar Var ({activeConflicts.length} Form)
                </h4>
                <p className="text-[11.5px] leading-relaxed text-[var(--text-soft)]">
                  Seçili projede bu test bölümlerine ait bazı formlar daha önceki yüklemelerde doldurulmuş. Boş
                  bırakılan formlar onaysız otomatik doldurulur; ancak zaten dolu olan formların üzerine yeni
                  dokümandaki kayıtların yazılması için onayınız gerekiyor:
                </p>
                <div className="max-h-40 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2">
                  <ul className="space-y-1 text-[11px]">
                    {activeConflicts.map((c, i) => (
                      <li
                        key={`${c.section_no}-${c.form_code}-${i}`}
                        className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-1 last:border-b-0 last:pb-0"
                      >
                        <span className="font-medium text-[var(--text)]">
                          <strong>{c.section_no}</strong> · {c.form_title}{" "}
                          <span className="font-mono text-[10px] text-[var(--text-muted)]">
                            ({c.botas_code})
                          </span>
                        </span>
                        <span className="text-[10.5px] text-[var(--text-muted)]">
                          Önceki: {c.existing_filename} ({c.existing_date}, Rev.{c.existing_revision}) → Yeni sayfa:{" "}
                          {c.new_pages.join(", ") || "—"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                <label className="flex cursor-pointer items-center gap-2 pt-1 text-xs font-semibold text-[var(--text)]">
                  <input
                    type="checkbox"
                    checked={confirmOverwrite}
                    onChange={(e) => setConfirmOverwrite(e.target.checked)}
                  />
                  Evet, yukarıdaki dolu formların yeni taranan verilerle güncellenmesini onaylıyorum.
                </label>
              </div>
            </div>
          </div>
        ) : null}

        {/* 3. Tüm Test Bölümleri — Çoklu Bölüm Alan Kartları */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-[15px] font-bold text-[var(--text)]">
                Tespit Edilen Test Bölümleri ({selectedSections.size} / {dossier.sections.length} kayıt için seçili)
              </h3>
              <p className="text-xs text-[var(--text-muted)]">
                Her test bölümü kendi parametreleri ve 11 zorunlu BOTAŞ formuyla ayrı alan kartında listelenir; ayrıntısını görmek için kartı seçin.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {dossier.sections.map((sec) => {
              const isActive = activeSection?.section_no === sec.section_no;
              const isChecked = selectedSections.has(sec.section_no);
              const airFail = sec.calculations.air?.status === "failed";
              const prFail = sec.calculations.pressure?.status === "failed";
              const profFail = sec.calculations.profile?.status === "failed";
              const pigFail = sec.calculations.pig?.status === "failed";
              const hasFail = airFail || prFail || profFail || pigFail;
              const tone: Tone = hasFail
                ? "fail"
                : sec.filled_required_count >= sec.required_total ||
                    sec.calculations.profile?.status === "passed"
                  ? "pass"
                  : "warning";

              const startKp = String(sec.header.start_kp || "—");
              const endKp = String(sec.header.end_kp || "—");
              const od = sec.header.outside_diameter_mm ? `${num(Number(sec.header.outside_diameter_mm), 1)} mm` : "—";
              const wt = sec.header.wall_thickness_mm ? `${num(Number(sec.header.wall_thickness_mm), 2)} mm` : "—";
              const lenM = sec.header.length_m ? `${num(Number(sec.header.length_m), 1)} m` : "—";
              const testP = sec.header.test_pressure_bar
                ? `${num(Number(sec.header.test_pressure_bar), 1)} bar`
                : sec.header.monitored_pressure_bar
                  ? `${num(Number(sec.header.monitored_pressure_bar), 1)} bar`
                  : "—";
              const matchedSess = existingSessionMatchMap.get(sec.section_no);

              return (
                <div
                  key={sec.section_no}
                  onClick={() => setActiveSectionNo(sec.section_no)}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-colors ${
                    isActive
                      ? "border-[var(--primary)] bg-[var(--surface-1)] ring-2 ring-[var(--primary)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-2">
                    <label
                      className="flex cursor-pointer items-center gap-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        aria-label={`${sec.section_no} kaydedilsin`}
                        checked={isChecked}
                        onChange={() => toggleSectionSelection(sec.section_no)}
                      />
                      <span className="font-mono text-[15px] font-bold text-[var(--text)]">
                        {sec.section_no}
                      </span>
                    </label>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {projectMode === "existing" && selectedProjectId ? (
                        <Badge tone={matchedSess ? "info" : "pass"}>
                          {matchedSess ? "Mevcut Kesit" : "Yeni Kesit"}
                        </Badge>
                      ) : null}
                      <Badge tone={tone}>
                        {sec.filled_required_count}/{sec.required_total} Zorunlu
                      </Badge>
                    </div>
                  </div>

                  <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11.5px]">
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">KP Aralığı</dt>
                      <dd className="font-mono font-semibold text-[var(--text)]">
                        {startKp} – {endKp}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Bölüm Boyu</dt>
                      <dd className="font-mono font-semibold text-[var(--text)]">{lenM}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Çap × Et</dt>
                      <dd className="font-mono text-[var(--text-soft)]">
                        {od} × {wt}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Test Basıncı</dt>
                      <dd className="font-mono text-[var(--text-soft)]">{testP}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">Hava Testi</dt>
                      <dd className={airFail ? "font-bold text-[var(--danger)]" : sec.calculations.air?.status === "passed" ? "font-bold text-[var(--success)]" : "text-[var(--text-muted)]"}>
                        {sec.calculations.air?.status === "passed"
                          ? "BAŞARILI"
                          : sec.calculations.air?.status === "failed"
                            ? "BAŞARISIZ"
                            : "Bekliyor"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
                        {sec.calculations.pressure?.status !== "pending" || !sec.calculations.profile
                          ? "24 Sa. Basınç"
                          : "Basınç Profili"}
                      </dt>
                      {sec.calculations.pressure?.status !== "pending" || !sec.calculations.profile ? (
                        <dd className={prFail ? "font-bold text-[var(--danger)]" : sec.calculations.pressure?.status === "passed" ? "font-bold text-[var(--success)]" : "text-[var(--text-muted)]"}>
                          {sec.calculations.pressure?.status === "passed"
                            ? "BAŞARILI"
                            : sec.calculations.pressure?.status === "failed"
                              ? "BAŞARISIZ"
                              : "Bekliyor"}
                        </dd>
                      ) : (
                        <dd className={profFail ? "font-bold text-[var(--danger)]" : sec.calculations.profile?.status === "passed" ? "font-bold text-[var(--success)]" : "text-[var(--text-muted)]"}>
                          {sec.calculations.profile?.status === "passed"
                            ? "BAŞARILI"
                            : sec.calculations.profile?.status === "failed"
                              ? "BAŞARISIZ"
                              : "Bekliyor"}
                        </dd>
                      )}
                    </div>
                  </dl>

                  <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-[var(--border)] pt-2 text-[11px] text-[var(--text-muted)]">
                    <span>Eksik: {sec.missing_required_forms.length} form</span>
                    <span className="font-mono text-[10.5px] text-[var(--primary)]">
                      {isActive ? "Ayrıntı açık ↓" : "İncele →"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 4. Seçili Bölümün Detaylı İncelemesi */}
        {activeSection ? (
          <div className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
              <div>
                <h4 className="text-sm font-bold text-[var(--text)]">
                  {activeSection.section_no} — Form & Kontrol Özeti
                </h4>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  Sayfalar: {activeSection.pages.join(", ") || "—"}
                  {activeSection.header.outside_diameter_mm
                    ? ` · D=${num(Number(activeSection.header.outside_diameter_mm), 1)} mm`
                    : ""}
                  {activeSection.header.wall_thickness_mm
                    ? ` · t=${num(Number(activeSection.header.wall_thickness_mm), 2)} mm`
                    : ""}
                  {activeSection.header.length_m
                    ? ` · L=${num(Number(activeSection.header.length_m), 1)} m`
                    : ""}
                  {activeSection.header.test_pressure_bar
                    ? ` · Ptest=${num(Number(activeSection.header.test_pressure_bar), 1)} bar`
                    : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge
                  tone={
                    activeSection.filled_required_count >= activeSection.required_total
                      ? "pass"
                      : "warning"
                  }
                >
                  Zorunlu: {activeSection.filled_required_count}/{activeSection.required_total}
                </Badge>
                {activeSection.supplementary_count > 0 ? (
                  <Badge tone="info">Ek Rapor: {activeSection.supplementary_count}</Badge>
                ) : null}
              </div>
            </div>

            {/* 4a. Hesap Değerlendirmesi (Başarılı / Başarısız) */}
            <div className="grid gap-3 md:grid-cols-3">
              {[
                {
                  key: "air",
                  title: "Hava İçerik Testi Değerlendirmesi",
                  calc: activeSection.calculations.air,
                  emptyText: "Hava içerik verisi bulunamadı.",
                },
                {
                  key: "pressure",
                  title: "24 Saat Basınç Değişimi Değerlendirmesi",
                  calc: activeSection.calculations.pressure,
                  emptyText: "Basınç testi verisi bulunamadı.",
                },
                {
                  key: "profile",
                  title: "Basınç Profili & Kot Uygunluğu (SMYS)",
                  calc: activeSection.calculations.profile,
                  emptyText: "Kot/SMYS basınç profili verisi bulunamadı.",
                },
                ...(activeSection.calculations.pig &&
                activeSection.calculations.pig.passed !== null &&
                activeSection.calculations.pig.passed !== undefined
                  ? [
                      {
                        key: "pig",
                        title: "Pig Hızı Değerlendirmesi",
                        calc: activeSection.calculations.pig,
                        emptyText: "Pig hız verisi bulunamadı.",
                      },
                    ]
                  : []),
              ].map((card) => (
                <div key={card.key} className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text)]">
                      {card.title}
                    </span>
                    <Badge
                      tone={
                        card.calc?.status === "passed"
                          ? "pass"
                          : card.calc?.status === "failed"
                            ? "fail"
                            : "neutral"
                      }
                    >
                      {card.calc?.status === "passed"
                        ? "BAŞARILI"
                        : card.calc?.status === "failed"
                          ? "BAŞARISIZ"
                          : "Veri Bekliyor"}
                    </Badge>
                  </div>
                  <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--text-soft)]">
                    {card.calc?.summary ?? card.emptyText}
                  </p>
                </div>
              ))}
            </div>

            {/* 4b. Mevcut Formlar ve Eksik Zorunlu Formlar */}
            <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
              <div>
                <h5 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--text)]">
                  <FileCheck2 size={14} className="text-[var(--primary)]" />
                  Bu Dokümanda Algılanan Formlar ({activeSection.present_forms.length})
                </h5>
                <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
                  <table className="w-full border-collapse text-left text-[11.5px]">
                    <thead className="bg-[var(--surface-2)] text-[10.5px] uppercase tracking-wider text-[var(--text-muted)]">
                      <tr>
                        <th className="px-2.5 py-2">Form Kodu</th>
                        <th className="px-2.5 py-2">Form Başlığı</th>
                        <th className="px-2.5 py-2">Sayfa</th>
                        <th className="px-2.5 py-2">Tarih</th>
                        <th className="px-2.5 py-2">Durum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {activeSection.present_forms.map((f) => {
                        const meta = formStatusMeta(f.status);
                        return (
                          <tr key={f.form_code}>
                            <td className="px-2.5 py-2 font-mono text-[10.5px] text-[var(--text-muted)]">
                              {f.botas_code}
                            </td>
                            <td className="px-2.5 py-2 font-medium text-[var(--text)]">
                              {f.form_title}
                              {!f.required ? (
                                <span className="ml-1.5 text-[10px] text-[var(--text-muted)]">
                                  (Ek)
                                </span>
                              ) : null}
                            </td>
                            <td className="px-2.5 py-2 font-mono text-[11px]">
                              {f.pages.join(", ")}
                            </td>
                            <td className="px-2.5 py-2 font-mono text-[11px]">
                              {f.form_date || "—"}
                            </td>
                            <td className="px-2.5 py-2">
                              <Badge tone={meta.tone}>{meta.label}</Badge>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h5 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--text)]">
                  <FileWarning size={14} className="text-[var(--warning)]" />
                  Testin Tamamlanması İçin Eksik Zorunlu Formlar (
                  {activeSection.missing_required_forms.length})
                </h5>
                {activeSection.missing_required_forms.length === 0 ? (
                  <InlineNotice tone="success" title="Tüm Zorunlu Formlar Tamam">
                    Bu test bölümü için zorunlu 11 BOTAŞ formunun tamamı (Ön Kurutma ve Nihai Kurutma
                    dahil) mevcut.
                  </InlineNotice>
                ) : (
                  <div className="max-h-72 overflow-y-auto rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] p-2.5">
                    <ul className="space-y-1.5 text-[11.5px]">
                      {activeSection.missing_required_forms.map((m) => (
                        <li
                          key={m.form_code}
                          className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-1 last:border-b-0 last:pb-0"
                        >
                          <span className="font-medium text-[var(--text)]">{m.form_title}</span>
                          <span className="font-mono text-[10px] text-[var(--text-muted)]">
                            {m.botas_code}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            {/* 4c. Operasyon Kontrol Noktaları (11 Madde Otomatik Kontrol) */}
            <div>
              <h5 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--text)]">
                <ClipboardCheck size={14} className="text-[var(--primary)]" />
                Otomatik Operasyon Kontrol Noktaları (Form Verilerine Göre)
              </h5>
              <div className="grid gap-2 md:grid-cols-2">
                {CHECK_DEFINITIONS.map((def) => {
                  const detail = activeSection.check_details?.[def.key];
                  const st = checkStatusMeta(detail?.status);
                  return (
                    <div
                      key={def.key}
                      className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[11.5px] font-semibold text-[var(--text)]">
                          {def.label}
                        </span>
                        <Badge tone={st.tone} className="shrink-0">
                          {st.label}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[11px] leading-snug text-[var(--text-soft)]">
                        {detail?.message ?? "Bu madde için ilgili form henüz taranmadı."}
                      </p>
                      <span className="mt-1 block font-mono text-[10px] text-[var(--text-faint)]">
                        Madde {def.ref}
                        {detail?.source_forms?.length
                          ? ` · Kaynak: ${detail.source_forms.join(", ")}`
                          : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : null}

        {/* 5. Doküman Geneli Notlar / Tanımsız Sayfalar */}
        {dossier.warnings.length > 0 || dossier.unassigned_pages.length > 0 ? (
          <InlineNotice tone="info" title="Doküman Ayrıştırma Notları">
            <ul className="list-disc space-y-1 pl-4 text-[11.5px]">
              {dossier.warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
              {dossier.unassigned_pages.slice(0, 6).map((u, idx) => (
                <li key={`u-${idx}`}>
                  Sayfa {u.page}
                  {u.section_no ? ` (${u.section_no})` : ""}: {u.reason}
                </li>
              ))}
              {dossier.unassigned_pages.length > 6 ? (
                <li>... ve {dossier.unassigned_pages.length - 6} sayfa daha.</li>
              ) : null}
            </ul>
          </InlineNotice>
        ) : null}

        {/* 6. Kayıt Hatası / Başarı Özeti / Kayıt Butonu */}
        {commitError ? (
          <InlineNotice tone="danger" title="Kayıt Uyarısı">
            {commitError}
          </InlineNotice>
        ) : null}

        {commitSuccess ? (
          <InlineNotice
            tone="success"
            title={`${commitSuccess.project.name} Projesine Kaydedildi`}
          >
            {(() => {
              const createdList = Array.isArray(commitSuccess.created_sections)
                ? commitSuccess.created_sections
                : [];
              const updatedList = Array.isArray(commitSuccess.updated_sections)
                ? commitSuccess.updated_sections
                : [];
              const allSections = createdList.concat(updatedList);
              return (
                <>
                  <p className="text-[11.5px]">
                    {commitSuccess.saved_forms_count} form kaydedildi (
                    {createdList.length} yeni test bölümü,{" "}
                    {updatedList.length} güncellenen bölüm
                    {commitSuccess.overwritten_forms_count > 0
                      ? `, ${commitSuccess.overwritten_forms_count} dolu form güncellendi`
                      : ""}
                    ). Kümülâtif hesaplamalar ve 11 operasyon kontrol noktası veritabanına işlendi.
                  </p>
                  <div className="mt-2.5 flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<FolderOpen size={13} />}
                      onClick={() => setTab("projects")}
                    >
                      Projeler &amp; Form Takibine Git
                    </Button>
                    {allSections.map((s) => (
                      <Button
                        key={s.session_id}
                        size="sm"
                        variant="ghost"
                        onClick={() => handleOpenCommittedSession(s.session_id)}
                      >
                        {s.section_no} Kontrol Noktalarını Aç
                      </Button>
                    ))}
                  </div>
                </>
              );
            })()}
          </InlineNotice>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-3">
          <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
            <ShieldAlert size={14} className="text-[var(--primary)]" />
            <span>
              Yeni bölümlerde 11 zorunlu form slotu otomatik oluşturulur; dolu formlar onay olmadan
              ezilmez.
            </span>
          </div>
          <Button
            size="lg"
            variant="primary"
            icon={
              submitting ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <CheckCircle2 size={15} />
              )
            }
            disabled={
              submitting ||
              selectedSections.size === 0 ||
              (activeConflicts.length > 0 && !confirmOverwrite)
            }
            onClick={handleCommit}
          >
            {submitting
              ? "Veritabanına Kaydediliyor..."
              : projectMode === "new"
                ? `Yeni Proje Oluştur ve ${selectedSections.size} Bölümü Kaydet`
                : `${selectedSections.size} Bölümü Projeye Kaydet / Güncelle`}
          </Button>
        </div>
      </div>
    </SectionCard>

    <Modal
      open={commitModalOpen}
      onClose={() => setCommitModalOpen(false)}
      title={
        dossier.detected_project_name && similarProjects.length === 0
          ? "Yeni Proje Algılandı — Veritabanına Kayıt"
          : similarProjects.length > 0
            ? "Kayıtlı Proje Eşleşmesi Bulundu — Bölüm & Form Kaydı"
            : "Proje Seçimi ve Test Bölümleri Kaydı"
      }
      description={`Taranan dosyada ${dossier.sections.length} ayrı test bölümü tespit edildi. Veritabanında kayıt durumuna göre yeni proje oluşturabilir veya mevcut projeye ekleyebilirsiniz.`}
      className="max-w-3xl max-h-[88vh] overflow-y-auto"
      footer={
        <>
          <Button variant="ghost" onClick={() => setCommitModalOpen(false)}>
            Önce Bölüm Alanlarını ve Formları İncele
          </Button>
          <Button
            size="lg"
            variant="primary"
            loading={submitting}
            disabled={
              submitting ||
              selectedSections.size === 0 ||
              (activeConflicts.length > 0 && !confirmOverwrite)
            }
            onClick={handleCommit}
          >
            {projectMode === "new"
              ? `Yeni Proje Oluştur ve ${selectedSections.size} Bölümü Kaydet`
              : `${selectedSections.size} Bölümü Seçili Projeye Kaydet`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {dossier.detected_project_name && similarProjects.length === 0 ? (
          <InlineNotice tone="info" title="Veritabanında Eşleşen Proje Bulunamadı — Yeni Proje Kaydı Hazır">
            Taranan dokümanda <strong>{dossier.detected_project_name}</strong> proje adı algılandı ve
            veritabanında %70 ve üzeri benzerlikte kayıtlı proje bulunmadığı görüldü. Aşağıdan yeni proje
            olarak oluşturup seçili <strong>{selectedSections.size} test bölümünü</strong> ve formlarını
            veritabanına kaydedebilirsiniz.
          </InlineNotice>
        ) : similarProjects.length > 0 ? (
          <InlineNotice tone="success" title="%70 ve Üzeri Benzer Kayıtlı Proje Bulundu">
            Algılanan proje adına (<strong>{dossier.detected_project_name ?? "—"}</strong>) benzer kayıtlı
            projeler aşağıda listelendi. Üzerine kaydedebilir veya yeni proje olarak devam edebilirsiniz.
          </InlineNotice>
        ) : (
          <InlineNotice tone="warning" title="Dokümandan Proje Adı Okunamadı">
            Lütfen mevcut kayıtlı projelerden birini seçin veya yeni proje adı girerek bölümleri kaydedin.
          </InlineNotice>
        )}

        {similarProjects.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {similarProjects.map((cand) => {
              const chosen = projectMode === "existing" && selectedProjectId === cand.id;
              return (
                <button
                  key={`m-${cand.id}`}
                  type="button"
                  onClick={() => {
                    setProjectMode("existing");
                    setSelectedProjectId(cand.id);
                  }}
                  className={`flex flex-col rounded-lg border p-2.5 text-left transition-colors ${
                    chosen
                      ? "border-[var(--primary)] bg-[var(--surface-1)] ring-1 ring-[var(--primary)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold text-[var(--text)]">{cand.name}</span>
                    <Badge tone={cand.similarity >= 0.9 ? "pass" : "info"}>
                      %{Math.round(cand.similarity_pct)}
                    </Badge>
                  </div>
                  <span className="mt-1 text-[10.5px] text-[var(--text-muted)]">
                    {cand.code ? `Kod: ${cand.code} · ` : ""}
                    {cand.section_count} kayıtlı kesit
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="inline-flex cursor-pointer items-center gap-2 font-semibold text-[var(--text)]">
            <input
              type="radio"
              name={`modal-dossier-mode-${analysisId}`}
              checked={projectMode === "new"}
              onChange={() => setProjectMode("new")}
            />
            Yeni proje olarak kaydet
          </label>
          <label className="inline-flex cursor-pointer items-center gap-2 font-semibold text-[var(--text)]">
            <input
              type="radio"
              name={`modal-dossier-mode-${analysisId}`}
              checked={projectMode === "existing"}
              onChange={() => setProjectMode("existing")}
            />
            Mevcut kayıtlı projeye kaydet
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {projectMode === "new" ? (
            <>
              <TextField
                label="Yeni proje adı"
                value={newProjectName}
                onChange={setNewProjectName}
                placeholder='Ör: 14" ERCİŞ PATNOS DGBH YAPIM İŞİ PROJESİ'
                required
              />
              <TextField
                label="Proje kodu (opsiyonel)"
                value={newProjectCode}
                onChange={setNewProjectCode}
                placeholder="Ör: ERC-01"
              />
            </>
          ) : (
            <SelectField
              label="Kayıtlı proje seçin"
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              options={
                projects.length > 0
                  ? projects.map((p) => ({
                      value: p.id,
                      label: `${p.code ? `[${p.code}] ` : ""}${p.name} (${p.section_count} bölüm)`,
                    }))
                  : [{ value: "", label: "Kayıtlı proje yok — yeni proje oluşturun" }]
              }
            />
          )}
        </div>

        {activeConflicts.length > 0 ? (
          <div className="rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] p-3 text-xs">
            <p className="font-bold text-[var(--warning)]">
              Seçili projede önceden doldurulmuş {activeConflicts.length} form mevcut:
            </p>
            <label className="mt-2 flex cursor-pointer items-center gap-2 font-semibold text-[var(--text)]">
              <input
                type="checkbox"
                checked={confirmOverwrite}
                onChange={(e) => setConfirmOverwrite(e.target.checked)}
              />
              Evet, dolu formların yeni taranan verilerle güncellenmesini onaylıyorum.
            </label>
          </div>
        ) : null}

        <div className="table-wrap scroll-thin max-h-60 overflow-y-auto">
          <table className="data compact">
            <thead>
              <tr>
                <th scope="col">Seç</th>
                <th scope="col">Bölüm</th>
                <th scope="col">Durum</th>
                <th scope="col">KP Aralığı</th>
                <th scope="col" className="num">Boy (m)</th>
                <th scope="col">Formlar</th>
                <th scope="col">Eksik</th>
              </tr>
            </thead>
            <tbody>
              {dossier.sections.map((sec) => {
                const matchedSess = existingSessionMatchMap.get(sec.section_no);
                return (
                <tr key={`modal-sec-${sec.section_no}`}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Modal ${sec.section_no} seçimi`}
                      checked={selectedSections.has(sec.section_no)}
                      onChange={() => toggleSectionSelection(sec.section_no)}
                    />
                  </td>
                  <td className="font-mono font-bold text-[var(--text)]">{sec.section_no}</td>
                  <td>
                    {projectMode === "existing" && selectedProjectId ? (
                      <Badge tone={matchedSess ? "info" : "pass"}>
                        {matchedSess ? "Mevcut Kesit" : "Yeni Kesit"}
                      </Badge>
                    ) : (
                      <Badge tone="pass">Yeni Kesit</Badge>
                    )}
                  </td>
                  <td className="font-mono text-[11px]">
                    {String(sec.header.start_kp || "—")} – {String(sec.header.end_kp || "—")}
                  </td>
                  <td className="num font-mono">
                    {sec.header.length_m ? num(Number(sec.header.length_m), 1) : "—"}
                  </td>
                  <td>
                    <Badge tone={sec.filled_required_count >= sec.required_total ? "pass" : "warning"}>
                      {sec.filled_required_count}/{sec.required_total}
                    </Badge>
                  </td>
                  <td className="text-[var(--text-muted)]">{sec.missing_required_forms.length} eksik</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {commitError ? (
          <InlineNotice tone="danger" title="Kayıt Hatası">
            {commitError}
          </InlineNotice>
        ) : null}
      </div>
    </Modal>
    </>
  );
}

export { Plus };
