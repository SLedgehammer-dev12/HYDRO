# HYDRO Web — UX Planı

**İlke:** Uygulama genel amaçlı bir hesap makinesi değil, operatörü doğru sıraya, doğru
birime ve doğru işaret tanımına yönlendiren **denetimli bir akış**tır
(bkz. `docs/ui_ergonomics.md` §Tasarım İlkesi).

**Öncelik:** Masaüstü (≥1280 px) → tablet (768–1279 px). Telefon kapsam dışı; yalnızca
okuma/onay için temel görünüm.

---

## 1. Bilgi mimarisi

Sol dikey navigasyon (≥1280 px) / üst yatay sekme şeridi (tablet). Sıra, operatörün
şartname akışıyla aynıdır:

| # | Sekme | Route | Amaç | Birincil CTA |
|---|---|---|---|---|
| 1 | **Dashboard** | `/` | Durum, karar özeti, sıradaki adım | "Sıradaki adıma git" |
| 2 | **Geometri** | `/geometry` | Boru kesiti, segmentler, kotlar, malzeme | "Geometriyi doğrula" |
| 3 | **Katsayılar** | `/coefficients` | A/B hazırlama, kaynak ve provenance | "A/B hazırla" |
| 4 | **Hava** | `/air` | Hava içerik testi | "Testi değerlendir" |
| 5 | **Basınç** | `/pressure` | Basınç değişim testi | "Testi değerlendir" |
| 6 | **Profil / Saha** | `/field` | Basınç penceresi, checklist, pig, 3D tam saha | "Profili doğrula" |
| 7 | **Raporlar** | `/reports` | Rapor önizleme + PDF/XLSX/TXT | "Raporu indir" |
| 8 | **OCR** | `/ocr` | Rapor yükleme, alan onayı, uyuşmazlık | "Analiz et" |
| 9 | **Ayarlar** | `/settings` | Backend, sahne, saklama, hakkında | — |

Global öğeler:

- **Üst bar:** uygulama adı + sürüm, oturum seçici (`Oturum 3`), kaydetme durumu
  ("Kaydedildi • 2 sn önce"), "Yeni oturum", yardım.
- **Karar şeridi (her zaman görünür):** aktif testin durumu + kabul kuralı + marj.
  Renkleri masaüstüyle aynı: `BEKLIYOR` gri, `KATSAYI GUNCELLENMELI` amber,
  `DOGRULANAMADI` amber, `BASARILI` yeşil, `BASARISIZ` kırmızı.
- **Sağ bağlam paneli (≥1440 px):** canlı özet — geometri, katsayı durumu, uyarılar.
  Gizlenebilir; tercih `localStorage`.
- **Alt aksiyon çubuğu (≤1279 px):** ekranın altında yapışkan "Değerlendir" + eksik
  alan gerekçesi.

Sekmeler arası geçişte form durumu korunur (Zustand + TanStack Query cache). URL
paylaşılabilir: `/pressure?session=7c1e…`.

---

