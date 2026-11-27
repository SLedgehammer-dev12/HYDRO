import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Command, FileText, FolderOpen, LayoutGrid, Moon, Plus, Search, Sun, Zap } from "lucide-react";
import { BOTAS_FORM_NAV_ITEMS, VISIBLE_TABS } from "../../lib/constants";
import type { BotasFormCode, TabKey } from "../../lib/types";
import { api, apiErrorMessage } from "../../lib/api";
import { useProjects, useSessions } from "../../hooks/queries";
import { useAppStore } from "../../store/useAppStore";
import { cn } from "../../lib/utils";

interface PaletteItem {
  id: string;
  group: "Sekmeler" | "BOTAŞ Formları" | "Test Bölümleri" | "Hızlı Eylemler";
  title: string;
  subtitle: string;
  keywords: string;
  run: () => void | Promise<void>;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onOpenHelp: () => void;
}

export function CommandPalette({ open, onClose, onOpenHelp }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const setTab = useAppStore((s) => s.setTab);
  const openForm = useAppStore((s) => s.openForm);
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const backend = useAppStore((s) => s.backend);
  const setSessionMeta = useAppStore((s) => s.setSessionMeta);
  const applySessionInputs = useAppStore((s) => s.applySessionInputs);
  const markSaved = useAppStore((s) => s.markSaved);
  const setProject = useAppStore((s) => s.setProject);
  const pushToast = useAppStore((s) => s.pushToast);

  const { data: sessions } = useSessions();
  const { data: projects } = useProjects();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      previousFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setQuery("");
      setActiveIndex(0);
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }

    if (typeof dialog.close === "function") {
      if (dialog.open) dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => {
      dialog.returnValue = "";
      onCloseRef.current();
      const prev = previousFocusRef.current;
      previousFocusRef.current = null;
      if (prev && prev.isConnected) {
        window.setTimeout(() => prev.focus(), 0);
      }
    };
    dialog.addEventListener("close", handleClose);

    let cleanupFallback: (() => void) | undefined;
    if (typeof HTMLDialogElement !== "undefined" && !("closedBy" in HTMLDialogElement.prototype)) {
      let pressedOutside = false;
      const outside = (e: PointerEvent) => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      const onPointerDown = (e: PointerEvent) => {
        pressedOutside = e.target === dialog && outside(e);
      };
      const onPointerUp = (e: PointerEvent) => {
        if (pressedOutside && e.target === dialog && outside(e) && dialog.open) {
          dialog.close();
        }
        pressedOutside = false;
      };
      dialog.addEventListener("pointerdown", onPointerDown);
      dialog.addEventListener("pointerup", onPointerUp);
      cleanupFallback = () => {
        dialog.removeEventListener("pointerdown", onPointerDown);
        dialog.removeEventListener("pointerup", onPointerUp);
      };
    }

    return () => {
      dialog.removeEventListener("close", handleClose);
      cleanupFallback?.();
    };
  }, [open]);

  const items = useMemo<PaletteItem[]>(() => {
    const tabItems: PaletteItem[] = VISIBLE_TABS.map((t) => ({
      id: `tab:${t.key}`,
      group: "Sekmeler",
      title: t.label,
      subtitle: t.description,
      keywords: `${t.key} ${t.label} ${t.description}`.toLocaleLowerCase("tr-TR"),
      run: () => setTab(t.key as TabKey),
    }));

    const formItems: PaletteItem[] = BOTAS_FORM_NAV_ITEMS.map((f) => ({
      id: `form:${f.code}`,
      group: "BOTAŞ Formları",
      title: `${f.shortCode} · ${f.title}`,
      subtitle: f.botasCode,
      keywords: `${f.code} ${f.shortCode} ${f.botasCode} ${f.title}`.toLocaleLowerCase("tr-TR"),
      run: () => openForm(f.code as BotasFormCode),
    }));

    const sessionItems: PaletteItem[] = (sessions ?? []).slice(0, 12).map((sess) => ({
      id: `sess:${sess.id}`,
      group: "Test Bölümleri",
      title: sess.name,
      subtitle: `rev. ${sess.revision} · ${sess.status}`,
      keywords: `${sess.name} ${sess.status}`.toLocaleLowerCase("tr-TR"),
      run: async () => {
        if (backend !== "online" || sess.id.startsWith("demo-")) {
          setSessionMeta({ id: sess.id, name: sess.name, revision: sess.revision, status: sess.status });
          return;
        }
        try {
          const loaded = await api.session(sess.id);
          applySessionInputs(loaded.inputs);
          setSessionMeta({
            id: loaded.id,
            name: loaded.name,
            revision: loaded.revision,
            status: loaded.status,
          });
          markSaved(loaded.revision);
          const proj = projects?.find((p) => p.id === loaded.project_id);
          if (proj) setProject(proj);
          pushToast("success", "Test Bölümü açıldı", loaded.name);
        } catch (err) {
          pushToast("error", "Test Bölümü açılamadı", apiErrorMessage(err));
        }
      },
    }));

    const actions: PaletteItem[] = [
      {
        id: "act:ocr",
        group: "Hızlı Eylemler",
        title: "OCR Rapor Yükle & Analiz Et",
        subtitle: "PDF / görsel / Excel rapordan alan çıkar",
        keywords: "ocr tarama pdf yukle analiz".toLocaleLowerCase("tr-TR"),
        run: () => setTab("ocr"),
      },
      {
        id: "act:theme",
        group: "Hızlı Eylemler",
        title: theme === "dark" ? "Açık Temaya Geç" : "Koyu Temaya Geç",
        subtitle: "Arayüz renk temasını değiştir",
        keywords: "tema dark light koyu acik gorunum".toLocaleLowerCase("tr-TR"),
        run: () => setTheme(theme === "dark" ? "light" : "dark"),
      },
      {
        id: "act:projects",
        group: "Hızlı Eylemler",
        title: "Projeler ve Yeni Kesit Yönetimi",
        subtitle: "Proje veya yeni Test Bölümü oluştur",
        keywords: "proje yeni kesit bolum olustur".toLocaleLowerCase("tr-TR"),
        run: () => setTab("projects"),
      },
      {
        id: "act:help",
        group: "Hızlı Eylemler",
        title: "Klavye Kısayolları ve Yardım",
        subtitle: "Kısayol listesini aç (?)",
        keywords: "yardim kisayol help soru".toLocaleLowerCase("tr-TR"),
        run: () => onOpenHelp(),
      },
    ];

    return [...tabItems, ...actions, ...formItems, ...sessionItems];
  }, [
    sessions,
    projects,
    backend,
    theme,
    setTab,
    openForm,
    setTheme,
    setSessionMeta,
    applySessionInputs,
    markSaved,
    setProject,
    pushToast,
    onOpenHelp,
  ]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr-TR");
    if (!q) return items.slice(0, 14);
    return items.filter((item) => item.keywords.includes(q)).slice(0, 20);
  }, [items, query]);

  if (!open || typeof document === "undefined") return null;

  const safeIndex = filtered.length > 0 ? Math.min(activeIndex, filtered.length - 1) : 0;

  const execute = (item: PaletteItem | undefined) => {
    if (!item) return;
    onClose();
    void item.run();
  };

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-label="Hızlı geçiş ve komut paleti"
      {...({ closedby: "any" } as Record<string, unknown>)}
      className="modal-dialog modal-palette overflow-hidden"
    >
      <div className="w-full overflow-hidden bg-[var(--surface)]">
        <div className="flex items-center gap-2.5 border-b border-[var(--border)] px-4 py-3">
          <Search size={16} className="shrink-0 text-[var(--primary)]" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                if (typeof dialogRef.current?.close === "function" && dialogRef.current.open) {
                  dialogRef.current.close();
                } else {
                  onClose();
                  previousFocusRef.current?.focus();
                  previousFocusRef.current = null;
                }
              } else if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((i) => (filtered.length ? (i + 1) % filtered.length : 0));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((i) =>
                  filtered.length ? (i - 1 + filtered.length) % filtered.length : 0,
                );
              } else if (event.key === "Enter") {
                event.preventDefault();
                execute(filtered[safeIndex]);
              }
            }}
            placeholder="Sekme, BOTAŞ formu, test bölümü veya eylem ara..."
            aria-label="Komut ve sayfa arama"
            className="w-full bg-transparent text-sm text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              if (typeof dialogRef.current?.close === "function" && dialogRef.current.open) {
                dialogRef.current.close();
              } else {
                onClose();
                previousFocusRef.current?.focus();
                previousFocusRef.current = null;
              }
            }}
            aria-label="Komut paletini kapat"
            className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-faint)] hover:border-[var(--border-strong)]"
          >
            ESC
          </button>
        </div>

        <div className="max-h-[56vh] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-[var(--text-faint)]">
              Aramanızla eşleşen sayfa, form veya eylem bulunamadı.
            </p>
          ) : (
            <ul role="listbox" aria-label="Komut sonuçları" className="space-y-0.5">
              {filtered.map((item, idx) => {
                const active = idx === safeIndex;
                const Icon =
                  item.group === "Sekmeler"
                    ? LayoutGrid
                    : item.group === "BOTAŞ Formları"
                      ? FileText
                      : item.group === "Test Bölümleri"
                        ? FolderOpen
                        : item.id === "act:theme"
                          ? theme === "dark"
                            ? Sun
                            : Moon
                          : item.id === "act:projects"
                            ? Plus
                            : Zap;
                return (
                  <li key={item.id} role="option" aria-selected={active}>
                    <button
                      type="button"
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => execute(item)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors",
                        active
                          ? "bg-[var(--primary-soft)] text-[var(--primary)]"
                          : "text-[var(--text)] hover:bg-[var(--surface-2)]",
                      )}
                    >
                      <Icon size={15} className="shrink-0 opacity-80" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-semibold">{item.title}</p>
                        <p className="truncate text-[11px] text-[var(--text-muted)]">{item.subtitle}</p>
                      </div>
                      <span className="shrink-0 rounded border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 text-[11px] text-[var(--text-faint)]">
                        {item.group}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="flex items-center justify-between border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-[11px] text-[var(--text-faint)]">
          <span className="inline-flex items-center gap-1">
            <Command size={11} aria-hidden="true" />↑↓ gezin · Enter aç · Esc kapat
          </span>
          <span>Ctrl/⌘ + K</span>
        </footer>
      </div>
    </dialog>,
    document.body,
  );
}
