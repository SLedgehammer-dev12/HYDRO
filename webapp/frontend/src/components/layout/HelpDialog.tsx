import { useMeta, useSpec } from "../../hooks/queries";
import { Modal } from "../ui/Dialog";
import { Badge } from "../ui/Badge";

const SHORTCUTS: Array<[string, string]> = [
  ["Alt + 1…9", "Sekme değiştir"],
  ["Ctrl/Cmd + S", "Oturumu kaydet"],
  ["Ctrl/Cmd + Enter", "Aktif testi / profili değerlendir"],
  ["Shift + ?", "Bu yardım penceresi"],
  ["Tab / Shift + Tab", "Alanlar arası gezin"],
  ["Esc", "Diyaloğu kapat"],
];

const STATUSES: Array<{ label: string; tone: "pending" | "warning" | "pass" | "fail" | "info"; meaning: string }> = [
  { label: "BEKLIYOR", tone: "pending", meaning: "Girdi veya hesap bekliyor" },
  { label: "KATSAYI GUNCELLENMELI", tone: "warning", meaning: "Girdi değişti, katsayı bayat" },
  { label: "DOGRULANAMADI", tone: "warning", meaning: "Koşullar sağlanamadı / bilgi yetersiz" },
  { label: "BASARILI", tone: "pass", meaning: "Kabul kuralı sağlandı" },
  { label: "BASARISIZ", tone: "fail", meaning: "Kabul kuralı sağlanmadı" },
];

export function HelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: meta } = useMeta();
  const { data: spec } = useSpec();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Yardım ve kısayollar"
      description="Denetimli akış: doğru sıra, doğru birim, doğru işaret."
    >
      <div className="space-y-4">
        <section>
          <h3 className="eyebrow">Klavye</h3>
          <div className="mt-2 overflow-hidden rounded-lg border border-[var(--border)]">
            {SHORTCUTS.map(([keys, action], index) => (
              <div
                key={keys}
                className="flex items-center justify-between gap-3 px-3 py-2 text-[12px]"
                style={{
                  borderTop: index === 0 ? undefined : "1px solid var(--border)",
                  background: index % 2 === 1 ? "var(--surface-2)" : "transparent",
                }}
              >
                <span className="flex flex-wrap gap-1">
                  {keys.split(" + ").map((key) => (
                    <kbd key={key} className="kbd">
                      {key}
                    </kbd>
                  ))}
                </span>
                <span className="text-right text-[var(--text-muted)]">{action}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="eyebrow">Karar renkleri</h3>
          <div className="mt-2 space-y-1.5">
            {STATUSES.map((status) => (
              <div key={status.label} className="flex items-center justify-between gap-2">
                <Badge tone={status.tone}>{status.label}</Badge>
                <span className="text-[11px] text-[var(--text-muted)]">{status.meaning}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="eyebrow">İşaret sözleşmesi</h3>
          <div className="mt-2 space-y-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-[11.5px] leading-relaxed text-[var(--text-muted)]">
            <p className="font-mono text-[var(--text-soft)]">
              {spec?.sign_convention.delta_t ?? "ΔT = Tilk - Tson"}
            </p>
            <p className="font-mono text-[var(--text-soft)]">{spec?.sign_convention.pa ?? "Pa = Pilk - Pson"}</p>
            <p>
              Kabul kuralları:{" "}
              <span className="font-mono">{spec?.acceptance_rules.air.text ?? "Vpa < 1.06 x Vp"}</span> ·{" "}
              <span className="font-mono">{spec?.acceptance_rules.pressure.text ?? "(Pa - Pt) <= 0.3 bar"}</span>
            </p>
            <p>Hidrolik kot hesabında 15 °C su yoğunluğu (999,1 kg/m³) kullanılır.</p>
          </div>
        </section>

        <section>
          <h3 className="eyebrow">Şartname</h3>
          <p className="mt-1 text-[12px] font-medium">{meta?.spec.code}</p>
          <p className="text-[11px] text-[var(--text-faint)]">{meta?.spec.title}</p>
          <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--text-faint)]">
            Nihai karar ASME B31.8 ve proje prosedürü ile birlikte değerlendirilmelidir. OCR çıktısı
            resmi kabul değildir; yetkili personel onayı zorunludur.
          </p>
        </section>

        <section>
          <h3 className="eyebrow">Bağlantı</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
            Sunucu bağlı değilse hesaplamalar tarayıcı üzerinde yerel olarak yürütülür. Bağlantı
            durumu üst çubuktadır; Ayarlar sayfasından yenilenebilir.
          </p>
        </section>
      </div>
    </Modal>
  );
}
