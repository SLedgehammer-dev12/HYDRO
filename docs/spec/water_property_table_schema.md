# Water Property Table Schema

## Kapsam

Bu sema, `A` ve `beta_water` icin dagitima uygun `table/interpolation backend`
tabanini tanimlar.

## Aralik

- Sicaklik: `0-40 degC`
- Basinc: `1-150 bar`
- Grid adimi: `1 degC x 1 bar`
- Toplam nokta: `41 x 150 = 6150`

## CSV Kolonlari

```text
temp_c,pressure_bar,a_micro_per_bar,water_beta_micro_per_c
```

Kolon anlamlari:

- `temp_c`: tablo sicakligi, birim `degC`
- `pressure_bar`: tablo basinci, birim `bar`
- `a_micro_per_bar`: suyun izotermal sikistirilabilirligi, birim `10^-6 / bar`
- `water_beta_micro_per_c`: suyun hacimsel genlesme katsayisi, birim `10^-6 / degC`

## Satir Sirasi

- CSV satirlari once `temp_c`, sonra `pressure_bar` artan sirada tutulur.
- Her sicaklik satiri icin `1..150 bar` araligi eksiksiz yer alir.

## Metadata Dosyasi

CSV yaninda `water_property_table_v1.meta.json` bulunur. Bu dosya:

- schema surumunu
- table key bilgisini
- eksen sinirlarini ve adimlarini
- interpolasyon yontemini
- tabloyu dolduran backend bilgisini
- uretim zamanini
- satir sayisini
- dagitim notlarini

tasir.

## Runtime Kural

- `table_v1` backend sadece CSV + metadata okur.
- `A` ve `beta_water` bu grid uzerinden `bilinear interpolation` ile uretilir.
- `B` tabloya yazilmaz; runtime'da `beta_water - celik alpha` olarak hesaplanir.
- `0-4 degC` civarinda `beta_water` fiziksel olarak negatif olabilir; tablo bu degeri saklar.
- `0 degC` alt sinirinda kaynak backend erime egirisine takilirsa tablo uretimi en yakin
  gecerli sivi noktadan kucuk pozitif sicaklik kaydirma ile veri alir.

## Uretim Yolu

Varsayilan offline uretim komutu:

```powershell
python tools/generate_water_property_table.py
```

Bu komut baslangic gridini mevcut `coolprop` backend'i ile doldurur ve
runtime backend'in kullanacagi dosyalari uretir.
