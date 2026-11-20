import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, Database, FileJson, FileUp, Sparkles } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Dialog";
import { CheckboxRow, FieldGrid, NumberField, SelectField, TextField } from "../../components/ui/Field";
import { InlineNotice } from "../../components/ui/State";
import {
  activateImportedSession,
  useGenerateSampleProject,
  useImportDesktopDb,
  useImportDesktopSnapshot,
  useImportProjectArchive,
  type DesktopSnapshotImportOutcome,
} from "../../hooks/queries";
import type { Project, Session } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";

export function SampleProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (project: Project) => void;
}) {
  const pushToast = useAppStore((s) => s.pushToast);
  const generateSample = useGenerateSampleProject();

  const [scenario, setScenario] = useState<"mixed" | "passing" | "failing">("mixed");
  const [sectionCount, setSectionCount] = useState<number | null>(3);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [includeTs, setIncludeTs] = useState(true);
  const [includeForms, setIncludeForms] = useState(true);

  function submit() {
    const count = Math.min(12, Math.max(1, Math.round(sectionCount ?? 3)));
    if (count < 1) {
      pushToast("warning", "En az 1 kesit seçin");
      return;
    }
    generateSample.mutate(
      {
        scenario,
        section_count: count,
        name: name.trim() || null,
        code: code.trim() || null,
        include_time_series: includeTs,
        include_forms: includeForms,
      },
      {
        onSuccess: (data) => {
          onCreated?.(data.project);
          onClose();
        },
      },
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Örnek Hidrostatik Test Projesi Üret"
      description="Gerçek 4-NGTL mühendislik hesap motorunu kullanarak eksiksiz test sonuçları, 24 saatlik zaman serisi ve BOTAŞ form verileri üretir."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button
            variant="primary"
            icon={<Sparkles size={14} />}
            loading={generateSample.isPending}
            onClick={submit}
          >
            Örnek Projeyi Oluştur
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <FieldGrid cols={2}>
          <SelectField
            label="Test senaryosu"
            value={scenario}
            onChange={(v) =>
              setScenario(v === "passing" ? "passing" : v === "failing" ? "failing" : "mixed")
            }
            options={[
              { value: "mixed", label: "Karma (Başarılı + Uyarılı + Başarısız kesitler)" },
              { value: "passing", label: "Tamamı Başarılı (Clean Pass)" },
              { value: "failing", label: "Kabul Dışı Sapmalı (Fail örneği)" },
            ]}
          />
          <NumberField
            label="Kesit sayısı"
            value={sectionCount}
            onChange={setSectionCount}
            min={1}
            max={12}
            digits={0}
          />
          <TextField
            label="Proje adı (isteğe bağlı)"
            value={name}
            onChange={setName}
            placeholder="Otomatik verilir"
          />
          <TextField
            label="Proje kodu (isteğe bağlı)"
            value={code}
            onChange={setCode}
            placeholder="Ör: SMP-01"
          />
        </FieldGrid>
        <FieldGrid cols={2}>
          <CheckboxRow
            checked={includeTs}
            onChange={setIncludeTs}
            label="24 saatlik basınç & sıcaklık zaman serisi oluştur"
          />
          <CheckboxRow
            checked={includeForms}
            onChange={setIncludeForms}
            label="Tüm zorunlu BOTAŞ formlarını örnek okumalarla doldur"
          />
        </FieldGrid>
      </div>
    </Modal>
  );
}

export function ProjectImportModal({
  open,
  onClose,
  onImported,
  onSessionImported,
  projects = [],
  selectedProjectId = null,
}: {
  open: boolean;
  onClose: () => void;
  onImported?: (project: Project) => void;
  onSessionImported?: (session: Session) => void;
  projects?: Project[];
  selectedProjectId?: string | null;
}) {
  const pushToast = useAppStore((s) => s.pushToast);
  const queryClient = useQueryClient();
  const importArchive = useImportProjectArchive();
  const importDesktopDb = useImportDesktopDb();
  const importDesktopSnapshot = useImportDesktopSnapshot();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const wasOpenRef = useRef(false);
  const fileInputId = useId();
  const tabPanelId = useId();
  const tabRefs = useRef<Record<"archive" | "desktop_db" | "desktop_json", HTMLButtonElement | null>>({
    archive: null,
    desktop_db: null,
    desktop_json: null,
  });

  const realProjects = projects.filter((p) => !p.id.startsWith("demo-"));
  const defaultTargetProjectId =
    selectedProjectId && !selectedProjectId.startsWith("demo-")
      ? selectedProjectId
      : realProjects[0]?.id ?? "__none__";

  const [mode, setMode] = useState<"archive" | "desktop_db" | "desktop_json">("archive");
  const [file, setFile] = useState<File | null>(null);
  const [targetName, setTargetName] = useState("");
  const [targetCode, setTargetCode] = useState("");
  const [targetProjectId, setTargetProjectId] = useState<string>(defaultTargetProjectId);
  const [includeAttachments, setIncludeAttachments] = useState(true);
  const [snapshotOutcome, setSnapshotOutcome] = useState<DesktopSnapshotImportOutcome | null>(null);

  function clearFileInput() {
    setFile(null);
    setSnapshotOutcome(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setTargetProjectId(defaultTargetProjectId);
      setTargetName("");
      setTargetCode("");
      setFile(null);
      setSnapshotOutcome(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
    wasOpenRef.current = open;
  }, [open, defaultTargetProjectId]);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    setFile(picked);
    setSnapshotOutcome(null);
  }

  function closeModal() {
    setTargetName("");
    setTargetCode("");
    clearFileInput();
    onClose();
  }

  function switchTab(nextMode: "archive" | "desktop_db" | "desktop_json") {
    setMode(nextMode);
    clearFileInput();
  }

  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    const order: Array<"archive" | "desktop_db" | "desktop_json"> = [
      "archive",
      "desktop_db",
      "desktop_json",
    ];
    const idx = order.indexOf(mode);
    if (idx < 0) return;
    let nextIdx = -1;
    if (e.key === "ArrowRight") nextIdx = (idx + 1) % order.length;
    else if (e.key === "ArrowLeft") nextIdx = (idx - 1 + order.length) % order.length;
    if (nextIdx >= 0) {
      e.preventDefault();
      const next = order[nextIdx];
      switchTab(next);
      tabRefs.current[next]?.focus();
    }
  }

  const busy =
    importArchive.isPending || importDesktopDb.isPending || importDesktopSnapshot.isPending;

  function submit() {
    if (!file) {
      pushToast(
        "warning",
        "Dosya seçilmedi",
        mode === "desktop_json"
          ? "Lütfen masaüstü JSON snapshot dosyası seçin."
          : "Lütfen geçerli bir paket veya .db dosyası seçin.",
      );
      return;
    }
    if (mode === "archive") {
      importArchive.mutate(
        {
          file,
          targetProjectName: targetName.trim() || undefined,
          targetProjectCode: targetCode.trim() || undefined,
          includeAttachments,
        },
        {
          onSuccess: (res) => {
            onImported?.(res.project);
            closeModal();
          },
        },
      );
    } else if (mode === "desktop_db") {
      importDesktopDb.mutate(
        {
          file,
          projectName: targetName.trim() || undefined,
          projectCode: targetCode.trim() || undefined,
        },
        {
          onSuccess: (res) => {
            onImported?.(res.project);
            closeModal();
          },
        },
      );
    } else {
      importDesktopSnapshot.mutate(
        {
          file,
          name: targetName.trim() || undefined,
          projectId: targetProjectId === "__none__" ? null : targetProjectId,
          openAfterImport: false,
        },
        {
          onSuccess: (res) => {
            const hasMappingNotes =
              res.mapping.warnings.length > 0 ||
              res.mapping.invalid_fields.length > 0 ||
              res.mapping.skipped.length > 0;
            if (hasMappingNotes) {
              setSnapshotOutcome(res);
              return;
            }
            activateImportedSession(queryClient, res);
            onSessionImported?.(res.session);
            closeModal();
          },
        },
      );
    }
  }

  return (
    <Modal
      open={open}
      dismissible={!busy}
      onClose={() => {
        if (!busy) closeModal();
      }}
      title="Proje Paketi, Masaüstü DB veya JSON İçe Aktar"
      description=".hydroproj.zip proje paketi, eski masaüstü hydro.db veritabanı veya masaüstü JSON snapshot dosyasını içe aktarın."
      footer={
        snapshotOutcome ? (
          <>
            <Button variant="ghost" onClick={closeModal}>
              Kapat
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                activateImportedSession(queryClient, snapshotOutcome);
                onSessionImported?.(snapshotOutcome.session);
                closeModal();
              }}
            >
              Tamam / Oturuma geç
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" disabled={busy} onClick={closeModal}>
              Vazgeç
            </Button>
            <Button variant="primary" icon={<FileUp size={14} />} loading={busy} onClick={submit}>
              İçe Aktar
            </Button>
          </>
        )
      }
    >
      <div className="space-y-3">
        <div className="seg-control" role="tablist" aria-label="İçe aktarma biçimi">
          <button
            ref={(el) => {
              tabRefs.current.archive = el;
            }}
            type="button"
            role="tab"
            aria-selected={mode === "archive"}
            aria-controls={tabPanelId}
            tabIndex={mode === "archive" ? 0 : -1}
            className="seg-btn"
            onKeyDown={onTabKeyDown}
            onClick={() => switchTab("archive")}
          >
            <Archive size={13} className="mr-1 inline" aria-hidden />
            .hydroproj.zip Arşiv Paketi
          </button>
          <button
            ref={(el) => {
              tabRefs.current.desktop_db = el;
            }}
            type="button"
            role="tab"
            aria-selected={mode === "desktop_db"}
            aria-controls={tabPanelId}
            tabIndex={mode === "desktop_db" ? 0 : -1}
            className="seg-btn"
            onKeyDown={onTabKeyDown}
            onClick={() => switchTab("desktop_db")}
          >
            <Database size={13} className="mr-1 inline" aria-hidden />
            Masaüstü hydro.db (SQLite)
          </button>
          <button
            ref={(el) => {
              tabRefs.current.desktop_json = el;
            }}
            type="button"
            role="tab"
            aria-selected={mode === "desktop_json"}
            aria-controls={tabPanelId}
            tabIndex={mode === "desktop_json" ? 0 : -1}
            className="seg-btn"
            onKeyDown={onTabKeyDown}
            onClick={() => switchTab("desktop_json")}
          >
            <FileJson size={13} className="mr-1 inline" aria-hidden />
            Masaüstü JSON Snapshot
          </button>
        </div>

        <div id={tabPanelId} role="tabpanel" className="space-y-3">
          <InlineNotice
            tone="info"
            title={
              mode === "archive"
                ? "SHA-256 Bütünlük Doğrulamalı Paket"
                : mode === "desktop_db"
                  ? "Eski Masaüstü Veritabanı Aktarımı"
                  : "Masaüstü JSON Snapshot Kesit Aktarımı"
            }
            icon={mode === "archive" ? Archive : mode === "desktop_db" ? Database : FileJson}
          >
            {mode === "archive" ? (
              "Arşivdeki tüm dosyalar SHA-256 manifestine göre doğrulanır, kesitler ve formlar yeni kimliklerle güvenle içeri alınır."
            ) : mode === "desktop_db" ? (
              "Masaüstü uygulamasının hydro.db dosyasındaki sessions, geometry_records, test_entries ve time_series_records tabloları okunur."
            ) : (
              <>
                Masaüstü uygulamasından dışa aktarılan{" "}
                <code className="font-mono text-[11px]">schema_version: 1</code> JSON snapshot
                dosyasından yeni bir kesit oturumu oluşturur (
                <code className="font-mono text-[11px]">POST /api/import/desktop-snapshot</code>).
              </>
            )}
          </InlineNotice>

          <div className="rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-2)] p-4">
            <label htmlFor={fileInputId} className="block text-[12px] font-medium text-[var(--text-soft)]">
              {mode === "archive"
                ? ".hydroproj.zip dosyası seçin"
                : mode === "desktop_db"
                  ? "hydro.db dosyası seçin"
                  : "Masaüstü snapshot (.json) dosyası seçin"}
            </label>
            <input
              ref={fileInputRef}
              id={fileInputId}
              type="file"
              accept={
                mode === "archive"
                  ? ".zip,.hydroproj.zip"
                  : mode === "desktop_db"
                    ? ".db,.sqlite,.sqlite3"
                    : "application/json,.json"
              }
              className="mt-2 block w-full text-[12px] text-[var(--text-muted)] file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--primary-soft)] file:px-3 file:py-1.5 file:text-[12px] file:font-semibold file:text-[var(--primary)]"
              onChange={handleFileChange}
            />
            {file ? (
              <p className="mt-2 font-mono text-[11px] text-[var(--text-faint)]">
                Seçilen: {file.name} ({Math.round(file.size / 1024)} KB)
              </p>
            ) : null}
          </div>

          {mode === "desktop_json" ? (
            <FieldGrid cols={2}>
              <TextField
                label="Kesit / oturum adı (isteğe bağlı)"
                value={targetName}
                onChange={setTargetName}
                placeholder="Otomatik verilir"
                maxLength={200}
              />
              <SelectField
                label="Hedef proje"
                value={targetProjectId}
                onChange={setTargetProjectId}
                options={[
                  { value: "__none__", label: "Bağımsız oturum (proje yok)" },
                  ...realProjects.map((project) => ({
                    value: project.id,
                    label: project.code ? `${project.code} · ${project.name}` : project.name,
                  })),
                ]}
              />
            </FieldGrid>
          ) : (
            <FieldGrid cols={2}>
              <TextField
                label="Hedef proje adı (isteğe bağlı)"
                value={targetName}
                onChange={setTargetName}
                placeholder="Arşiv / varsayılan adı kullan"
              />
              <TextField
                label="Hedef proje kodu (isteğe bağlı)"
                value={targetCode}
                onChange={setTargetCode}
                placeholder="İsteğe bağlı"
              />
            </FieldGrid>
          )}

          {mode === "archive" ? (
            <CheckboxRow
              checked={includeAttachments}
              onChange={setIncludeAttachments}
              label="Arşivdeki PDF ve görsel form eklerini de içe aktar"
            />
          ) : null}

          {snapshotOutcome ? (
            <InlineNotice
              tone={
                snapshotOutcome.mapping.warnings.length > 0 ||
                snapshotOutcome.mapping.invalid_fields.length > 0
                  ? "warning"
                  : "info"
              }
              title={`Kesit oluşturuldu: ${snapshotOutcome.session.name}`}
            >
              <div className="space-y-1 text-[11.5px]">
                <p>
                  <strong>{snapshotOutcome.mapping.converted}</strong> alan dönüştürüldü
                  {snapshotOutcome.mapping.skipped.length > 0
                    ? ` · Atlanan (${snapshotOutcome.mapping.skipped.length}): ${snapshotOutcome.mapping.skipped.join(", ")}`
                    : ""}
                </p>
                {snapshotOutcome.mapping.invalid_fields.length > 0 ? (
                  <p>Geçersiz alanlar: {snapshotOutcome.mapping.invalid_fields.join(", ")}</p>
                ) : null}
                {snapshotOutcome.mapping.warnings.length > 0 ? (
                  <ul className="list-disc pl-4">
                    {snapshotOutcome.mapping.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </InlineNotice>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
