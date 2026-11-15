import type {
  CheckKey,
  LocationClassRule,
  PigModeOption,
  SpecLimits,
  SteelModel,
  TabKey,
} from "./types";

export interface TabMeta {
  key: TabKey;
  label: string;
  path: string;
  index: number;
  group: "calisma" | "cikti";
  description: string;
  hidden?: boolean;
}

export const TABS: TabMeta[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    path: "/",
    index: 1,
    group: "calisma",
    description: "Proje durumu, kararlar ve sıradaki adım",
  },
  {
    key: "projects",
    label: "Projeler & Kesitler",
    path: "/projects",
    index: 2,
    group: "calisma",
    description: "Proje kayıtları, kesit listesi ve kayıtlı çalışmalar",
  },
  {
    key: "geometry",
    label: "Geometri & Saha",
    path: "/geometry",
    index: 3,
    group: "calisma",
    description: "Kesit, segment, kot, malzeme, basınç penceresi ve pig",
  },
  {
    key: "coefficients",
    label: "Katsayılar",
    path: "/coefficients",
    index: 4,
    group: "calisma",
    description: "A/B hazırlama ve testlere hızlı geçiş",
  },
  {
    key: "coefficient_detail",
    label: "Katsayı Detayı",
    path: "/coefficient-detail",
    index: 5,
    group: "calisma",
    description: "Üç kaynak, backend ve A onarım karşılaştırması",
  },
  {
    key: "air",
    label: "Hava İçerik",
    path: "/air",
    index: 6,
    group: "calisma",
    description: "Hava içerik testi değerlendirmesi",
  },
  {
    key: "pressure",
    label: "Basınç Değişim",
    path: "/pressure",
    index: 7,
    group: "calisma",
    description: "Basınç değişim testi değerlendirmesi",
  },
  {
    key: "reports",
    label: "Raporlar",
    path: "/reports",
    index: 8,
    group: "cikti",
    description: "Rapor önizleme ve dışa aktarma",
  },
  {
    key: "ocr",
    label: "OCR",
    path: "/ocr",
    index: 9,
    group: "cikti",
    description: "Rapor yükleme, alan onayı, uyuşmazlık",
  },
  {
    key: "settings",
    label: "Ayarlar",
    path: "/settings",
    index: 10,
    group: "cikti",
    description: "Backend, görünüm ve oturum yönetimi",
  },
  {
    key: "field",
    label: "Profil / Saha",
    path: "/field",
    index: 0,
    group: "calisma",
    description: "Eski bağlantı; Geometri & Saha sayfasına yönlendirilir",
    hidden: true,
  },
];

/** Kenar çubuğunda görünen sekmeler (eski `field` gizlidir). */
export const VISIBLE_TABS = TABS.filter((tab) => !tab.hidden);

export const TAB_BY_KEY: Record<TabKey, TabMeta> = TABS.reduce(
  (acc, tab) => {
    acc[tab.key] = tab;
    return acc;
  },
  {} as Record<TabKey, TabMeta>,
);

