# HYDRO Web Arayüzü & Program İkonu Uygulama Planı

> Kaynak: Kullanıcı onayı sonrası **Faz 1–5** görev listesi (`tasks/todo.md` masaüstü domain listesi korunur).

- [x] **Faz 1 — Konuya Uygun Program İkonu & Marka Sistemi**
  - [x] `tools/generate_icons.py` ile Boru Kesiti + Hidrostatik Su + Manometre ikon setinin (`SVG`, `PNG`, `.ico`, `.icns`, PWA manifest) üretilmesi
  - [x] `<HydroLogo />` bileşeninin oluşturulması ve `Sidebar`, mobil `TopBar`, `UpdateManagerModal` içine yerleştirilmesi
  - [x] `webapp/frontend/index.html` içine favicon, `apple-touch-icon`, `site.webmanifest`, `color-scheme` meta ve erken tema yükleyici eklenmesi
  - [x] `HydroWeb.spec`, `HidrostatikTest.spec`, `installer/hydro_web.iss`, `webapp/desktop_launcher.py` ve `hidrostatik_test/ui/app.py` ikon bağlantıları
- [x] **Faz 2 — Modern Web Altyapısı & Erişilebilirlik**
  - [x] `Dialog.tsx`: yerel `<dialog>` + `.showModal()` + `closedby="any"` (Safari pointer-coordinate fallback) + `overscroll-behavior: contain`
  - [x] `styles.css`: `:root` / `[data-theme]` `color-scheme` + `accent-color` iyileştirmesi
  - [x] `Sidebar.tsx`: mobil gezinme çekmecesinin yerel `<dialog>` top-layer yapısına geçirilmesi
- [x] **Faz 3 — Sol Menü Form Ağacı, `DecisionStrip` & `RightPanel` Operatör Akışı**
  - [x] `Sidebar.tsx`: `w-[280px]` genişlik ve `Tümü | Bulgulu | Eksik` hızlı filtre çipleri
  - [x] `DecisionStrip.tsx` & `RightPanel.tsx`: `Formlar · Dolu/11` durumu, aktif form bağlamı ve ilk bulgulu forma tek tıkla geçiş
- [x] **Faz 4 — BOTAŞ Form Sayfaları Ergonomisi**
  - [x] `styles.css` & `FormBodyEditor`: `@container` yapışkan `<thead>` ve yapışkan `Saat` ilk sütunu (`role="region"`, `tabIndex={0}`)
  - [x] Excel / TSV çoklu satır yapıştırma (`pasteUtils.ts`, `FormTablePrimitives.tsx`, `MonitoringFormEditor.tsx`)
  - [x] `020`/`022` & `PressurePage.tsx` alan seviyesi işaret/sınır mikro-rehberleri (`AcceptanceFormEditor.tsx`)
  - [x] `SectionFormPage.tsx`: kaydedilmemiş değişiklik koruma diyaloğu ve iskelet yükleyici
- [x] **Faz 5 — `DashboardPage`, `ProjectsPage` Modülerleştirme & Tam Doğrulama**
  - [x] `DashboardPage.tsx`: 3 adımlı denetimli iş akışı çubuğu ve form hazırlık satırı
  - [x] `ProjectsPage.tsx`: `SectionFormsModal.tsx` & `PlanProfileScanModal.tsx` alt bileşen ayrımı
  - [x] `npm run typecheck && npm run build`, `ruff`, `mypy`, `pytest`, `unittest`, `--self-test`, `verify-tabs.mjs` ve canlı tarayıcı doğrulaması + `DURUM.md` güncellemesi
