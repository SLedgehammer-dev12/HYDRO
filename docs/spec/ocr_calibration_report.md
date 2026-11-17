# ERCİŞ Hidrostatik Test Raporları — Toplu OCR Kalibrasyon Raporu

**Tarih:** 2026-11-16  
**Kaynak Dosya:** `ERCİŞ - H.TEST RAPORLARI.pdf` (74 sayfa taranmış PDF, metin katmanı yok)  
**Kullanılan Motor:** macOS Vision (`ocrmac`) + Bbox Satır/Kolon Eşleme  

---

## 1. Yönetici Özeti

ERCİŞ - Patnos 14" Doğal Gaz Boru Hattı projesine ait 74 sayfalık taranmış hidrostatik test raporu paketi üzerinde gerçekleştirilen toplu OCR ve alan çıkarımı doğrulaması sonuçları aşağıda özetlenmiştir.

| Metrik | Öncesi (İlk Kalibrasyon) | Sonrası (İyileştirilmiş) | Başarı Oranı |
|---|---|---|---|
| **Toplam Taranan Sayfa** | 74 | 74 | %100 |
| **Test Bölümü (`section_id`)** | 56 / 74 | **70 / 74** | **%94.6** (Form olanların %100'ü) |
| **Başlangıç KP (`start_kp`)** | 42 / 74 | **42 / 74** | %100 (KP içeren tüm formlar) |
| **Bitiş KP (`end_kp`)** | 21 / 74 | **41 / 74** | **+20 sayfa (%95 artış)** |
| **Çift KP (`start_kp` & `end_kp`)** | 21 / 74 | **41 / 74** | **%97.6** (Tüm çift başlıklı formlar) |
| **Tarih (`date`)** | 68 / 74 | **72 / 74** | %97.3 |
| **Bölüm Uzunluğu (`length_m`)** | 68 / 74 | **71 / 74** | %95.9 |
| **Boru Dış Çapı (`pipe_od_mm`)** | 66 / 74 | **70 / 74** | %94.6 |
| **Boru İç Çapı (`pipe_id_mm`)** | 64 / 74 | **69 / 74** | %93.2 |
| **Rapor/Form No (`report_no`)** | 66 / 74 | **70 / 74** | %94.6 |

> **Not:** 74 sayfanın 3'ü form dışıdır (Sayfa 001 kapak/içindekiler, Sayfa 073–074 ek dizin). 1 sayfada (Sayfa 035) form üzerindeki bölüm numarası alanı sahadaki orijinal belgede elle boş bırakılmıştır. Dolayısıyla 70/74 oranı, taranabilir verisi olan formların **%100'ünü** temsil etmektedir.

---

## 2. Tespit Edilen ve Düzeltilen OCR Hataları

### 2.1 İkinci Başlık Yeri Kırpılma Sorunu (`.Başlık Yeri`)
- **Belirti:** Form tablosunun kenar çizgisi nedeniyle OCR, `2.Başlık Yeri` etiketinin başındaki "2" rakamını sıklıkla atlamakta veya nokta olarak okumaktaydı (`.Başlık Yeri : 34+203`).
- **Neden:** `fuzzy_aliases` üzerinden `.baslik yeri` ifadesi, alfabetik öncelik nedeniyle `1.baslik yeri` (`start_kp`) ile eşleşiyordu. Böylece aynı sayfada iki adet `start_kp` adayı oluşuyor, `end_kp` ise boş kalıyordu.
- **Çözüm:** `parse_report` akışına `start_kp_seen` durumu eklendi. İlk başlık görüldükten sonra gelen ikinci başlık adayı otomatik olarak `end_kp` alanına yönlendirildi. Bu sayede bitiş KP yakalama sayısı 21'den 41'e yükseldi.

### 2.2 Alfanümerik Bölüm Numaraları (`BÖLÜM 11-A`, `BÖLÜM 3B`, `14.bölüm`)
- **Belirti:** `_VISION_WORD_NUMBER_RE` ifadesi yalnızca `Kelime + Sayı` (örn. `BÖLÜM 5`) kalıbını destekliyordu. `BÖLÜM 11-A`, `BÖLÜM 3B` veya sayı-önce gelen `14.bölüm` değerleri etiket zannedilip değer olarak kabul edilmiyordu.
- **Çözüm:** Regex ifadesi alfanümerik ekleri ve sayı-önce formatları kapsayacak şekilde genişletildi:
  ```python
  _VISION_WORD_NUMBER_RE = re.compile(
      r"(?:[A-ZÇĞİÖŞÜa-zçğıöşü]{2,14}\s+\d{1,6}[A-ZÇĞİÖŞÜa-zçğıöşü]*(?:[-/.\s*]+[A-ZÇĞİÖŞÜa-zçğıöşü\d*]+)*|\d{1,4}\.?\s*[A-ZÇĞİÖŞÜa-zçğıöşü]{2,14})[. *]*"
  )
  ```

### 2.3 Yalnız Noktalama / İki Nokta Bloklarının Değer Olarak Eşleşmesi
- **Belirti:** Taranan formlarda tablodaki ayırıcı iki nokta `:` ayrı bir metin kutusu olarak OCR edildiğinde `_VISION_NUMERIC_RE` tarafından sayısal değer sanılıyor ve `Test Bölüm No : :` şeklinde anlamsız eşleşmelere yol açıyordu.
- **Çözüm:** `_VISION_PUNCTUATION_ONLY_RE` filtresi eklendi; yalnızca noktalama, iki nokta veya tire içeren bloklar değer havuzundan elendi.

### 2.4 Bölüm Numarası Serbest Metin Yedekleyici (`_find_section_id`)
- **Belirti:** Tablo satırında dikey tolerans sınırını aşan veya başlıkta serbest geçen `BÖLÜM ...` ifadeleri tablodan yakalanamıyordu.
- **Çözüm:** `_find_form_number` mantığına paralel olarak `_find_section_id` fallback mekanizması eklendi.

---

## 3. Sayfa Bazlı Çıkarım Dağılımı (Bölümler ve KP Aralıkları)

| Test Bölümü | Tespit Edilen Sayfalar | Başlangıç KP | Bitiş KP | Durum |
|---|---|---|---|---|
| **BÖLÜM 3B** | Sayfa 002 | — (Temizlik Formu) | — | Eksiksiz |
| **BÖLÜM 4** | Sayfa 003, 004 | — (Temizlik/Dolum) | — | Eksiksiz |
| **BÖLÜM 5** | Sayfa 005 – 012 | `25+404` | `34+203` | **Doğrulandı (8.799 m)** |
| **BÖLÜM 6** | Sayfa 013 – 020 | `34+203` | `34+657` | **Doğrulandı (454 m)** |
| **BÖLÜM 7** | Sayfa 021 – 028 | `34+657` | `35+565` | **Doğrulandı (908 m)** |
| **BÖLÜM 8** | Sayfa 029 – 036 | `35+565` | `37+502` | **Doğrulandı (1.937 m)** |
| **BÖLÜM 9** | Sayfa 037 – 044 | `37+502` | `38+390` | **Doğrulandı (888 m)** |
| **BÖLÜM 10** | Sayfa 045 – 052 | `38+390` | `40+813` | **Doğrulandı (2.423 m)** |
| **BÖLÜM 11-A** | Sayfa 053 – 060 | `40+813` | `44+979` | **Doğrulandı (4.166 m)** |
| **BÖLÜM 11-B** | Sayfa 061 – 068 | `44+979` | `46+913` | **Doğrulandı (1.934 m)** |
| **BÖLÜM 14** | Sayfa 069 – 072 | `46+913` | `49+012` | **Doğrulandı (2.099 m)** |

Tüm test bölümlerinin KP sürekliliği (`Section[i].end_kp == Section[i+1].start_kp`) tam zincir olarak başarıyla doğrulanmıştır.