export function tabFromHash(hash: string): TabKey {
  const path = hash.replace(/^#/, "").split("?")[0] || "/";
  /* Eski `#/field` bağlantıları birleşik Geometri & Saha sayfasına gider. */
  if (path === "/field") return "geometry";
  const found = TABS.find((tab) => !tab.hidden && tab.path === path);
  return found?.key ?? "dashboard";
}

export function hashForTab(tab: TabKey): string {
  if (tab === "field") return "#/geometry";
  return `#${TAB_BY_KEY[tab].path}`;
}

export const CHECK_DEFINITIONS: Array<{ key: CheckKey; label: string; ref: string }> = [
  {
    key: "ambient_temp",
    label: "Dolum sırasında hava sıcaklığı +2 °C limitine göre kontrol edildi",
    ref: "10.1",
  },
  {
    key: "temp_probes",
    label: "Boru ve toprak sıcaklık probları uygun yerlere yerleştirildi",
    ref: "10.4",
  },
  {
    key: "fill_air_entry",
    label: "Su dolumu sırasında sisteme hava girmesi engellendi",
    ref: "11.2",
  },
  {
    key: "fill_records",
    label: "Doldurulan su hacmi ve sıcaklığı saatlik olarak kaydedildi",
    ref: "11.3-11.4",
  },
  {
    key: "thermal_balance",
    label: "Minimum 24 saat termal dengeleme ve 0,5 °C koşulu kontrol edildi",
    ref: "12",
  },
  {
    key: "air_content_limit",
    label: "Hava içerik testi %6 kabul sınırına göre teyit edildi",
    ref: "13",
  },
  {
    key: "pressurization_volume",
    label: "14.2 için basınç-hacim ve %0,2 ilave su limiti izlendi",
    ref: "14.2",
  },
  {
    key: "two_hour_hold",
    label: "14.3 için 2 saat bekleme ve 15 dakikalık okumalar alındı",
    ref: "14.3",
  },
  {
    key: "pressure_records",
    label: "24 saatlik basınç ve sıcaklık kayıtları düzenli tutuldu",
    ref: "15.1",
  },
  {
    key: "depressurize_discharge",
    label: "Basınç düşürme ve boşaltma işlemleri kontrollü ve raporlu yapıldı",
    ref: "16-17",
  },
  {
    key: "forms",
    label: "21.1-21.5 saha formları dolduruldu",
    ref: "21",
  },
];

export const K_PRESETS = [
  { label: "Kaynaklı boru - 1.02", value: 1.02 },
  { label: "Dikişsiz boru - 1.00", value: 1.0 },
  { label: "Özel", value: null },
] as const;

export const STEEL_PRESETS = [
  { label: "Karbon çelik - 12.0", value: 12.0 },
  { label: "Düşük alaşımlı - 12.5", value: 12.5 },
  { label: "Paslanmaz - 16.0", value: 16.0 },
  { label: "Özel", value: null },
] as const;

export const STEEL_MODEL_OPTIONS: Array<{ value: SteelModel; label: string; note: string }> = [
  {
    value: "volumetric",
    label: "Hacimsel (β − 3α)",
    note: "Varsayılan; hacimsel genleşme eksi üç eksenel çelik genleşmesi.",
  },
  {
    value: "linear",
    label: "Doğrusal (β − α)",
    note: "Yalnızca eksenel çelik genleşmesi düşülür.",
  },
  {
    value: "volumetric_temperature",
    label: "Sıcaklığa bağlı (β − 3α(T))",
    note: "α(T) = 10,8 + 0,012·T ilişkisi kullanılır.",
  },
];

export const FALLBACK_LOCATION_CLASSES: LocationClassRule[] = [
  {
    class_number: 1,
    label: "Class 1 - min 1.25 x dizayn basinci",
    minimum_test_factor: 1.25,
    spec_reference: "NGTL 5007 / 4.2, ASME B31.8 Class 1",
  },
  {
    class_number: 2,
    label: "Class 2 - min 1.25 x dizayn basinci",
    minimum_test_factor: 1.25,
    spec_reference: "NGTL 5007 / 4.2, ASME B31.8 Class 2",
  },
  {
    class_number: 3,
    label: "Class 3 - min 1.50 x dizayn basinci",
    minimum_test_factor: 1.5,
    spec_reference: "NGTL 5007 / 4.2, ASME B31.8 Class 3",
  },
  {
    class_number: 4,
    label: "Class 4 - min 1.50 x dizayn basinci",
    minimum_test_factor: 1.5,
    spec_reference: "NGTL 5007 / 4.2, ASME B31.8 Class 4",
  },
];

export const FALLBACK_PIG_MODES: PigModeOption[] = [
  { label: "Temizlik pigi", spec_reference: "Madde 9", max_speed_m_per_s: 2.5 },
  { label: "Ön kurutma pigi", spec_reference: "Madde 18.3", max_speed_m_per_s: 2.222 },
  { label: "Nihai kurutma süngeri", spec_reference: "Madde 20.5", max_speed_m_per_s: 1.2 },
  { label: "Serbest kontrol", spec_reference: "Bilgi", max_speed_m_per_s: null },
];

export const FALLBACK_LIMITS: SpecLimits = {
  max_file_size_bytes: 26_214_400,
  max_pdf_pages: 200,
  max_ocr_pages: 30,
  max_test_section_length_m: 20_000,
  max_test_section_volume_m3: 12_500,
  air_acceptance_factor: 1.06,
  pressure_variation_acceptance_bar: 0.3,
  pressurization_volume_limit_percent: 0.2,
  thermal_balance_min_hours: 24,
  thermal_balance_threshold_c: 0.5,
  ambient_temp_limit_c: 2,
  air_pressure_rise_bar: 1,
};

export const FALLBACK_PUMP_LOCATIONS = ["Baslangic noktasi", "Bitis noktasi"];

export const PUMP_LABELS: Record<string, string> = {
  "Baslangic noktasi": "Başlangıç noktası",
  "Bitis noktasi": "Bitiş noktası",
  "Başlangıç noktası": "Başlangıç noktası",
  "Bitiş noktası": "Bitiş noktası",
};

export const STEEL_ALPHA_DEFAULT = 12.0;
export const WATER_DENSITY_15C = 999.1;
