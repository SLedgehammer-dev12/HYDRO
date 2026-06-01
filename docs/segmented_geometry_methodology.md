# Segmentli Geometri Metod Notu

## Kapsam

Bu doküman, NGTL 5007 hidrostatik test sartnamesinde tanımlanan formüllerin
farklı et kalınlığına sahip boru segmentlerinden oluşan test bölümlerine
nasıl uygulandığını açıklar.

## Arka Plan

NGTL 5007 Madde 13 ve 15'te tanımlanan formüller tek bir `ri` (iç yarıçap)
ve `s` (et kalınlığı) değeri varsayar:

**Hava İçerik Testi (Madde 13):**
```
Vp = ((0.884 × ri / s) + A) × 10^-6 × Vt × K
```

**Basınç Değişim Testi (Madde 15):**
```
dP = (B × dT) / ((0.884 × ri / S) + A)
```

## Problem

Gerçek saha uygulamalarında, bir test bölümü farklı et kalınlıklarına sahip
birden fazla boru segmentinden oluşabilir. Bu durumda formüllerde kullanılacak
tek bir `ri` ve `s` değeri belirsizdir.

## Uygulanan Yöntem

### Hacim Ağırlıklı Ortalama

Kod tabanı, her segment için elastisite terimini (`0.884 × ri / s`) ayrı ayrı
hesaplar ve bunları **iç hacim ağırlıklı ortalama** ile indirger:

```python
# hidrostatik_test/domain/hydrotest_core.py
@property
def elasticity_term(self) -> float:
    total_volume = self.internal_volume_m3
    return sum(
        section.elasticity_term * section.internal_volume_m3 
        for section in self.sections
    ) / total_volume
```

### Matematiksel İfade

Segment sayısı `n`, her segment için:
- `V_i`: i. segmentin iç hacmi
- `E_i`: i. segmentin elastisite terimi = `0.884 × ri_i / s_i`

**Toplam elastisite terimi:**
```
E_eff = Σ(E_i × V_i) / Σ(V_i)
```

**Efektif iç yarıçap:**
```
ri_eff = Σ(ri_i × V_i) / Σ(V_i)
```

## Varsayımlar

1. Her segment silindirik geometriye sahiptir
2. Segmentler arası geçişlerde ani çap değişimi ihmal edilir
3. Basınç tüm test bölümünde homojen dağılır
4. Sıcaklık tüm test bölümünde homojen kabul edilir

## Limitasyonlar

1. **Sartname Uyumu:** NGTL 5007 doğrudan bu indirgeme yöntemini tanımlamaz
2. **Kritik Projeler:** Yüksek basınç veya kritik uygulamalarda bu yaklaşım
   için kurum içi onay gerekebilir
3. **Çok Uzun Segmentler:** 20 km üzeri test bölümlerinde basınç düşüşü
   etkileri ihmal edilmiştir

## Doğrulama

Yöntem, aşağıdaki senaryolar için doğrulanmıştır:

1. Tek segment (baseline)
2. İki segment: aynı OD, farklı WT
3. Üç segment: farklı OD ve WT kombinasyonları

Test sonuçları `tests/test_hydrotest_core.py` dosyasında
`PipeSectionTests.test_segmented_geometry_aggregates_length_volume_and_elasticity`
testinde görülebilir.

## Örnek Hesaplama

**Girdi:**
- Segment 1: OD=406.4 mm, WT=8.74 mm, L=500 m
- Segment 2: OD=406.4 mm, WT=12.7 mm, L=500 m

**Hesaplama:**
```
Segment 1:
  ri_1 = (406.4/2) - 8.74 = 194.46 mm
  V_1 = π × (0.19446)² × 500 = 59.399 m³
  E_1 = 0.884 × 194.46 / 8.74 = 19.665

Segment 2:
  ri_2 = (406.4/2) - 12.7 = 190.50 mm
  V_2 = π × (0.19050)² × 500 = 56.985 m³
  E_2 = 0.884 × 190.50 / 12.7 = 13.268

Toplam:
  V_total = 59.399 + 56.985 = 116.384 m³
  E_eff = (19.665 × 59.399 + 13.268 × 56.985) / 116.384 = 16.538
  ri_eff = (194.46 × 59.399 + 190.50 × 56.985) / 116.384 = 192.52 mm
```

## Kurum İçi Onay Şablonu

```
Proje: [Proje Adı]
Test Bölümü: [Bölüm Tanımı]
Tarih: [YYYY-AA-GG]
Hazırlayan: [İsim]

Segment Sayısı: [n]
Toplam Uzunluk: [L] m
Toplam İç Hacim: [V] m³

Efektif İç Yarıçap: [ri_eff] mm
Efektif Elastisite Terimi: [E_eff]

Onay:
[ ] Yöntem anlaşıldı ve kabul edildi
[ ] Kritik proje değil / Ek önlem gerekmiyor
[ ] Sonuçlar bağımsız kontrol ile doğrulandı

İmza: _______________
```

## Referanslar

- NGTL 5007 R4 Hidrostatik Test ve İçten Denetleme Şartnamesi
- ASME B31.8 Gas Transmission and Distribution Piping Systems
- API 5L Specification for Line Pipe
