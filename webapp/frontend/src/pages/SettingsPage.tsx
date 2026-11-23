import { useState } from "react";
import {
  ArrowUpCircle,
  Database,
  Eye,
  Info,
  KeyRound,
  Monitor,
  Palette,
  RefreshCw,
  ScanLine,
  Settings,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { SelectField } from "../components/ui/Field";
import { ConfirmDialog } from "../components/ui/Dialog";
import { InlineNotice, OfflineNotice } from "../components/ui/State";
import { useCheckUpdates, useMeta, useOcrStatus, useUpdateStatus } from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { getWorkspaceId } from "../lib/api";
import { STEEL_MODEL_OPTIONS, STEEL_PRESETS } from "../lib/constants";
import { dateTime, fmt, formatCoefficientState, num } from "../lib/format";
import { cn } from "../lib/utils";
import { DatabaseAdminPanel } from "../features/settings/DatabaseAdminPanel";

export function SettingsPage() {
  const meta = useMeta().data;
  const ocr = useOcrStatus().data;
  const queryClient = useQueryClient();

  const backend = useAppStore((state) => state.backend);
  const health = useAppStore((state) => state.health);
  const sessionApiReady = useAppStore((state) => state.sessionApiReady);
  const lastCheck = useAppStore((state) => state.lastBackendCheck);
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const toggleRightPanel = useAppStore((state) => state.toggleRightPanel);
  const inputs = useAppStore((state) => state.inputs);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const sessionId = useAppStore((state) => state.sessionId);
  const sessionName = useAppStore((state) => state.sessionName);
  const sessionStatus = useAppStore((state) => state.sessionStatus);
  const revision = useAppStore((state) => state.revision);
  const dirty = useAppStore((state) => state.dirty);
  const sessionCount = useAppStore((state) => state.history.length);
  const resetSession = useAppStore((state) => state.resetSession);
  const clearLocalData = useAppStore((state) => state.clearLocalData);
  const pushToast = useAppStore((state) => state.pushToast);
  const setTab = useAppStore((state) => state.setTab);
  const setUpdateModalOpen = useAppStore((state) => state.setUpdateModalOpen);

  const updateStatus = useUpdateStatus().data;
  const checkUpdates = useCheckUpdates();

  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const workspace = getWorkspaceId();

  function copyWorkspace() {
    void navigator.clipboard
      .writeText(workspace)
      .then(() => pushToast("success", "Workspace anahtarı kopyalandı"))
      .catch(() => pushToast("error", "Kopyalanamadı", "Tarayıcı pano iznini kontrol edin."));
  }

  function retryBackend() {
    void queryClient.invalidateQueries({ queryKey: ["health"] });
    void queryClient.invalidateQueries({ queryKey: ["meta"] });
    void queryClient.invalidateQueries({ queryKey: ["catalog"] });
    pushToast("info", "Bağlantı yeniden kontrol ediliyor", "Sonuç birkaç saniye içinde güncellenir.");
  }

  const backendTone = backend === "online" ? "pass" : backend === "demo" ? "warning" : "pending";

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Ayarlar"
        title="Hesaplama, görünüm ve bölüm yönetimi"
        description="Backend bağlantısı, varsayılan katsayı kaynakları, tema ve yerel veri yönetimi."
        meta={
          <>
            <Badge tone={backendTone}>
              {backend === "online" ? "Sunucu bağlı" : backend === "demo" ? "Çevrimdışı" : "Kontrol ediliyor"}
            </Badge>
            <span className="text-[10.5px] text-[var(--text-faint)]">
              Son kontrol: {lastCheck ? dateTime(lastCheck) : "—"}
            </span>
          </>
        }
        actions={
          <Button variant="primary" icon={<RefreshCw size={14} />} onClick={retryBackend}>
            Bağlantıyı yenile
          </Button>
        }
      />

      {backend === "demo" ? <OfflineNotice /> : null}

      <div className="grid gap-4 xl:grid-cols-[1.05fr_1fr]">
        <SectionCard
          title="Backend"
          description="API taban yolu `/api`; Vite geliştirmede 127.0.0.1:8080'e proxy yapılır."
          icon={Database}
          action={<Badge tone={backendTone}>{backend === "online" ? "çalışıyor" : backend === "demo" ? "erişilemiyor" : "kontrol"}</Badge>}
        >
          {backend === "online" && sessionApiReady === false ? (
            <div className="mb-2">
              <InlineNotice tone="warning" title="Oturum API’si henüz hazır değil">
                Sağlık ucu yanıt veriyor ancak `/api/sessions` yanıt vermiyor. Hesaplamalar
                sunucudan, oturum işlemleri tarayıcı üzerinden yürütülür.
              </InlineNotice>
            </div>
          ) : null}
          {health ? (
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Durum</p>
                <p className="mt-0.5 font-mono text-[11px]">{health.status}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Sürüm</p>
                <p className="mt-0.5 font-mono text-[11px]">{health.version}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Veritabanı</p>
                <p className="mt-0.5 font-mono text-[11px]">
                  {health.db.ok ? "ok" : "bilinmiyor"} · {health.db.dialect} · {health.db.migration}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">OCR kuyruğu</p>
                <p className="mt-0.5 font-mono text-[11px]">
                  {health.ocr.queue.queued} bekleyen · {health.ocr.queue.running} çalışan
                </p>
              </div>
              <div className="col-span-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Çalışma süresi</p>
                <p className="mt-0.5 font-mono text-[11px]">
                  {health.uptime_s > 0
                    ? `${Math.floor(health.uptime_s / 3600)} sa ${Math.floor((health.uptime_s % 3600) / 60)} dk`
                    : "bilinmiyor"}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <InlineNotice tone="warning" title="Sunucu yanıtı yok">
                Sağlık ucu yanıt vermedi. Bağlantı sağlanana kadar hesaplamalar tarayıcı üzerinde
                yerel olarak yürütülür.
              </InlineNotice>
              <p className="text-[10.5px] leading-relaxed text-[var(--text-faint)]">
                Backend’i başlattıktan sonra “Bağlantıyı yenile” ile durum güncellenir.
              </p>
            </div>
          )}

          <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
              <KeyRound size={11} aria-hidden /> Workspace anahtarı (X-Session-ID)
            </p>
            <div className="mt-1 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text-muted)]">{workspace}</code>
              <Button size="sm" variant="ghost" onClick={copyWorkspace}>
                Kopyala
              </Button>
            </div>
            <p className="mt-1 text-[9.5px] leading-relaxed text-[var(--text-faint)]">
              Oturum kimliği değildir; anonim çalışma alanı anahtarıdır.
            </p>
          </div>
        </SectionCard>

        <SectionCard
          title="Hesaplama varsayılanları"
          description="Yeni oturumlarda kullanılan su backend'i, B kaynağı ve çelik modeli."
          icon={Settings}
        >
          <div className="space-y-3">
            <SelectField
              label="Su özelliği backend'i"
              value={inputs.water_backend || meta?.water_backends[0]?.key || "table_v1"}
              onChange={(value) => patchInputs({ water_backend: value })}
              options={(meta?.water_backends ?? []).map((item) => ({
                value: item.key,
                label: `${item.label}${item.note ? ` · ${item.note}` : ""}`,
              }))}
            />
            <SelectField
              label="Varsayılan B kaynağı"
              value={inputs.modes.pressure_b_source}
              onChange={(value) =>
                patchInputs({
                  modes: { pressure_b_source: value as typeof inputs.modes.pressure_b_source },
                })
              }
              options={(meta?.b_sources ?? []).map((source) => ({
                value: source.key,
                label: `${source.label}${source.default ? " (varsayılan)" : ""}`,
              }))}
            />
            <SelectField
              label="Çelik modeli"
              value={inputs.modes.steel_model}
              onChange={(value) =>
                patchInputs({ modes: { steel_model: value as typeof inputs.modes.steel_model } })
              }
              options={STEEL_MODEL_OPTIONS.map((model) => ({ value: model.value, label: model.label }))}
              help={STEEL_MODEL_OPTIONS.find((model) => model.value === inputs.modes.steel_model)?.note}
            />
            <SelectField
              label="Çelik α preset"
              value={inputs.modes.steel_preset}
              onChange={(value) => {
                const preset = STEEL_PRESETS.find((item) => item.label === value);
                patchInputs({
                  modes: { steel_preset: value },
                  helper: { steel_alpha_micro_per_c: preset?.value ?? inputs.helper.steel_alpha_micro_per_c },
                });
              }}
              options={STEEL_PRESETS.map((preset) => ({ value: preset.label, label: preset.label }))}
            />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Su backend'i</p>
                <p className="mt-0.5 truncate font-mono text-[10.5px]">
                  {inputs.water_backend || meta?.water_backends[0]?.key || "table_v1"}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Çelik α</p>
                <p className="mt-0.5 font-mono text-[10.5px]">{fmt.a(inputs.helper.steel_alpha_micro_per_c)}</p>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Görünüm" description="Tema ve sayı biçimi." icon={Palette}>
          <div className="space-y-3">
            <div>
              <span className="field-label">Tema</span>
              <div className="mt-1.5 seg-control" role="group" aria-label="Tema">
                <button type="button" className="seg-btn" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>
                  Koyu
                </button>
                <button type="button" className="seg-btn" aria-pressed={theme === "light"} onClick={() => setTheme("light")}>
                  Açık
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <span className="text-[11px] text-[var(--text-muted)]">Sayı biçimi</span>
              <span className="font-mono text-[10.5px]">tr-TR · 1.234,56</span>
            </div>
            <div className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <span className="text-[11px] text-[var(--text-muted)]">Sağ canlı özet paneli</span>
              <Button size="sm" variant="ghost" icon={<Eye size={12} />} onClick={toggleRightPanel}>
                {rightPanelOpen ? "Açık" : "Kapalı"}
              </Button>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
              <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Birimler</p>
              <p className="mt-0.5 font-mono text-[10.5px] text-[var(--text-muted)]">
                bar · °C · m · mm · m³ · m/s · km/sa · 10⁻⁶/bar · 10⁻⁶/°C · MPa
              </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="OCR motoru"
          description="Salt okunur; kurulum yönetici tarafında yapılır."
          icon={ScanLine}
          action={<Badge tone={ocr?.available ? "pass" : "fail"}>{ocr?.available ? "hazır" : "kapalı"}</Badge>}
        >
          <div className="space-y-2 text-[11px] text-[var(--text-muted)]">
            <p>{ocr?.status_text ?? "OCR durumu alınamadı."}</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Motor</p>
                <p className="mt-0.5 font-mono text-[10.5px]">{ocr?.engine ? `${ocr.engine.name} ${ocr.engine.version}` : "—"}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Dil</p>
                <p className="mt-0.5 font-mono text-[10.5px]">{ocr?.engine?.default_language ?? "—"}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Düşük güven</p>
                <p className="mt-0.5 font-mono text-[10.5px]">{num(ocr?.thresholds.low_confidence, 2)}</p>
              </div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-2">
                <p className="text-[9.5px] uppercase tracking-wide text-[var(--text-faint)]">Kritik güven</p>
                <p className="mt-0.5 font-mono text-[10.5px]">{num(ocr?.thresholds.critical_confidence, 2)}</p>
              </div>
            </div>
            <p className="text-[10px] leading-relaxed text-[var(--text-faint)]">
              {ocr?.pdf_rasterizer.available
                ? "Taranmış PDF desteği açık."
                : ocr?.pdf_rasterizer.note ?? "Taranmış PDF desteği kapalı olabilir."}
            </p>
            <Button size="sm" variant="ghost" onClick={() => setTab("ocr")}>
              OCR sekmesine git
            </Button>
          </div>
        </SectionCard>

        <SectionCard title="Oturum" description="Aktif oturum ve yerel veriler." icon={ShieldCheck}>
          <dl className="space-y-1.5 text-[11px]">
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">Ad</dt>
              <dd className="truncate text-right">{sessionName}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">Kimlik</dt>
              <dd className="truncate font-mono text-[10px]">{sessionId ?? "yerel-oturum"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">Durum</dt>
              <dd>{sessionStatus}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">Revizyon</dt>
              <dd className="font-mono">{revision}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">Değişiklik</dt>
              <dd className={dirty ? "tone-warning" : "tone-pass"}>{dirty ? "kaydedilmedi" : "kaydedildi"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">İşlem geçmişi</dt>
              <dd className="font-mono">{sessionCount} kayıt</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-faint)]">A katsayısı</dt>
              <dd>{formatCoefficientState(inputs.air.a_micro_per_bar ? "computed" : "empty")}</dd>
            </div>
          </dl>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Button size="sm" variant="ghost" onClick={() => setConfirmReset(true)}>
              Oturumu sıfırla
            </Button>
            <Button size="sm" variant="danger" icon={<Trash2 size={12} />} onClick={() => setConfirmClear(true)}>
              Yerel verileri sil
            </Button>
          </div>
          <p className="mt-2 text-[9.5px] leading-relaxed text-[var(--text-faint)]">
            Otomatik kayıt varsayılan olarak kapalıdır; üst bardaki “Kaydet” kullanılır. Yerel
            veriler yalnızca bu tarayıcıda saklanır.
          </p>
        </SectionCard>
      </div>

      <SectionCard
        title="Güncelleme Yöneticisi (HydroWeb)"
        description="GitHub Releases üzerinden yeni HydroWeb sürümlerini denetleyin, SHA-256 ve Ed25519 dijital imzasıyla doğrulayıp kurun."
        icon={ArrowUpCircle}
        action={
          <Badge tone={updateStatus?.update_available ? "pass" : "info"}>
            {updateStatus?.update_available && updateStatus.latest_version
              ? `Yeni sürüm v${updateStatus.latest_version}`
              : `v${updateStatus?.current_version ?? meta?.app.version ?? "2.0.0"}`}
          </Badge>
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1 text-xs text-[var(--text-soft)]">
            <p>
              Yüklü sürüm: <strong className="font-mono text-[var(--text)]">v{updateStatus?.current_version ?? meta?.app.version ?? "2.0.0"}</strong>
              {updateStatus?.latest_version ? (
                <>
                  {" · "}Son sürüm: <strong className="font-mono text-[var(--text)]">v{updateStatus.latest_version}</strong>
                </>
              ) : null}
            </p>
            <p className="text-[11px] text-[var(--text-muted)]">
              {updateStatus?.runtime.can_self_install
                ? "Paketli masaüstü uygulaması aktif: tek tıkla yerinde kurulum (.dmg / .exe) ve yeniden başlatma desteklenir."
                : "Web sunucu / geliştirme modu: SHA-256 ve Ed25519 imza doğrulaması sunucuda yapılıp paket indirilebilir."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              icon={<RefreshCw size={13} />}
              loading={checkUpdates.isPending}
              disabled={backend !== "online"}
              onClick={() => checkUpdates.mutate({ force: true })}
            >
              Denetle
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={<ArrowUpCircle size={13} />}
              onClick={() => setUpdateModalOpen(true)}
            >
              Güncelleme Yöneticisini Aç
            </Button>
          </div>
        </div>
      </SectionCard>

      <DatabaseAdminPanel />

      <SectionCard title="Hakkında" description="Sürüm, şartname ve özellikler." icon={Info}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="eyebrow">Uygulama</p>
            <p className="mt-1 text-[13px] font-semibold">{meta?.app.name}</p>
            <p className="text-[10.5px] text-[var(--text-faint)]">Sürüm {meta?.app.version}</p>
          </div>
          <div>
            <p className="eyebrow">Şartname</p>
            <p className="mt-1 text-[11px] font-semibold">{meta?.spec.code}</p>
            <p className="text-[10.5px] leading-snug text-[var(--text-faint)]">{meta?.spec.title}</p>
          </div>
          <div>
            <p className="eyebrow">Özellikler</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Badge tone={meta?.features.scene ? "pass" : "pending"}>3D sahne</Badge>
              <Badge tone={meta?.features.ocr ? "pass" : "pending"}>OCR</Badge>
              <Badge tone={meta?.features.auth === "none" ? "info" : "pass"}>auth: {meta?.features.auth}</Badge>
            </div>
          </div>
          <div>
            <p className="eyebrow">Sınırlar</p>
            <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--text-faint)]">
              20.000 m · 12.500 m³ · %0,2 basınçlandırma · 24 sa termal denge
            </p>
          </div>
        </div>
        <InlineNotice tone="info" title="Yetki notu" icon={Monitor}>
          Yerel kurulumda kimlik doğrulama kapalıdır; çalışma alanı anonim anahtarla ayrılır. Resmi
          kabul için yetkili personel onayı ve ASME B31.8 değerlendirmesi gerekir.
        </InlineNotice>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            icon={<Database size={12} />}
            onClick={() => setTab("reports")}
          >
            Raporlar
          </Button>
          <span className="text-[9.5px] text-[var(--text-faint)]">
            UI sürümü 0.1.0 · React 19 + TypeScript + Tailwind 4
          </span>
        </div>
      </SectionCard>

      <div
        className={cn(
          "rounded-xl border px-3.5 py-2.5 text-[10.5px] leading-relaxed",
          theme === "light"
            ? "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)]"
            : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)]",
        )}
      >
        Sunucu bağlantısı olmadığında hesaplamalar tarayıcıda yerel olarak yürütülür; resmi kabul
        için sunucu kaydı ve yetkili personel onayı gerekir.
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="Oturum sıfırlansın mı?"
        message="Girdiler varsayılan değerlere döner, sonuçlar yeniden üretilir ve kaydedilmemiş değişiklikler kaybolur. Sunucudaki oturum silinmez."
        confirmLabel="Sıfırla"
        onConfirm={() => {
          resetSession();
          pushToast("info", "Oturum sıfırlandı", "Varsayılan girdilerle yeni taslak hazır.");
        }}
        onClose={() => setConfirmReset(false)}
      />
      <ConfirmDialog
        open={confirmClear}
        title="Yerel veriler silinsin mi?"
        message="Bu tarayıcıda saklanan oturum girdileri, sonuçlar, tema ve dışa aktarma geçmişi silinir. Workspace anahtarı korunur."
        confirmLabel="Sil"
        danger
        onConfirm={() => {
          clearLocalData();
          pushToast("success", "Yerel veriler silindi", "Uygulama temiz bir taslakla açıldı.");
        }}
        onClose={() => setConfirmClear(false)}
      />
    </div>
  );
}