## 2. Genel yerleşim

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ HYDRO 1.7.3 | Oturum 3 ▾ | Kaydedildi 12:04 |  Yeni | ?                    │
├──────────┬─────────────────────────────────────────────────┬───────────────┤
│ Dashboard│  Karar şeridi: BASARILI · Vpa < 1.06 x Vp · +0.0004 m³          │
│ Geometri │─────────────────────────────────────────────────│  Canlı Özet   │
│ Katsayı  │                                                 │  Geometri     │
│ Hava     │  Ana çalışma alanı (kartlar, form, grafik, 3D)  │  A/B durumu   │
│ Basınç   │                                                 │  Uyarılar     │
│ Profil   │                                                 │               │
│ Raporlar │                                                 │               │
│ OCR      │                                                 │               │
│ Ayarlar  │                                                 │               │
├──────────┴─────────────────────────────────────────────────┴───────────────┤
│ Eksik: et kalınlığı, Vpa                         [Taslak] [Değerlendir]     │
└────────────────────────────────────────────────────────────────────────────┘
```

Kart hiyerarşisi: `SectionCard` (başlık + açıklama + aksiyon) → `FieldGrid` (2/3/4
kolon) → `ResultTile` (etiket, büyük değer, birim, delta) → `DecisionCard`.

---

## 3. Sekme bazlı içerik

### 3.1 Dashboard

**Amaç:** Operatör 5 saniyede "ne yapmalıyım?" sorusunun cevabını görür.

| Bölge | İçerik |
|---|---|
| Oturum başlığı | Ad, durum rozeti, son güncelleme, proje |
| Karar kartları (2) | Hava ve Basınç: durum, kural, marj, "Detaya git" |
| Hazırlık kontrolü | Geometri ✓, A ✗, B ✗, dT/Pa ✗ → tıklanabilir satırlar |
| Ana metrikler (4) | Vt (m³), Vp (m³), Pt (bar), Pig hızı (m/s) — yoksa "—" |
| Basınç penceresi | Yatay bant grafiği: min–max, izlenen basınç işareti |
| Trend | Son 24 saat P/T sparkline (kayıt varsa) |
| Son aktivite | Son 5 kayıt: "12:04 Hava testi — BASARILI" |
| Sıradaki adım | Tek CTA: "Katsayıları hazırla" / "Testi değerlendir" / "Raporu üret" |

**Boş durum:** "Henüz hesap yok. Geometri ile başlayın." + birincil buton.
**Yükleniyor:** 4 iskelet kart (shimmer yok; sabit gri blok).
**Hata:** "Oturum yüklenemedi" + `request_id` + "Tekrar dene".
**Kısmi:** Katsayı yoksa metrikler `—`, karar `BEKLIYOR`.

### 3.2 Geometri

| Kart | İçerik |
|---|---|
| Katalog | NPS + Schedule seçici, "Listeden doldur"; seçim OD/WT'yi doldurur |
| Manuel kesit | OD, WT, hat uzunluğu; sağda türetilen ri, Vt, 0.884·ri/s |
| Segmentler | Tablo: #, NPS, Schedule, OD, WT, L, istasyon; ekle/sil/temizle; satır içi düzenleme |
| Test bölümü profili | 4 kot, dizayn basıncı, malzeme kalitesi → SMYS (readonly), Location Class, pompa konumu |
| Kot şeması | Recharts çizgi: start → highest/lowest → end; pompa noktası işaretli |
| Basınç penceresi özeti | Min/max pencere, seçili pompa, 3 limit satırı (uzunluk, hacim, 100% SMYS) |
| 3D önizleme | Küçük sahne (320 px), "Tam sahneye geç" |

Doğrulama: alan altında kırmızı mesaj; `2·WT ≥ OD` hatası WT alanına odaklanır.
`SMYS` kalite seçilmeden boşsa profil hesabı kapalıdır ve gerekçe görünür.

### 3.3 Katsayılar

| Kart | İçerik |
|---|---|
| A — su sıkıştırılabilirliği | T, P, backend seçici; "Hesapla"; sonuç `44.971994 10⁻⁶/bar` + backend rozeti |
| A — mod | Otomatik / Tablo / Manuel; Tablo ise BOTAŞ/GAIL seçici |
| B — kaynak | Üç segment kontrol: Kurum içi (varsayılan) / GAIL / Otomatik; altında model seçici (yalnız otomatik) |
| B — sonuç | Değer, kaynak etiketi, not, `repaired` rozeti, beta/alpha (otomatikse) |
| Üç kaynak karşılaştırma | Tablo: institutional, GAIL, auto; delta kolonları; GAIL hücresi aralık dışıysa kırmızı |
| Backend karşılaştırma | A, β, ρ satırları; hata varsa hücrede "—" + tooltip |
| Provenance | "HESAP / TABLO / MANUEL / BAYAT" badge; bayatsa amber uyarı + "Yenile" |

Ölçüm: bir katsayı hazırlama ≤ 2 tık (T/P zaten doluysa 1 tık).

### 3.4 Hava

| Bölge | İçerik |
|---|---|
| Girdi (sol, 480 px) | T, P, A (readonly + mod), P=1.0 (kilitli görünüm, neden?), K (preset + değer), Vpa |
| Sonuç (sağ) | Vp, kabul limiti, Vpa, oran; yatay gauge: 0 → 1.06·Vp çizgisi, Vpa işareti |
| Karar | `BASARILI/BASARISIZ`, kural, marj, "Neden?" açılır paneli (formül + girdiler) |
| Katsayı özeti | A kaynağı + kontrol tablosu değeri + delta |
| Geçmiş | Bu oturumdaki hava hesapları (zaman, Vpa, sonuç) |
| Uyarılar | P ≠ 1.0 ise alan kırmızı + "Şartname 13: tam 1.0 bar" |

`Vpa` girilmeden "Değerlendir" pasif; gerekçe: "Eksik: Vpa".

### 3.5 Basınç

| Bölge | İçerik |
|---|---|
| Girdi | T, P, A (+mod), B (+kaynak/model), dT, Pa |
| İşaret yardımı | `dT = Tilk − Tson`, `Pa = Pilk − Pson` alan altında sabit; örnek: "+2 °C soğuma" |
| Sonuç | Pt, üst sınır, Pa, marj; gauge: Pt etrafında ±0.3 bar bandı |
| Karar | durum + kural + marj |
| B yorumu | Negatif B ise mavi bilgi kutusu: "B negatif; dP işareti döner, geçerlidir" |
| Duyarlılık | B kaynağına göre Pt farkı (institutional/GAIL/auto) küçük tablo |
| Geçmiş | Son basınç hesapları |

`Tilk/Tson` opsiyonel alanları (parity+): girilirse `dT` otomatik hesaplanır ve kilitlenir;
girilmezse dT doğrudan girilir. Çelişki varsa uyarı.

### 3.6 Profil / Saha

Üç sütun (≥1600 px) / iki sütun (≥1280 px):

| Bölge | İçerik |
|---|---|
| Sol: profil girdileri | Kotlar, dizayn P, SMYS/kalite, Location Class, pompa konumu, izlenen P (slider + input) |
| Orta: grafikler | Kot profili (alan grafiği), basınç penceresi (min–max bandı + monitored noktası), 3 limit kartı |
| Sağ: saha | Checklist (11 madde, progress), pig hesaplayıcı (mod, mesafe, süre, hız gauge) |
| Alt: **3D tam saha** | Tam genişlik, 480–640 px yükseklik; katmanlar ve kesit kontrolleri |

Basınç penceresi grafiği: x = istasyon (0 → L), y = kot; iki yatay çizgi (min/max) ve
monitored noktası. Limit aşılırsa ilgili bölge kırmızı tarama.

Checklist: her satır checkbox + etiket + referans rozeti; "Tümünü tamamla" yok (bilinçli;
operatör tek tek onaylar). Progress `n/11`.

Pig: mod seçilince limit metni; hesap sonrası hız + limit karşılaştırma çubuğu;
limitsiz modda "bilgi" durumu.

### 3.7 Raporlar

| Bölge | İçerik |
|---|---|
| Önizleme | TXT raporu, bölüm başlıklarına göre katlanabilir; `pre` tipografi, kopyala |
| Meta | Rapor no, operatör, tarih (opsiyonel; boşsa "—") |
| İçerik durumu | Hangi bölümler dolu/boş; boş bölüm uyarısı |
| Dışa aktarma | PDF / XLSX / TXT butonları; üretim sırasında spinner + iptal yok |
| Geçmiş | Son export'lar (zaman, format, boyut, indir) |
| OCR bağlantısı | "Raporu OCR ile karşılaştır" → `/ocr?session=…` |

Kural: rapor önizlemesi **salt okunur**; düzeltme ilgili sekmede yapılır. Export sırasında
`revision` değişirse "Oturum değişti, önizlemeyi yenile" uyarısı.

### 3.8 OCR

Akış `§6`'da. Sayfa düzeni: sol yükleme + geçmiş, sağ sonuç (özet / alanlar / uyuşmazlık /
uyarılar sekmeleri). Masaüstü diyaloğunun dört sekmesi korunur.

### 3.9 Ayarlar

| Grup | Alanlar |
|---|---|
| Hesaplama | Su backend'i (liste + "dev backend'leri göster"), varsayılan B kaynağı, steel model |
| Görünüm | Sayı biçimi (tr-TR), tema (açık; koyu "yakında" değil, kapsam dışı), sahne dikey abartı |
| 3D | Renk modu varsayılanı, ızgara/etiket açık-kapalı, animasyon hızı |
| OCR | Motor durumu (readonly), dil, eşleme profilleri, saklama |
| Oturum | Otomatik kayıt aralığı (500 ms debounce sabit), saklama süresi (readonly bilgi) |
| Hakkında | Sürüm, şartname, lisans notları, `request_id` kopyala |

Auth sonrası buraya "Hesap / roller" grubu eklenir; MVP'de "Giriş yakında" gösterilmez
(yanlış beklenti yaratmamak için yalnızca yönetici notu).

---

## 4. Tasarım dili

### 4.1 Renk paleti

| Token | Hex | Kullanım |
|---|---|---|
| `--canvas` | `#F8FAFD` | Sayfa arka planı |
| `--surface` | `#FFFFFF` | Kart |
| `--surface-muted` | `#F5F7FA` | Readonly alan, tablo zebra |
| `--border` | `#D6DCE8` | Kart/alan kenarı |
| `--border-strong` | `#B9C4D6` | Odak dışı vurgu |
| `--text` | `#111827` | Ana metin |
| `--text-muted` | `#6B7280` | Yardım metni |
| `--text-inverse` | `#FFFFFF` | Koyu zemin |
| `--primary-900` | `#16365D` | Başlık, birincil buton |
| `--primary-700` | `#243B73` | İkincil vurgu, link |
| `--primary-100` | `#EEF4FF` | Bilgi zemini |
| `--focus` | `#1D4ED8` | Odak halkası |
| `--success` | `#1E6F43` | Başarılı metin |
| `--success-bg` | `#EEF8EE` | Başarılı zemin |
| `--warning` | `#8A5B00` | Uyarı metni |
| `--warning-bg` | `#FFF6E5` | Uyarı zemini |
| `--danger` | `#A4262C` | Hata metni |
| `--danger-bg` | `#FDEAEA` | Hata zemini |
| `--info` | `#16365D` | Bilgi metni |
| `--info-bg` | `#EEF4FF` | Bilgi zemini |
| `--neutral-bg` | `#F1F3F5` | Bekliyor |

