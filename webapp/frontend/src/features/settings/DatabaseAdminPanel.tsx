import { useRef, useState, type ChangeEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArchiveRestore,
  Database,
  Download,
  HardDrive,
  KeyRound,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Upload,
  Wrench,
} from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { KpiCard, SectionCard } from "../../components/ui/Card";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { CheckboxRow, FieldGrid, TextField } from "../../components/ui/Field";
import { EmptyState, InlineNotice } from "../../components/ui/State";
import {
  useClaimWorkspace,
  useCreateDbBackup,
  useDbBackups,
  useDbStats,
  useMeta,
  usePurgeTrashItem,
  useRestoreDbBackup,
  useRestoreTrashItem,
  useRunDbMaintenance,
  useTrash,
  useWorkspaces,
} from "../../hooks/queries";
import { ApiError, api, apiErrorMessage, getAdminToken, setAdminToken, setWorkspaceId } from "../../lib/api";
import { dateTime, fmt, num } from "../../lib/format";
import { downloadBlob } from "../../lib/report";
import type { TrashItem } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";

type DbAdminTab = "overview" | "backups" | "trash" | "workspaces";

export function DatabaseAdminPanel() {
  const backend = useAppStore((s) => s.backend);
  const pushToast = useAppStore((s) => s.pushToast);
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<DbAdminTab>("overview");
  const [downloadingBackup, setDownloadingBackup] = useState<string | null>(null);

  // Bakım seçenekleri
  const [checkpointWal, setCheckpointWal] = useState(true);
  const [cleanExports, setCleanExports] = useState(true);
  const [cleanOrphanUploads, setCleanOrphanUploads] = useState(false);
  const [vacuumDb, setVacuumDb] = useState(false);

  // Onay diyalogları
  const [confirmRestoreName, setConfirmRestoreName] = useState<string | null>(null);
  const [pendingRestoreFile, setPendingRestoreFile] = useState<File | null>(null);
  const [confirmPurgeItem, setConfirmPurgeItem] = useState<TrashItem | null>(null);
  const [confirmClaimHash, setConfirmClaimHash] = useState<string | null>(null);
  const [claimSourceKey, setClaimSourceKey] = useState("");
  const [customWorkspaceKey, setCustomWorkspaceKey] = useState("");
  const [adminTokenInput, setAdminTokenInput] = useState(() => getAdminToken());
  const [savedAdminToken, setSavedAdminToken] = useState(() => getAdminToken());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const online = backend === "online";
  const metaQuery = useMeta();
  const statsQuery = useDbStats(online);
  const backupsQuery = useDbBackups(online && tab === "backups");
  const trashQuery = useTrash(online && tab === "trash");
  const workspacesQuery = useWorkspaces(online && tab === "workspaces");

  const createBackup = useCreateDbBackup();
  const restoreBackup = useRestoreDbBackup();
  const restoreTrash = useRestoreTrashItem();
  const purgeTrash = usePurgeTrashItem();
  const claimWorkspace = useClaimWorkspace();
  const runMaintenance = useRunDbMaintenance();

  async function handleDownloadBackup(filename: string) {
    setDownloadingBackup(filename);
    try {
      const res = await api.downloadDbBackup(filename);
      downloadBlob(res.blob, res.filename);
      pushToast("success", "Yedek dosyası indirildi", res.filename);
    } catch (error) {
      pushToast("error", "Yedek indirilemedi", apiErrorMessage(error));
    } finally {
      setDownloadingBackup(null);
    }
  }

  function handleRestoreFilePick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    e.target.value = "";
    if (!file) return;
    setPendingRestoreFile(file);
  }

  function handleSwitchWorkspaceKey() {
    const clean = customWorkspaceKey.trim();
    if (!clean) {
      pushToast("warning", "Geçerli bir workspace anahtarı girin");
      return;
    }
    setWorkspaceId(clean);
    setCustomWorkspaceKey("");
    void queryClient.invalidateQueries();
    pushToast("success", "Çalışma alanı anahtarı güncellendi", "Projeler ve kesitler yeniden yükleniyor.");
  }

  function handleSaveAdminToken() {
    const saved = setAdminToken(adminTokenInput);
    setSavedAdminToken(saved);
    setAdminTokenInput(saved);
    void queryClient.invalidateQueries();
    pushToast(
      saved ? "success" : "info",
      saved ? "Yönetici anahtarı kaydedildi" : "Yönetici anahtarı temizlendi",
      "Bu sekme oturumu boyunca X-Hydro-Admin-Token başlığı gönderilecek.",
    );
  }

  const isAuth403 = statsQuery.error instanceof ApiError && statsQuery.error.status === 403;
  const showAdminTokenBar =
    Boolean(metaQuery.data?.features?.admin_token_configured) ||
    metaQuery.data?.features?.is_loopback_host === false ||
    Boolean(savedAdminToken) ||
    isAuth403;

  const stats = statsQuery.data;

  return (
    <SectionCard
      title="Veritabanı Yönetimi & Veri Koruma"
      description="Yerel SQLite veritabanının şema durumu, anlık yedekleme/geri yükleme, çöp kutusu, çalışma alanı kurtarma ve bakım araçları."
      icon={Database}
      action={
        stats ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="info">Şema v{stats.schema_migration}</Badge>
            <Badge tone={stats.integrity_status === "ok" ? "pass" : "warning"}>
              {stats.integrity_status === "ok" ? "Bütünlük OK" : stats.integrity_status}
            </Badge>
          </div>
        ) : null
      }
    >
      {!online ? (
        <InlineNotice tone="warning" title="Sunucu çevrimdışı" icon={Database}>
          Veritabanı yedekleme, çöp kutusu ve bakım araçları için HYDRO sunucu bağlantısı gereklidir.
        </InlineNotice>
      ) : (
        <div className="space-y-4">
          {showAdminTokenBar ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-[220px] flex-1">
                  <TextField
                    label="Yönetici Anahtarı (X-Hydro-Admin-Token)"
                    type="password"
                    autoComplete="off"
                    value={adminTokenInput}
                    onChange={setAdminTokenInput}
                    placeholder="X-Hydro-Admin-Token anahtarını girin..."
                  />
                </div>
                <Button size="sm" variant="primary" icon={<KeyRound size={13} />} onClick={handleSaveAdminToken}>
                  Anahtarı Kaydet
                </Button>
                {savedAdminToken ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setAdminToken("");
                      setSavedAdminToken("");
                      setAdminTokenInput("");
                      void queryClient.invalidateQueries();
                    }}
                  >
                    Temizle
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="seg-control" role="tablist" aria-label="Veritabanı yönetimi sekmeleri">
            {[
              { id: "overview" as const, label: "Durum & Bakım" },
              { id: "backups" as const, label: "Yedekleme & Geri Yükleme" },
              { id: "trash" as const, label: "Çöp Kutusu" },
              { id: "workspaces" as const, label: "Çalışma Alanı Kurtarma" },
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
            statsQuery.isError ? (
              <InlineNotice tone="warning" title="Veritabanı bilgisi alınamadı" icon={Database}>
                {apiErrorMessage(statsQuery.error)}
              </InlineNotice>
            ) : stats ? (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <KpiCard
                    label="Veritabanı Boyutu"
                    value={fmt.bytes(stats.db_size_bytes)}
                    hint={`WAL: ${fmt.bytes(stats.wal_size_bytes)} · ${stats.journal_mode}`}
                    icon={HardDrive}
                  />
                  <KpiCard
                    label="Aktif Kayıtlar"
                    value={`${stats.table_counts.projects ?? 0} / ${stats.table_counts.sessions ?? 0}`}
                    hint={`Proje / Kesit · ${stats.table_counts.section_forms ?? 0} Form`}
                    icon={Database}
                    tone="info"
                  />
                  <KpiCard
                    label="Disk Kullanımı"
                    value={fmt.bytes(
                      stats.storage.uploads_bytes +
                        stats.storage.exports_bytes +
                        stats.storage.backups_bytes,
                    )}
                    hint={`Ek: ${stats.storage.uploads_files} · Çıktı: ${stats.storage.exports_files} · Yedek: ${stats.storage.backups_count}`}
                    icon={ShieldCheck}
                  />
                  <KpiCard
                    label="Çöp / Çalışma Alanı"
                    value={
                      (stats.table_counts.projects_deleted ?? 0) +
                      (stats.table_counts.sessions_deleted ?? 0)
                    }
                    unit="silinmiş"
                    hint={`${stats.workspace_count} çalışma alanı tespit edildi`}
                    icon={Trash2}
                  />
                </div>

                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5 space-y-3">
                  <p className="text-[12px] font-semibold text-[var(--text)]">
                    Bakım ve Temizlik İşlemleri
                  </p>
                  <FieldGrid cols={2}>
                    <CheckboxRow
                      checked={checkpointWal}
                      onChange={setCheckpointWal}
                      label="WAL Checkpoint (TRUNCATE)"
                      hint="Bekleyen yazma günlüklerini ana .db dosyasına birleştirir."
                    />
                    <CheckboxRow
                      checked={cleanExports}
                      onChange={setCleanExports}
                      label="Geçici çıktı dosyalarını temizle (exports/)"
                      hint="Eski indirilebilir rapor kopyalarını silerek alan açar."
                    />
                    <CheckboxRow
                      checked={cleanOrphanUploads}
                      onChange={setCleanOrphanUploads}
                      label="Sahipsiz (orphan) yükleme dosyalarını temizle"
                      hint="Tüm çalışma alanlarındaki DB ekleriyle eşleşmeyen dosyaları kaldırır."
                    />
                    <CheckboxRow
                      checked={vacuumDb}
                      onChange={setVacuumDb}
                      label="SQLite VACUUM uygula"
                      hint="Silinen kayıtlardan kalan boş sayfaları sıkıştırır."
                    />
                  </FieldGrid>
                  <div className="flex justify-end">
                    <Button
                      variant="primary"
                      icon={<Wrench size={14} />}
                      loading={runMaintenance.isPending}
                      onClick={() =>
                        runMaintenance.mutate({
                          checkpoint_wal: checkpointWal,
                          vacuum: vacuumDb,
                          clean_exports: cleanExports,
                          clean_orphan_uploads: cleanOrphanUploads,
                        })
                      }
                    >
                      Bütünlük Kontrolü &amp; Bakım Çalıştır
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-[var(--text-muted)]">
                Veritabanı istatistikleri yükleniyor...
              </div>
            )
          ) : null}

          {tab === "backups" ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[11.5px] text-[var(--text-muted)]">
                  Online SQLite backup API kullanarak kesintisiz anlık yedek alır; geri yükleme
                  öncesinde otomatik güvenlik kopyası (pre-restore) oluşturulur.
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".db,.sqlite,.sqlite3"
                    className="hidden"
                    onChange={handleRestoreFilePick}
                  />
                  <Button
                    size="sm"
                    icon={<Upload size={13} />}
                    loading={restoreBackup.isPending}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Dosyadan (.db) Geri Yükle
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    icon={<ArchiveRestore size={13} />}
                    loading={createBackup.isPending}
                    onClick={() => createBackup.mutate("manual")}
                  >
                    Anlık Yedek Al
                  </Button>
                </div>
              </div>

              {(backupsQuery.data?.items ?? []).length === 0 ? (
                <EmptyState
                  title="Henüz yerel yedek yok"
                  description="'Anlık Yedek Al' ile mevcut veritabanının tam kopyasını oluşturabilirsiniz."
                  icon={ArchiveRestore}
                />
              ) : (
                <div className="table-wrap scroll-thin">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Yedek Dosyası</th>
                        <th className="num">Boyut</th>
                        <th>Oluşturulma</th>
                        <th>İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(backupsQuery.data?.items ?? []).map((bkp) => (
                        <tr key={bkp.filename}>
                          <td className="font-mono text-[11px]">{bkp.filename}</td>
                          <td className="num">{fmt.bytes(bkp.size_bytes)}</td>
                          <td className="text-[11px]">{dateTime(bkp.created_at ?? "")}</td>
                          <td>
                            <div className="flex flex-wrap gap-1.5">
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={<Download size={12} />}
                                loading={downloadingBackup === bkp.filename}
                                onClick={() => handleDownloadBackup(bkp.filename)}
                              >
                                İndir
                              </Button>
                              <Button
                                size="sm"
                                variant="danger"
                                icon={<RotateCcw size={12} />}
                                onClick={() => setConfirmRestoreName(bkp.filename)}
                              >
                                Geri Yükle
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}

          {tab === "trash" ? (
            (trashQuery.data?.items ?? []).length === 0 ? (
              <EmptyState
                title="Çöp kutusu boş"
                description="Silinen proje ve kesitler kalıcı olarak silinene kadar burada tutulur."
                icon={Trash2}
              />
            ) : (
              <div className="table-wrap scroll-thin">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Tür</th>
                      <th>Ad / Kod</th>
                      <th>Silinme</th>
                      <th>İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(trashQuery.data?.items ?? []).map((item) => (
                      <tr key={`${item.entity_type}-${item.id}`}>
                        <td>
                          <Badge tone="neutral">
                            {item.entity_type === "project" ? "Proje" : "Kesit"}
                          </Badge>
                        </td>
                        <td>
                          <span className="font-medium text-[var(--text)]">{item.name}</span>
                          {item.code ? (
                            <span className="ml-2 font-mono text-[10.5px] text-[var(--text-faint)]">
                              {item.code}
                            </span>
                          ) : null}
                        </td>
                        <td className="text-[11px]">{dateTime(item.deleted_at ?? "")}</td>
                        <td>
                          <div className="flex flex-wrap gap-1.5">
                            <Button
                              size="sm"
                              variant="primary"
                              icon={<RotateCcw size={12} />}
                              loading={restoreTrash.isPending}
                              onClick={() =>
                                restoreTrash.mutate({
                                  entityType: item.entity_type,
                                  entityId: item.id,
                                })
                              }
                            >
                              Geri Yükle
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              icon={<Trash2 size={12} />}
                              loading={purgeTrash.isPending}
                              onClick={() => setConfirmPurgeItem(item)}
                            >
                              Kalıcı Sil
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : null}

          {tab === "workspaces" ? (
            <div className="space-y-3">
              <InlineNotice tone="info" title="Tarayıcı Önbelleği Temizlenirse Verinizi Kurtarın" icon={KeyRound}>
                Projeleriniz tarayıcının çalışma alanı kimliğine (X-Session-ID) göre izole edilir.
                Başka bir oturumda kalmış projeleri tek tıkla mevcut çalışma alanınıza
                taşıyabilirsiniz.
              </InlineNotice>

              <div className="table-wrap scroll-thin">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Çalışma Alanı Özeti</th>
                      <th className="num">Proje</th>
                      <th className="num">Kesit</th>
                      <th>Örnek Projeler</th>
                      <th>İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(workspacesQuery.data?.items ?? []).map((ws) => (
                      <tr key={ws.workspace_hash}>
                        <td className="font-mono text-[11px]">
                          {ws.hash_short}...{" "}
                          {ws.is_current ? <Badge tone="pass">Aktif</Badge> : null}
                        </td>
                        <td className="num">{num(ws.project_count, 0)}</td>
                        <td className="num">{num(ws.section_count, 0)}</td>
                        <td className="max-w-[260px] truncate text-[11px]">
                          {ws.sample_projects.join(", ") || "—"}
                        </td>
                        <td>
                          {ws.is_current ? (
                            <span className="text-[11px] text-[var(--text-faint)]">Geçerli alan</span>
                          ) : (
                            <Button
                              size="sm"
                              variant="primary"
                              loading={claimWorkspace.isPending}
                              onClick={() => setConfirmClaimHash(ws.workspace_hash)}
                            >
                              Bu Alana Devral
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <TextField
                  label="Özel çalışma alanı anahtarına geç (opsiyonel)"
                  value={customWorkspaceKey}
                  onChange={setCustomWorkspaceKey}
                  placeholder="Bilinen X-Session-ID anahtarını girin"
                  className="min-w-[260px] flex-1"
                />
                <Button size="sm" icon={<KeyRound size={13} />} onClick={handleSwitchWorkspaceKey}>
                  Anahtarı Uygula
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(confirmRestoreName)}
        title="Veritabanı geri yüklensin mi?"
        message={
          <span>
            <strong>{confirmRestoreName}</strong> yedeği mevcut veritabanının yerine yüklenecek.
            Güvenlik için önce otomatik bir pre-restore yedeği alınır.
          </span>
        }
        confirmLabel="Geri Yükle"
        danger
        onConfirm={() => {
          if (confirmRestoreName) {
            restoreBackup.mutate({ backupFilename: confirmRestoreName });
          }
        }}
        onClose={() => setConfirmRestoreName(null)}
      />

      <ConfirmDialog
        open={Boolean(pendingRestoreFile)}
        title="Dosyadan veritabanı geri yüklensin mi?"
        message={
          <span>
            <strong>{pendingRestoreFile?.name}</strong> dosyası bütünlük kontrolünden geçirildikten
            sonra aktif veritabanının yerine kopyalanacaktır.
          </span>
        }
        confirmLabel="Dosyadan Yükle"
        danger
        onConfirm={() => {
          if (pendingRestoreFile) {
            restoreBackup.mutate({ file: pendingRestoreFile });
          }
        }}
        onClose={() => setPendingRestoreFile(null)}
      />

      <ConfirmDialog
        open={Boolean(confirmPurgeItem)}
        title="Kayıt kalıcı olarak silinsin mi?"
        message={
          <span>
            <strong>{confirmPurgeItem?.name}</strong> ve ilişkili tüm ekler geri döndürülemeyecek
            biçimde silinecek.
          </span>
        }
        confirmLabel="Kalıcı Sil"
        danger
        onConfirm={() => {
          if (confirmPurgeItem) {
            purgeTrash.mutate({
              entityType: confirmPurgeItem.entity_type,
              entityId: confirmPurgeItem.id,
            });
          }
        }}
        onClose={() => setConfirmPurgeItem(null)}
      />

      <ConfirmDialog
        open={Boolean(confirmClaimHash)}
        title="Çalışma alanı verileri devralınsın mı?"
        message={
          <div className="space-y-3">
            <p>
              Seçili çalışma alanındaki tüm proje, kesit, BOTAŞ form ve ek kayıtları mevcut
              çalışma alanınıza taşınacak.
            </p>
            <TextField
              label="Kaynak çalışma alanı anahtarı (X-Session-ID)"
              value={claimSourceKey}
              onChange={setClaimSourceKey}
              placeholder="Kaynak tarayıcı X-Session-ID"
              help="HYDRO_ALLOW_WORKSPACE_CLAIM=1 açık değilse kaynak çalışma alanı anahtarı zorunludur."
            />
          </div>
        }
        confirmLabel="Devral"
        onConfirm={() => {
          if (confirmClaimHash) {
            const keyTrimmed = claimSourceKey.trim();
            claimWorkspace.mutate({
              sourceHash: confirmClaimHash,
              sourceKey: keyTrimmed || undefined,
            });
            setClaimSourceKey("");
          }
        }}
        onClose={() => {
          setConfirmClaimHash(null);
          setClaimSourceKey("");
        }}
      />
    </SectionCard>
  );
}
