import { ArrowRight, Compass, FolderPlus, Sparkles, X } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { Button } from "../ui/Button";
import { useStartDemoTour } from "./useStartDemoTour";

export function OnboardingWelcomeCard() {
  const setTab = useAppStore((state) => state.setTab);
  const setOnboardingDismissed = useAppStore((state) => state.setOnboardingDismissed);
  const pushToast = useAppStore((state) => state.pushToast);

  const { startDemoTour, loadingDemo } = useStartDemoTour();

  function handleOwnProject() {
    setOnboardingDismissed(true);
    setTab("projects");
  }

  function handleDismiss() {
    setOnboardingDismissed(true);
    pushToast(
      "info",
      "Başlangıç rehberi gizlendi",
      "İstediğiniz zaman üst çubuktaki ? Yardım penceresinden rehberli turu tekrar açabilirsiniz.",
    );
  }

  return (
    <section
      aria-labelledby="onboarding-welcome-title"
      className="panel hero-wash border-[color-mix(in_srgb,var(--primary)_32%,var(--border))] p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="eyebrow flex items-center gap-1.5">
            <Sparkles size={12} aria-hidden /> İlk Kullanım Rehberi
          </p>
          <h2 id="onboarding-welcome-title" className="text-base font-bold text-[var(--text)]">
            HYDRO&apos;ya hoş geldiniz — nasıl başlamak istersiniz?
          </h2>
          <p className="max-w-[78ch] text-xs leading-relaxed text-[var(--text-muted)]">
            Onayınızla örnek bir boru hattı projesi oluşturup 5 adımda (~1 dakika) tüm ekranları birlikte
            gezebilir veya doğrudan kendi projenizle çalışmaya başlayabilirsiniz.
          </p>
        </div>

        <button
          type="button"
          onClick={handleDismiss}
          className="rounded-lg p-1.5 text-[var(--text-faint)] hover:bg-[var(--surface-3)] hover:text-[var(--text)]"
          aria-label="Karşılama rehberini gizle"
          title="Şimdi değil"
        >
          <X size={15} aria-hidden />
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          icon={<Compass size={14} />}
          loading={loadingDemo}
          onClick={() => void startDemoTour()}
        >
          Rehberli Demo Turunu Başlat
        </Button>
        <Button
          size="sm"
          variant="default"
          icon={<FolderPlus size={14} />}
          onClick={handleOwnProject}
        >
          Kendi Projemle Başla
          <ArrowRight size={12} aria-hidden />
        </Button>
        <Button size="sm" variant="ghost" onClick={handleDismiss}>
          Şimdi değil
        </Button>
      </div>
    </section>
  );
}