Durum eşlemesi: `BEKLIYOR` → neutral; `KATSAYI GUNCELLENMELI` / `DOGRULANAMADI` →
warning; `BASARILI` → success; `BASARISIZ` → danger; `BILGI` → info.

### 4.2 Tipografi

- Aile: `Inter`, yedek `"Segoe UI", system-ui, sans-serif`.
- Ölçek: 12 (yardım), 13 (tablo), 14 (gövde), 16 (kart başlığı), 20 (bölüm), 24 (sayfa),
  32 (karar durumu).
- Ağırlık: 400 gövde, 500 etiket, 600 başlık, 700 karar.
- Sayılar: `font-variant-numeric: tabular-nums`; ondalık hizalama sağa.
- Satır yüksekliği 1.45; uzun paragraflar 72ch.

### 4.3 Boşluk ve yüzey

- 4 px taban; kullanılan adımlar 4, 8, 12, 16, 24, 32, 48.
- Kart içi 16 (mobil 12), kart arası 16, bölüm arası 24.
- Köşe yarıçapı: alan 6, kart 8, modal 12.
- Gölge: `0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.1)`; hover'da artmaz.
- Kenarlık 1 px; odak 2 px + 2 px offset.

### 4.4 Erişilebilirlik

- WCAG 2.2 AA: metin kontrastı ≥ 4.5:1, büyük metin ≥ 3:1; durum yalnız renkle
  anlatılmaz (ikon + metin).
