import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  HardDriveDownload,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api, apiErrorMessage } from "../../lib/api";
import { downloadBlob } from "../../lib/report";
import { dateTime } from "../../lib/format";
import {
  useApplyUpdate,
  useCheckUpdates,
  useStartUpdateDownload,
  useUpdateStatus,
} from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Dialog";
import { HydroLogo } from "../ui/HydroLogo";
import { InlineNotice } from "../ui/State";

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function assetKindLabel(kind: string, name: string): string {
  if (kind === "macos_arm64_dmg") return "macOS Apple Silicon M1+ (.dmg)";
  if (kind === "macos_universal_dmg") return "macOS Universal (.dmg)";
  if (kind === "windows_setup_exe") return "Windows 64-bit Kurulum (.exe)";
  if (kind === "windows_portable_zip") return "Windows Taşınabilir (.zip)";
  return name;
}

export function UpdateManagerModal() {
  const open = useAppStore((state) => state.updateModalOpen);
  const setOpen = useAppStore((state) => state.setUpdateModalOpen);
  const backend = useAppStore((state) => state.backend);
  const pushToast = useAppStore((state) => state.pushToast);

  const statusQuery = useUpdateStatus();
  const checkUpdates = useCheckUpdates();
  const startDownload = useStartUpdateDownload();
  const applyUpdate = useApplyUpdate();

  const status = statusQuery.data;
  const [chosenAsset, setChosenAsset] = useState<string>("");
  const [savingFile, setSavingFile] = useState(false);

  const autoCheckedOnOpenRef = useRef(false);

  useEffect(() => {
    if (!open) {
      autoCheckedOnOpenRef.current = false;
      return;
    }
    if (
      backend === "online" &&
      status &&
      !status.checked &&
      !checkUpdates.isPending &&
      !autoCheckedOnOpenRef.current
    ) {
      autoCheckedOnOpenRef.current = true;
      checkUpdates.mutate({ force: false, silent: true });
    }
  }, [open, backend, status, checkUpdates]);

  useEffect(() => {
    if (!status) return;
    if (status.selected_asset && (!chosenAsset || !status.all_assets.some((a) => a.name === chosenAsset))) {
      setChosenAsset(status.selected_asset.name);
    } else if (!chosenAsset && status.all_assets.length > 0) {
      setChosenAsset(status.all_assets[0].name);
    }
  }, [status, chosenAsset]);

  const job = status?.job;
  const isBusy =
    checkUpdates.isPending ||
    startDownload.isPending ||
    applyUpdate.isPending ||
    job?.state === "downloading" ||
    job?.state === "verifying" ||
    job?.state === "installing";

  const readyToInstall =
    job?.state === "ready_to_install" &&
    (!chosenAsset || job.asset_name === chosenAsset);

  async function saveVerifiedInstaller() {
    if (!job?.asset_name) return;
    setSavingFile(true);
    try {
      const result = await api.downloadVerifiedUpdateFile(job.asset_name);
      downloadBlob(result.blob, result.filename);
      pushToast("success", "Kurulum paketi indirildi", result.filename);
    } catch (err) {
      pushToast("error", "Kurulum paketi alınamadı", apiErrorMessage(err));
    } finally {
      setSavingFile(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      title={
        <span className="inline-flex items-center gap-2.5">
          <HydroLogo size={24} />
          <span>HYDRO Web Güncelleme Yöneticisi</span>
        </span>
      }
      description="GitHub Releases üzerinden yeni HydroWeb sürümlerini denetleyin, SHA-256 ve Ed25519 dijital imzasıyla doğrulayıp kurun."
      className="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Kapat
          </Button>
          <Button
            icon={<RefreshCw size={14} />}
            loading={checkUpdates.isPending}
            disabled={backend !== "online" || isBusy}
            onClick={() => checkUpdates.mutate({ force: true })}
          >
            Güncellemeleri Denetle
          </Button>
          {status?.all_assets.length && !readyToInstall ? (
            <Button
              variant="primary"
              icon={<Download size={14} />}
              loading={startDownload.isPending || job?.state === "downloading" || job?.state === "verifying"}
              disabled={backend !== "online" || isBusy || !chosenAsset}
              onClick={() => startDownload.mutate({ assetName: chosenAsset })}
            >
              Doğrula ve İndir
            </Button>
          ) : null}
          {readyToInstall ? (
            <Button
              icon={<HardDriveDownload size={14} />}
              loading={savingFile}
              onClick={() => void saveVerifiedInstaller()}
            >
              Doğrulanmış Paketi Kaydet
            </Button>
          ) : null}
          {readyToInstall && status?.runtime.can_self_install ? (
            <Button
              variant="primary"
              icon={<RotateCcw size={14} />}
              loading={applyUpdate.isPending || job?.state === "installing"}
              onClick={() => applyUpdate.mutate()}
            >
              Şimdi Kur ve Yeniden Başlat
            </Button>
          ) : null}
        </>
      }
    >
      <div className="space-y-4">
        {backend !== "online" ? (
          <InlineNotice tone="warning" title="Sunucu bağlı değil">
            Güncelleme denetimi için backend sunucusunun çalışıyor olması gerekir.
          </InlineNotice>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
              Yüklü Sürüm
            </span>
            <p className="mt-1 font-mono text-base font-bold text-[var(--text)]">
              v{status?.current_version ?? "1.9.1"}
            </p>
            <p className="mt-0.5 text-[10.5px] text-[var(--text-muted)]">
              {status?.runtime.frozen ? "Paketli Masaüstü (HydroWeb)" : "Kaynak / Web Sunucu Modu"}
            </p>
          </div>

          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
              Son Release Sürümü
            </span>
            <div className="mt-1 flex items-center gap-2">
              <p className="font-mono text-base font-bold text-[var(--text)]">
                {status?.latest_version ? `v${status.latest_version}` : "—"}
              </p>
              {status?.checked ? (
                <Badge tone={status.update_available ? "pass" : "neutral"}>
                  {status.update_available ? "Yeni Sürüm" : "Güncel"}
                </Badge>
              ) : null}
            </div>
            <p className="mt-0.5 text-[10.5px] text-[var(--text-muted)]">
              {status?.published_at ? dateTime(status.published_at) : "Henüz denetlenmedi"}
            </p>
          </div>

          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
              Güvenlik & Doğrulama
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Badge tone={job?.sha256_verified ? "pass" : "info"}>
                <ShieldCheck size={11} className="mr-1" aria-hidden />
                {job?.sha256_verified ? "SHA-256 Doğrulandı" : "SHA-256 Zorunlu"}
              </Badge>
              <Badge tone={job?.signature_verified ? "pass" : "info"}>
                {job?.signature_verified ? "Ed25519 İmzalı" : "Ed25519 Fail-Closed"}
              </Badge>
            </div>
          </div>
        </div>

        {status?.check_error ? (
          <InlineNotice tone="warning" title="Release sunucu mesajı">
            {status.check_error}
          </InlineNotice>
        ) : null}

        {status?.update_available ? (
          <InlineNotice tone="success" title={`HydroWeb v${status.latest_version} yayında`} icon={Sparkles}>
            Yeni sürüm paketleri aşağıdan platformunuza göre seçilip SHA-256 + Ed25519 dijital imzasıyla
            doğrulanarak indirilebilir.
          </InlineNotice>
        ) : status?.checked && !status.check_error ? (
          <InlineNotice tone="info" title="Uygulama güncel" icon={CheckCircle2}>
            Yüklü HydroWeb sürümünüz (v{status.current_version}) yayınlanan en son sürümdür.
          </InlineNotice>
        ) : null}

        {status?.all_assets.length ? (
          <div className="space-y-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-[var(--text)]">
                Kurulum Paketi Seçimi
              </span>
              {status.html_url ? (
                <a
                  href={status.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--primary)] hover:underline"
                >
                  GitHub Release Sayfası <ExternalLink size={11} aria-hidden />
                </a>
              ) : null}
            </div>
            <div className="space-y-1.5">
              {status.all_assets.map((asset) => {
                const selected = asset.name === chosenAsset;
                return (
                  <label
                    key={asset.name}
                    className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition-colors ${
                      selected
                        ? "border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--text)]"
                        : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-soft)] hover:border-[var(--border-strong)]"
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <input
                        type="radio"
                        name="hydroweb-asset"
                        checked={selected}
                        disabled={isBusy}
                        onChange={() => setChosenAsset(asset.name)}
                      />
                      <span className="truncate font-medium">
                        {assetKindLabel(asset.kind, asset.name)}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[10.5px] text-[var(--text-muted)]">
                      {formatBytes(asset.size)}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        ) : null}

        {job && (job.state === "downloading" || job.state === "verifying" || job.state === "ready_to_install" || job.state === "installing" || job.state === "restarting" || job.state === "failed") ? (
          <div className="space-y-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-[var(--text)]">
                {job.message || job.state}
              </span>
              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                {job.total_bytes > 0
                  ? `${formatBytes(job.downloaded_bytes)} / ${formatBytes(job.total_bytes)} (%${job.progress_pct.toFixed(0)})`
                  : `${job.progress_pct.toFixed(0)}%`}
              </span>
            </div>
            <progress
              value={job.progress_pct}
              max={100}
              className="h-2 w-full accent-[var(--primary)]"
            />
            {job.error ? (
              <p className="text-[11px] font-medium text-[var(--danger)]">{job.error}</p>
            ) : null}
          </div>
        ) : null}

        {status && !status.runtime.can_self_install ? (
          <p className="text-[11px] leading-relaxed text-[var(--text-muted)]">
            Not: Sunucu şu anda geliştirme / kaynak modunda çalışıyor ({status.runtime.platform}).
            Paketi “Doğrula ve İndir” ile sunucuda SHA-256 + Ed25519 imza kontrolünden geçirdikten sonra
            “.dmg” veya “Setup.exe” kurulumunu bilgisayarınıza kaydedip çalıştırabilirsiniz.
          </p>
        ) : null}

        {status?.release_notes ? (
          <div className="space-y-1">
            <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-faint)]">
              Sürüm Notları
            </span>
            <pre className="max-h-36 overflow-y-auto whitespace-pre-wrap rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3 font-sans text-[11.5px] leading-relaxed text-[var(--text-soft)] scroll-thin">
              {status.release_notes}
            </pre>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
