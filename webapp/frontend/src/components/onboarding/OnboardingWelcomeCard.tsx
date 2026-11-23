import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Compass, FolderPlus, Sparkles, X } from "lucide-react";
import { api } from "../../lib/api";
import { hydrateSessionResults } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { Button } from "../ui/Button";

export function OnboardingWelcomeCard() {
  const backend = useAppStore((state) => state.backend);
  const setTab = useAppStore((state) => state.setTab);
  const setProject = useAppStore((state) => state.setProject);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const markSaved = useAppStore((state) => state.markSaved);
  const setOnboardingDismissed = useAppStore((state) => state.setOnboardingDismissed);
  const startTour = useAppStore((state) => state.startTour);
  const pushToast = useAppStore((state) => state.pushToast);

  const queryClient = useQueryClient();
  const [loadingDemo, setLoadingDemo] = useState(false);

  async function handleStartDemoTour() {
    if (backend !== "online") {
      pushToast(
        "info",
        "Yerel demo ile rehberli tur başlatıldı",
        "Sunucu bağlı olmadığı için yerleşik demo verileriyle 5 adımlı tur açılıyor.",
      );
      startTour(null);
      return;
    }

    setLoadingDemo(true);
    try {
      const generated = await api.generateSampleProject({
        scenario: "mixed",
        section_count: 2,
        name: "Demo Boru Hattı (Rehber)",
        code: "DEMO-TUR",
        include_time_series: true,
        include_forms: true,
      });
      const firstSection = generated.sections[0];
      setProject({
        id: generated.project.id,
        name: generated.project.name,
        code: generated.project.code,
      });
      if (firstSection) {
        const session = await api.session(firstSection.id);
        applySessionInputs(session.inputs);
        setSessionMeta({
          id: session.id,
          name: session.name,
          status: session.status,
          revision: session.revision,
        });
        markSaved(session.revision);
        void hydrateSessionResults(session.id);
      }
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      startTour(generated.project.id);
    } catch {
      pushToast(
        "warning",
        "Örnek proje oluşturulamadı; yerel demo verileriyle devam ediliyor",
        "İstediğiniz zaman Projeler & Kesitler ekranından yeni örnek proje açabilirsiniz.",
      );
      startTour(null);
    } finally {
      setLoadingDemo(false);
    }
  }

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
          onClick={() => void handleStartDemoTour()}
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