- Dokunma hedefi ≥ 44×44 px (tablet).
- Her alan görünür `<label>`; placeholder etiket yerine geçmez.
- Hata: `aria-invalid="true"` + `aria-describedby` ile mesaj; hata özeti `role="alert"`.
- Tablo: `<caption>`, `scope` başlıkları, satır seçimi klavyeyle.
- Grafik: özet metin + "Veri tablosu" aç/kapa; renk körlüğü için desen/etiket.
- 3D: "3D'yi atla" bağlantısı, eşdeğer tablo, kamera ön ayarları klavyeyle.
- `prefers-reduced-motion` → animasyonlar kapanır, pig "anlık konum" moduna geçer.
- Dil: `<html lang="tr">`; tarih/sayı `Intl.NumberFormat("tr-TR")`.

### 4.5 Klavye

| Kısayol | Eylem |
|---|---|
| `Tab` / `Shift+Tab` | Alanlar arası |
| `Enter` | Sonraki alan (metin girişinde) |
| `Shift+Enter` | Önceki alan |
| `Ctrl/Cmd+Enter` | Aktif testi değerlendir |
| `F5` | Katsayıları yenile |
| `Alt+1…9` | Sekme değiştir |
| `/` | Oturum/alan arama |
| `Esc` | Drawer/modal kapat |
| `?` | Kısayol yardımı |

