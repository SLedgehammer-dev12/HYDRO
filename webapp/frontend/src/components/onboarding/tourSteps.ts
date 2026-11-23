import type { TabKey } from "../../lib/types";

export interface TourStep {
  id: string;
  tab: TabKey;
  targetSelector: string;
  title: string;
  description: string;
  hint: string;
}

export const GUIDED_TOUR_STEPS: TourStep[] = [
  {
    id: "projects",
    tab: "projects",
    targetSelector: '[data-tour="nav-projects"]',
    title: "1 / 5 · Proje & Kesit Seçimi",
    description:
      "Çalışmalar Proje altında Test Bölümleri (Kesit) olarak tutulur. Örnek projeyi seçebilir, kendi projenizi oluşturabilir veya mevcut kesitler arasında güvenle geçiş yapabilirsiniz.",
    hint: "İpucu: Bir kesite tıkladığınızda tüm girdi ve BOTAŞ formları otomatik yüklenir.",
  },
  {
    id: "geometry",
    tab: "geometry",
    targetSelector: '[data-tour="nav-geometry"]',
    title: "2 / 5 · Geometri, Kot & 3D Saha",
    description:
      "Boru dış çapı, et kalınlığı, segment uzunlukları, SMYS/malzeme ve kot profili burada tanımlanır. Sağlıklı girilen profil verileri aynı ekranda 3D sahneyi ve basınç penceresini oluşturur.",
    hint: "İpucu: Plan-Profil veya saha etüdü CSV/Excel verilerini tek tıkla içe aktarabilirsiniz.",
  },
  {
    id: "ocr",
    tab: "ocr",
    targetSelector: '[data-tour="nav-ocr"]',
    title: "3 / 5 · OCR ile Rapor & Form Okuma",
    description:
      "Sahadan gelen taranmış PDF veya Excel test formlarını buraya yükleyin. Sistem değerleri ayıklayıp mühendislik hesaplarıyla karşılaştırır ve ilgili BOTAŞ formlarına aktarır.",
    hint: "İpucu: Sekme değiştirseniz bile sunucudaki OCR taraması arka planda güvenli şekilde devam eder.",
  },
  {
    id: "air",
    tab: "air",
    targetSelector: '[data-tour="nav-air"]',
    title: "4 / 5 · Hava, Basınç Testi & Karar",
    description:
      "Hava İçerik (Vpa < 1,06·Vp) ve Basınç Değişim (|Pa - Pt| ≤ 0,3 bar) değerlendirmeleri şartname kurallarına göre net BASARILI / BASARISIZ kararı ve marj üretir.",
    hint: "İpucu: Hesaplama sekmelerinde üst karar şeridi anlık durumu her an görünür tutar.",
  },
  {
    id: "reports",
    tab: "reports",
    targetSelector: '[data-tour="nav-reports"]',
    title: "5 / 5 · Resmî Rapor & Ham OCR Eki",
    description:
      "Değerlendirme tamamlandığında tek tıkla PDF, Excel veya TXT raporu indirebilirsiniz. İsterseniz ham OCR metin ve form özetini (OCR_Ham_Metin) rapora ekleyebilirsiniz.",
    hint: "Turu dilediğiniz zaman sağ üstteki ? Yardım menüsünden yeniden başlatabilirsiniz.",
  },
];
