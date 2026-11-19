import { useState, type ChangeEvent } from "react";
import { Archive, Database, FileUp, Sparkles } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Dialog";
import { CheckboxRow, FieldGrid, NumberField, SelectField, TextField } from "../../components/ui/Field";
import { InlineNotice } from "../../components/ui/State";
import {
  useGenerateSampleProject,
  useImportDesktopDb,
  useImportProjectArchive,
} from "../../hooks/queries";
import type { Project } from "../../lib/types";
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
}: {
  open: boolean;
  onClose: () => void;
  onImported?: (project: Project) => void;
}) {
  const pushToast = useAppStore((s) => s.pushToast);
  const importArchive = useImportProjectArchive();
  const importDesktopDb = useImportDesktopDb();

  const [mode, setMode] = useState<"archive" | "desktop_db">("archive");
  const [file, setFile] = useState<File | null>(null);
  const [targetName, setTargetName] = useState("");
  const [targetCode, setTargetCode] = useState("");
  const [includeAttachments, setIncludeAttachments] = useState(true);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    setFile(picked);
  }

  function submit() {
    if (!file) {
      pushToast("warning", "Dosya seçilmedi", "Lütfen geçerli bir paket veya .db dosyası seçin.");
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
            setFile(null);
            onClose();
          },
        },
      );
    } else {
      importDesktopDb.mutate(
        {
          file,
          projectName: targetName.trim() || undefined,
          projectCode: targetCode.trim() || undefined,
        },
        {
          onSuccess: (res) => {
            onImported?.(res.project);
            setFile(null);
            onClose();
          },
        },
      );
    }
  }

  const busy = importArchive.isPending || importDesktopDb.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Proje Paketi veya Masaüstü DB İçe Aktar"
      description="Başka bir bilgisayardan dışa aktarılan .hydroproj.zip paketini veya eski masaüstü hydro.db SQLite veritabanını yeni bir projeye aktarın."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" icon={<FileUp size={14} />} loading={busy} onClick={submit}>
            İçe Aktar
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="seg-control" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "archive"}
            className="seg-btn"
            onClick={() => {
              setMode("archive");
              setFile(null);
            }}
          >
            <Archive size={13} className="mr-1 inline" />
            .hydroproj.zip Arşiv Paketi
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "desktop_db"}
            className="seg-btn"
            onClick={() => {
              setMode("desktop_db");
              setFile(null);
            }}
          >
            <Database size={13} className="mr-1 inline" />
            Masaüstü hydro.db (SQLite)
          </button>
        </div>

        <InlineNotice
          tone="info"
          title={mode === "archive" ? "SHA-256 Bütünlük Doğrulamalı Paket" : "Eski Masaüstü Veritabanı Aktarımı"}
          icon={mode === "archive" ? Archive : Database}
        >
          {mode === "archive"
            ? "Arşivdeki tüm dosyalar SHA-256 manifestine göre doğrulanır, kesitler ve formlar yeni kimliklerle güvenle içeri alınır."
            : "Masaüstü uygulamasının hydro.db dosyasındaki sessions, geometry_records, test_entries ve time_series_records tabloları okunur."}
        </InlineNotice>

        <div className="rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-2)] p-4">
          <label className="block text-[12px] font-medium text-[var(--text-soft)]">
            {mode === "archive" ? ".hydroproj.zip dosyası seçin" : "hydro.db dosyası seçin"}
          </label>
          <input
            type="file"
            accept={mode === "archive" ? ".zip,.hydroproj.zip" : ".db,.sqlite,.sqlite3"}
            className="mt-2 block w-full text-[12px] text-[var(--text-muted)] file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--primary-soft)] file:px-3 file:py-1.5 file:text-[12px] file:font-semibold file:text-[var(--primary)]"
            onChange={handleFileChange}
          />
          {file ? (
            <p className="mt-2 font-mono text-[11px] text-[var(--text-faint)]">
              Seçilen: {file.name} ({Math.round(file.size / 1024)} KB)
            </p>
          ) : null}
        </div>

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

        {mode === "archive" ? (
          <CheckboxRow
            checked={includeAttachments}
            onChange={setIncludeAttachments}
            label="Arşivdeki PDF ve görsel form eklerini de içe aktar"
          />
        ) : null}
      </div>
    </Modal>
  );
}
