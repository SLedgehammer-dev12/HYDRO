import { CalendarDays, FolderOpen, MapPin, Tag } from "lucide-react";
import { SectionCard } from "./ui/Card";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { FieldGrid, TextField } from "./ui/Field";
import { useAppStore } from "../store/useAppStore";

/**
 * Kesit kimlik kartı: proje bağlantısı ve kesit meta bilgisi.
 * Aynı bilgi oturum `inputs.section_meta` alanında saklanır.
 */
export function SectionIdentityCard() {
  const inputs = useAppStore((state) => state.inputs);
  const patchInputs = useAppStore((state) => state.patchInputs);
  const setTab = useAppStore((state) => state.setTab);
  const projectName = useAppStore((state) => state.projectName);
  const projectCode = useAppStore((state) => state.projectCode);
  const projectId = useAppStore((state) => state.projectId);

  const meta = inputs.section_meta;

  return (
    <SectionCard
      title="Kesit kimliği"
      description="Proje, kesit numarası ve test künyesi. Kaydedince oturumun girdileriyle birlikte saklanır."
      icon={Tag}
      action={
        <Button size="sm" variant="ghost" icon={<FolderOpen size={12} />} onClick={() => setTab("projects")}>
          Projeler & Kesitler
        </Button>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={projectId ? "info" : "warning"}>
          {projectId ? projectCode || projectName || "Proje bağlı" : "Proje seçilmedi"}
        </Badge>
        {projectName ? <span className="text-[11px] text-[var(--text-muted)]">{projectName}</span> : null}
        <span className="chip">
          <MapPin size={10} /> {meta.location || "konum girilmedi"}
        </span>
        <span className="chip">
          <CalendarDays size={10} /> {meta.test_date || "tarih girilmedi"}
        </span>
      </div>

      <FieldGrid cols={3}>
        <TextField
          label="Kesit no"
          value={meta.section_no}
          onChange={(value) => patchInputs({ section_meta: { section_no: value } })}
          placeholder="K-01"
          maxLength={40}
        />
        <TextField
          label="Kesit açıklaması"
          value={meta.description}
          onChange={(value) => patchInputs({ section_meta: { description: value } })}
          placeholder="Bölüm 12–13 · Doğu Hattı"
          maxLength={200}
        />
        <TextField
          label="Konum / KP"
          value={meta.location}
          onChange={(value) => patchInputs({ section_meta: { location: value } })}
          placeholder="KP 0+000 – 12+000"
          maxLength={120}
        />
        <TextField
          label="Test tarihi"
          type="date"
          value={meta.test_date}
          onChange={(value) => patchInputs({ section_meta: { test_date: value } })}
        />
        <TextField
          label="Test türü"
          value={meta.test_type}
          onChange={(value) => patchInputs({ section_meta: { test_type: value } })}
          placeholder="Hidrostatik test"
          maxLength={80}
        />
        <TextField
          label="Not"
          value={meta.notes}
          onChange={(value) => patchInputs({ section_meta: { notes: value } })}
          placeholder="Kısa saha notu"
          maxLength={240}
        />
      </FieldGrid>
    </SectionCard>
  );
}
