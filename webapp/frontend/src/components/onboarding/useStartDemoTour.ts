import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { hydrateSessionResults } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";

export function useStartDemoTour() {
  const backend = useAppStore((state) => state.backend);
  const setProject = useAppStore((state) => state.setProject);
  const applySessionInputs = useAppStore((state) => state.applySessionInputs);
  const setSessionMeta = useAppStore((state) => state.setSessionMeta);
  const markSaved = useAppStore((state) => state.markSaved);
  const startTour = useAppStore((state) => state.startTour);
  const pushToast = useAppStore((state) => state.pushToast);

  const queryClient = useQueryClient();
  const [loadingDemo, setLoadingDemo] = useState(false);

  async function startDemoTour() {
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
    let createdProjectId: string | null = null;
    try {
      const generated = await api.generateSampleProject({
        scenario: "mixed",
        section_count: 2,
        name: "Demo Boru Hattı (Rehber)",
        code: "DEMO-TUR",
        include_time_series: true,
        include_forms: true,
      });
      createdProjectId = generated.reused ? null : generated.project.id;
      const firstSection = generated.sections[0];
      if (firstSection) {
        const session = await api.session(firstSection.id);
        setProject({
          id: generated.project.id,
          name: generated.project.name,
          code: generated.project.code,
        });
        applySessionInputs(session.inputs);
        setSessionMeta({
          id: session.id,
          name: session.name,
          status: session.status,
          revision: session.revision,
        });
        markSaved(session.revision);
        void hydrateSessionResults(session.id);
      } else {
        setProject({
          id: generated.project.id,
          name: generated.project.name,
          code: generated.project.code,
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      startTour(generated.project.id);
    } catch {
      if (createdProjectId) {
        await api.deleteProject(createdProjectId).catch(() => undefined);
      }
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

  return { startDemoTour, loadingDemo };
}