Odak halkası her zaman görünür (fare tıklamasında da). Hatalı alana otomatik odak +
`scrollIntoView({block:"center"})`.

---

## 5. 3D sahne etkileşimleri

### 5.1 Sahne içeriği

- Zemin düzlemi + ölçek ızgarası (her 500 m / 1 km etiket).
- Segment silindirleri: OD/WT oranına göre duvar kalınlığı; segment sınırlarında halka.
- Vanalar: gövde + el çarkı; açık/kapalı renk.
- Pompa: uçta kutu + boru bağlantısı; yön oku.
- Test başlığı: kısa dikey boru + manometre sembolü.
- Pig: disk; hareket yönü oku; limit durumuna göre renk.
- Kot profili: zeminin altında/üstünde ince çizgi + dolgu (toggle).
- Akış animasyonu: boru içinde akan çizgiler/partiküller; hız pig hızıyla ölçeklenir.
- Basınç/utilization renkleri: segment yüzeyi renk skalası (mavi → yeşil → amber → kırmızı).
- Etiketler: NPS, istasyon, basınç (zoom'a göre LOD).

### 5.2 Kontroller

| Etkileşim | Davranış |
|---|---|
| Sol tık + sürükle | Yörünge döndürme |
| Tekerlek / iki parmak | Zoom (min 0.5×, max 20×) |
| Sağ tık + sürükle / iki parmak kaydır | Pan |
| Segment tık | Seç; sağ panelde detay; URL `?seg=2`; klavyede `←/→` segment gezer |
| Hover | Tooltip: istasyon, kot, OD/WT, P, utilization, durum |
| Kesit slider | İstasyon boyunca kesme düzlemi; iç yüzey + et kalınlığı görünür |
| "Kesit" toggle | Yarım boru (180°) / tam kesit / kapalı |
| Katmanlar | ground, pipe, valves, pump, test_head, pig, flow, profile, labels |
| Renk modu | Basınç / utilization / malzeme / durum; lejant sağ altta |
| Kamera ön ayarları | Genel, pompa ucu, pig takip, kesit, kuş bakışı |
| Pig animasyonu | Oynat/durdur, 1×/10×/60×, zaman çizgisi; süre = `travel_time_min` |
| "Sahneyi sıfırla" | Kamera + katmanlar varsayılan |

### 5.3 Performans ve dayanıklılık

- Hedef: 1080p, entegre GPU'da ≥ 45 fps; 10 000 m hat, 20 segment.
- Uzun hatlarda `InstancedMesh`; segment başına ayrı mesh yok.
- `dpr` üst sınırı 2; sekme gizliyken render durur (`document.visibilityState`).
- Kesit/animasyon sırasında gölge ve post-process kapalı.
- Sahne yüklenemezse (WebGL yok) eşdeğer 2D kot profili + tablo gösterilir; hata değil,
  "3D bu cihazda kapalı" bilgisi.
- `warnings` doluysa sahne üstünde amber rozet: "Yaklaşık sahne — kot profili 4 noktadan
  türetildi".

### 5.4 Erişilebilir alternatif

Sahnenin altında katlanabilir tablo: segment, istasyon, kot, OD/WT, P, utilization, durum.
"3D'yi atla" bağlantısı tabloya odaklanır. Kamera ön ayarları düğme olarak da mevcut.

---

## 6. OCR akışı

### 6.1 Adımlar

1. **Yükleme** — sürükle-bırak veya dosya seç. Kabul: PDF/JPG/PNG/TIFF/BMP/WEBP, ≤25 MB.
   Anında ön kontrol: uzantı, boyut; hata alan altında.
2. **Hazırlık** — "Hesaplanan değerlerle karşılaştır" toggle (varsayılan açık, oturum
   varsa payload otomatik). "Analiz et".
3. **İlerleme** — aşamalar: `Yükleniyor` → `Metin/OCR çıkarılıyor` →
   `Alanlar ayrıştırılıyor` → `Karşılaştırılıyor`. Süre + aşama; "İptal".
   Sayfa sayısı ancak çıkarım bitince gösterilir (servis sayfa bazlı ilerleme vermiyor).
4. **Sonuç özeti** — kaynak (PDF metin katmanı / OCR / karma), sayfa, ortalama güven,
   engelleyici uyuşmazlık sayısı, `needs_human_review` bandı.
5. **Alan onayı** — tablo: alan, değer, birim, güven, ham metin, sayfa.
   Güven rozetleri: ≥0.85 yeşil, 0.60–0.85 amber, <0.60 kırmızı.
   Düşük güvenli alan düzenlenebilir; düzenleme "onaylandı" sayılmaz, ayrıca onay gerekir.
6. **Uyuşmazlık paneli** — kritik/uyarı grupları; alan, rapor değeri, hesaplanan, fark,
   tolerans, mesaj. "Hesaba git" ilgili sekmeye taşır.
7. **Onay** — "Seçilenleri onayla" / "Tümünü onayla". Düşük güvenli alan onaylanmadan
   "Tümünü onayla" pasif; gerekçe görünür.
8. **Uygula** (opsiyonel) — onaylı alanları oturuma yaz; çakışan alanlar için onay iste.

### 6.2 Durumlar

| Durum | Gösterim |
|---|---|
| Boş | Sürükle-bırak alanı + desteklenen formatlar + "OCR hazır değil" uyarısı (motor yoksa) |
| Yükleniyor | Dosya adı + boyut + iptal |
| Analiz | Aşama göstergesi; sayfa sayacı; iptal |
| Başarılı, uyuşmazlık yok | Yeşil özet + "İnsan onayı yine gerekli" notu |
| Başarılı, kritik uyuşmazlık | Kırmızı özet + "Kabul akışı durduruldu" + iki kişi onayı önerisi |
| Motor yok | "Taranmış belge için OCR kurulu değil" + kurulum komutu (yalnız yönetici) |
| Rasterizer yok | Metin katmanı yoksa "Taranmış PDF desteği kapalı" + yönetici notu; görsel OCR çalışmaya devam eder |
| Hata | Kod + Türkçe mesaj + `request_id`; "Yeniden dene" (dosya korunur) |
| Zaman aşımı | "300 sn aşıldı"; daha küçük dosya/daha az sayfa önerisi |

### 6.3 Alan eşleme konfigürasyonu (format yarın geliyor)

- **Profil seçici** üstte; default profil otomatik seçilir.
- **Profil düzenleyici** (yalnız yetkili): kanonik alan listesi (solda) → etiket alias'ları
  (sağda, çoklu satır), birim, regex, zorunluluk, bölüm ipucu.
- "JSON olarak düzenle" sekmesi: şema doğrulamalı editör; hata satırı işaretlenir.
- **Kuru çalıştırma:** yüklenen metin üzerinde eşlemeyi uygula, eşleşen/eşleşmeyen
  alanları göster (hesap yapmaz). Bu, format geldiğinde kalibrasyonun ana aracıdır.
- Profil sürümlenir (`updated_at`); analiz, kullandığı profil kimliğini saklar.
- Format değişince **yeni profil**; eski analizler eski profille okunur.

### 6.4 Güven ve sorumluluk

- Her ekranda kalıcı not: "OCR çıktısı resmi kabul değildir; yetkili personel onayı
  zorunludur." (`needs_human_review` her zaman `true`).
- Düşük güvenli alan sayısı kadar "onay bekliyor" rozeti sekmede görünür.
- Onaylayan, zaman ve alan bazlı değişiklik denetim izine yazılır (auth sonrası kullanıcı).

---

## 7. Responsive davranış

| Genişlik | Yerleşim |
|---|---|
| ≥1600 | Sol nav 208 px + içerik + sağ panel 320 px; 3 sütun form |
| 1440–1599 | Sol nav 208 px + içerik + sağ panel 288 px; 2–3 sütun |
| 1280–1439 | Sol nav daraltılmış 64 px (ikon + tooltip) + içerik; sağ panel drawer |
| 1024–1279 | Üst sekme şeridi; tek sütun kart; yapışkan alt aksiyon çubuğu |
| 768–1023 | Tablet: tek sütun; tablolar yatay kaydırma; 3D tam genişlik 360 px |
| <768 | Yalnız okuma/onay: formlar tek sütun, 3D statik görsel + tablo; hesaplama kapalı |

Kurallar:

- Yatay kaydırma yalnız tablo ve 3D sahne içinde; sayfa gövdesinde asla.
- Alt aksiyon çubuğu `position: sticky`; iOS güvenli alan payı.
- Form alanları 2 sütundan 1 sütuna düşerken etiket üstte kalır.
- Grafikler `ResizeObserver` ile yeniden boyutlanır; minimum 280×160 px.
- 3D sahne tablette tam genişlik; kamera kontrolleri dokunmatik (tek parmak döndür,
  iki parmak zoom/pan).

---

## 8. Bileşen envanteri

| Bileşen | Sorumluluk |
|---|---|
| `AppShell` | Nav, üst bar, karar şeridi, sağ panel |
| `SessionPicker` | Oturum listesi, yeni, kaydetme durumu |
| `DecisionStrip` | Durum + kural + marj; renk eşlemesi |
| `DecisionCard` | Test kararı, neden paneli, aksiyonlar |
| `Field` | Etiket, birim, yardım, hata, readonly; `aria-describedby` |
| `NumberField` | `tr-TR` ayrıştırma, min/max, adım, hata |
| `SelectField` | Enum, açıklama, opsiyonel "Özel" |
| `FieldGrid` | 1/2/3/4 sütun |
| `SectionCard` | Başlık, açıklama, aksiyon, durum rozeti |
| `ResultTile` | Değer + birim + delta + durum |
| `GateButton` | Pasif + "Eksik: …" gerekçesi |
| `PressureWindowChart` | Min/max bandı + monitored |
| `ElevationProfileChart` | Kot profili + eğim |
| `TrendChart` | P/T/V zaman serisi |
| `RatioGauge` | Vpa/Vp ve marj |
| `ChecklistGrid` | 11 madde + progress |
| `FullFieldScene` | 3D sahne + kontroller |
| `SceneLegend` | Renk skalası |
| `SegmentTable` | Düzenlenebilir segmentler |
| `CoefficientBadge` | HESAP/TABLO/MANUEL/BAYAT |
| `DiscrepancyTable` | OCR uyuşmazlıkları |
| `ConfidenceBadge` | Güven eşikleri |
| `MappingEditor` | Profil alan eşlemesi |
| `EmptyState`, `ErrorState`, `Skeleton` | Durum bileşenleri |
| `Toast` | Kısa geri bildirim (3 sn; hata 8 sn) |
| `ConfirmDialog` | Silme/iptal |

---

## 9. Durum ve geri bildirim desenleri

| Durum | Kural |
|---|---|
| **Boş** | Ne olduğu + neden + tek CTA. Asla yalnız "Veri yok". |
| **Yükleniyor** | İskelet; 300 ms'den kısa yüklemede gösterilmez (titremeyi önler) |
| **Hata** | Ne oldu + ne yapmalı + `request_id` kopyala; form verisi korunur |
| **Kısmi** | Hesaplanabilen alanlar gösterilir, hesaplanamayan `—` + neden |
| **Bayat** | `KATSAYI GUNCELLENMELI`; değer korunur ama karar üretilmez |
| **Çevrimdışı** | Üstte kalıcı şerit "Bağlantı yok — girdiler yerel olarak korunuyor"; kaydetme kuyruğa alınır |
| **Çakışma** | "Bu oturum başka bir sekmede değişti" + alan farkları + "Benimkini uygula" / "Sunucuyu al" |
| **Başarı** | Kısa toast; karar kartı zaten güncellenir (çift bildirim yok) |

Sayı gösterimi: `Intl.NumberFormat("tr-TR", {maximumFractionDigits: n})`. Birimler
etiketten ayrı, küçük ve soluk; `10⁻⁶/bar` üst simgeyle.

---

## 10. Terminoloji ve metin

- "Saha Kontrol" tek terim (başka yerde "Saha" / "Field" kullanılmaz).
- "Katsayı" (A/B), "katsayı kaynağı", "bayat" (stale).
- Birimler: `°C`, `bar`, `m³`, `m/s`, `km/sa`, `10⁻⁶/bar`, `10⁻⁶/°C`, `mm`, `m`, `MPa`.
- Karar: `BEKLIYOR`, `KATSAYI GUNCELLENMELI`, `DOGRULANAMADI`, `BASARILI`, `BASARISIZ`
  (masaüstüyle birebir; çeviri değiştirilmez).
- Hata mesajı: ne oldu + hangi alan + nasıl düzeltilir. "Hata oluştu" yasak.
- OCR: "okundu" ≠ "doğrulandı"; "onay" yalnız insan eylemi için.

---

## 11. Ölçülebilir kabul kriterleri

| Ölçüt | Hedef |
|---|---|
| İlk hesaplama | Dashboard'dan ≤ 3 tık (geometri doluysa ≤ 2) |
| Zorunlu alan kapısı | Eksik alan varken değerlendirme butonu %100 pasif + gerekçeli |
| Klavye | Tüm form alanları ve butonlar yalnız klavyeyle erişilebilir |
| Odak görünürlüğü | Her odaklanabilir öğede 2 px halka |
| Kontrast | Tüm metin AA; otomatik axe testi 0 kritik ihlal |
| Form hatası | Alan altında ≤ 100 ms içinde görünür (yerel doğrulama) |
| 3D | 1080p / entegre GPU ≥ 45 fps; ilk kare ≤ 1.5 s |
| OCR geri bildirimi | Yükleme sonrası ilk durum ≤ 200 ms |
| OCR onay kapısı | Düşük güvenli alan onaysız "Tümünü onayla" imkânsız |
| Rapor önizleme | TXT içeriği ≤ 1 s içinde; export ≤ 5 s (10 sayfa) |
| Boş/hata durumu | Her sekmede tanımlı ve test edilmiş |
| Responsive | 1024 px'te yatay sayfa kaydırması yok |
| Erişilebilirlik | `prefers-reduced-motion` desteklenir; 3D alternatifi var |

---

## 12. Açık UX kararları

1. **Sağ panel** masaüstünde varsayılan açık mı? Öneri: ≥1440 px açık, altında kapalı.
2. **Koyu tema** kapsam dışı; talep gelirse token'lar hazır.
3. **Wizard** masaüstündeki 4 adım web'de Dashboard + sekmelerle çakışıyor. Öneri:
   wizard'ı ayrı mod olarak değil, Dashboard'daki "sıradaki adım" rehberi olarak uygula.
4. **3D varsayılan sekmesi:** Profil/Saha içinde açık; Dashboard'da küçük önizleme.
5. **OCR onayı oturuma otomatik uygulanmalı mı?** Öneri: hayır; ayrı "Uygula" adımı.
6. **Tilk/Tson alanları** Basınç sekmesine eklenmeli mi? Öneri: evet (parity+), dT türetimi
   ile; çelişki uyarısı.
7. **Rapor kimliği** (rapor no, operatör, tarih) Raporlar sekmesinde mi, Ayarlar'da
   varsayılan mı? Öneri: Raporlar'da oturum bazlı.
8. **Tablet hesaplama** açık mı? Öneri: açık; yalnız <768 px'te salt okuma.
