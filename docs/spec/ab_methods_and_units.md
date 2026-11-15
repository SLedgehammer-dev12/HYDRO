# NGTL 5007 A/B Katsayilari: Fiziksel Yontem, Birimler ve Kaynak Secimi

**Kapsam:** NGTL 5007 hidrostatik test sartnamesindeki `A` ve `B` katsayilarinin
fiziksel tanimi, birim boyutu, sayisal dogrulugu, kaynak secimi ve bilinen
`7 degC / 90 bar` A anomalisinin calisma zamaninda onarimi.

**Durum:** Arastirma + dokuman. Bu calismada hicbir kod veya veri dosyasi
degistirilmedi. Sayisal sonuclar `CoolProp 7.2.0` (IAPWS-95) ve
`iapws 1.5.5` ile 2026-11-15 tarihinde uretildi; kullanilan repo surumu
`fix/audit-remediation` dalidir.

**Ilgili dosyalar:**

- `docs/spec/ngtl_5007_raw_extract.txt` (madde 13 ve 15.2)
- `docs/spec/ngtl_5007_hydrostatic_analysis.md`
- `docs/spec/ngtl_5007_validation.md`
- `docs/spec/formula_source_map.md`
- `docs/spec/public_ab_source_comparison.md`
- `hidrostatik_test/domain/hydrotest_core.py`
- `hidrostatik_test/domain/water_properties.py`
- `hidrostatik_test/domain/coefficient_sources.py` (paralel uygulama)
- `hidrostatik_test/data/ab_control_table.py`
- `hidrostatik_test/data/botas_reference_table.py`
- `hidrostatik_test/data/gail_reference_table.py`

---

## 1. Yonetici Ozeti ve Net Oneriler

1. **A'nin birimi `1/bar`'dir; formulde `10^-6/bar` (micro/bar) olarak
   kullanilmalidir.** Sartnamenin 13. maddesindeki `(1/K)` ifadesi basim
   hatasidir. Ayni sartnamenin 15.2 maddesi `(1/bar)` der; boyut analizi de
   yalnizca `1/bar` ile sonucun `m3` cikacagini gosterir. Mevcut kod
   (`micro_per_bar`) dogrudur.

2. **B hacimseldir; celik tarafi lineer `alpha` degil, hacimsel terim
   olmalidir.** `B = beta_su - alpha_celik` (lineer) fiziksel olarak
   yanlistir ve tablolardan 20-35 micro/K sapar. Varsayilan
   `B = beta_su - 3*alpha_celik` kurum ici tabloya ortalama 4.8 micro/K,
   GAIL tablosuna 3.8 micro/K yaklasir. Bu, lineer modelin 22-25 micro/K
   hatasina gore yaklasik 5 kat iyilesmedir. Tutulmus boru icin mekanik
   alternatif `2*(1+nu)*alpha = 2.6*alpha`'dir; kurum ici tabloda MAE'de
   cok az daha iyi, GAIL'de belirgin kotudur ve muhendislik onayi
   gerektirir (bkz. 3.1).

3. **Otomatik model icin varsayilan: `B = beta - 3*alpha`, `alpha = 12 micro/K`.**
   Sicakliga bagli `3*alpha(T)` modeli kurum ici tabloda MAE'yi 4.80'den
   4.37'ye dusurur, fakat GAIL'de 3.80'den 4.68'e cikarir ve 2-10 degC
   araliginda kotulestirir. Bu nedenle `3*alpha(T)` varsayilan degil,
   opsiyonel bir duyarlilik modeli olmalidir.

4. **Varsayilan kaynak kurum ici A/B kontrol tablosudur.** GAIL ve otomatik
   model ikincil/karsilastirma kaynagidir. Secilen kaynak raporda zorunlu
   satir olarak gorunmelidir; kaynak sessizce degistirilememelidir.

5. **7 degC anomalisi gercektir ve onarilmalidir.** Etkilenen bant
   `P=81-100 bar` (20 hucre; anlamli bozulma `81-99`), tepe sapma
   `P=90 bar`'da `-3.41%` (komsu satir ortalamasina gore) ve `-4.06%`
   (IAPWS-95'e gore). Ayni T satirinda `80` ve `101 bar` capalari arasinda
   lineer kopru, sapmayi `0.01 micro/bar` altina indirir. Mevcut uygulama
   bunu yapiyor; ham CSV degismiyor, B etkilenmiyor.

6. **Olcum belirsizligi kaynak farkindan buyuktur.** `0.5 degC` sicaklik
   belirsizligi yaklasik `0.5 bar` teorik basinc belirsizligi uretir; bu,
   `0.3 bar` kabul esiginin uzerindedir. B kaynaklari arasindaki 4-5 micro/K
   fark ise 1 K icin yaklasik `0.07 bar` yapar. Bu nedenle once sicaklik
   olcum zinciri iyilestirilmeli, sonra B kaynagi tartisilmalidir.

---

## 2. Sembolik Birim Analizi

### 2.1 Sartnamedeki ifadeler

Ham metin (`ngtl_5007_raw_extract.txt`):

- Madde 13, satir 350:
  `Vp = ((0,884 x ri / s) + A) x 10^-6 x Vt x K`
- Madde 13, satir 356:
  `A : ... suyun izotermal sıkıştırılabilirliği (1/K)`
- Madde 15.2, satir 395:
  `dP = (B x dT) / ((0,884 x ri / S) + A)`
- Madde 15.2, satir 400-401:
  `B : ... suyun termal genleşmesinin çeliğin termal genleşmesiyle farkı (1/K)`
- Madde 15.2, satir 409-410:
  `A : ... suyun tahmin edilen izotermal sıkıştırılabilirliği (1/bar)`

Ayni dokumanin iki bolumu A icin farkli birim veriyor. Fiziksel tanim
"izotermal sikistirilabilirlik" oldugu icin dogru birim `1/bar`'dir;
`1/K` bir hacimsel genlesme katsayisinin birimidir ve B'ye aittir. 13.
maddedeki `(1/K)` ifadesi, 15.2'deki `(1/bar)` ile celisen bir yazim
hatasidir. **Her iki formulde de (Vp ve dP) A ayni katsayidir ve `1/bar`
(uygulamada micro/bar) olarak girilir; `1/K` versiyonu hicbir formulde
kullanilamaz.**

### 2.2 `0.884*ri/s` teriminin birimi

`ri` ve `s` ayni birimde (mm) oldugu icin `0.884*ri/s` saf sayidir
(dimensionless). Ancak formuldaki rolu, celigin **birim basinc altinda
hacimsel kompliyansi**dir. Ince cidarli, eksenel olarak tutulmus bir boru
icin:

```text
epsilon_s = (2*ri/s) * (1 - nu^2) / E        [1/bar]
```

`E = 2.06e6 bar`, `nu = 0.3` ile:

```text
epsilon_s * 1e6 = 2 * 0.91 / 2.06e6 * 1e6 * (ri/s)
                = 0.8835 * (ri/s)
```

Yani sartnamedeki `0.884` katsayisi, `E ~= 206 GPa` ve `nu = 0.3` icin
`2*(1-nu^2)/E`'nin micro/bar cinsinden degeridir. Bu, `0.884*ri/s`'in
sayisal olarak **micro/bar** mertebesinde oldugunu gosterir:

```text
0.884 * ri/s = 19.668...   (16" OD, s=8.74 mm icin)
```

Bu terim tek basina `m3` uretmez; `10^-6` carpani ile `1/bar`'a cevrilir.
Dolayisiyla:

```text
epsilon_s [1/bar] = 0.884 * (ri/s) * 1e-6
```

### 2.3 `Vp` denkleminin boyutu

```text
Vp = (0.884*ri/s + A) * 1e-6 * Vt * P * K
```

Boyutlar:

- `0.884*ri/s`: sayi, fakat formuldaki sayisal degeri micro/bar.
- `A`: `1/bar`; ayni parantezde toplanabilmesi icin `A_micro = A[1/bar]*1e6`
  olarak girilmelidir.
- `1e-6`: `1/bar`'a cevrim (micro -> 1).
- `Vt`: `m3`.
- `P`: `bar`.
- `K`: boyutsuz.

Sonuc:

```text
[(micro/bar) * (1/bar cevrimi)] * m3 * bar = m3
```

**A'nin micro/bar olarak kullanilmasi matematiksel olarak zorunludur.**
Alternatif olarak denklem su sekilde de yazilabilir:

```text
Vp = (0.884*ri/s * 1e-6 + A[1/bar]) * Vt * P * K
```

Bu ikinci yazimda `0.884*ri/s` terimi acikca `1/bar` boyutuna sokulur ve
`A` da `1/bar` olarak girilir. Iki yazim sayisal olarak aynidir; fark,
birim etiketidir. Sartname birinci yazimi kullandigi icin `A_micro`
konvansiyonu zorunlu hale gelir.

**A `1/K` olsaydi:** parantez `sayi + 1/K` olurdu; `P` ile carpim `bar/K`
uretirdi, `Vt` ile carpim `m3*bar/K` olurdu; `Vp` hacim cikmazdi. Bu nedenle
13. maddedeki `(1/K)` ifadesi uygulanabilir degildir.

### 2.4 `dP` denkleminin boyutu

```text
dP = (B * dT) / (0.884*ri/S + A)
```

Micro birimlerle:

- `B_micro`: `1e-6/K` (micro/K)
- `dT`: `K`
- `A_micro`: `1e-6/bar` (micro/bar)
- `0.884*ri/S`: micro/bar mertebesinde sayi

```text
dP = (B_micro * dT) / (0.884*ri/S + A_micro)
   = [(1e-6/K) * K] / (1e-6/bar)
   = 1e-6 / 1e-6 * bar
   = bar
```

`1e-6` pay ve paydada ayni oldugu icin sadelesir. Bu, micro konvansiyonunun
`dP` formulunde de tutarli oldugunu gosterir: **B micro/K, A micro/bar
alindiginda sonuc bar'dir.** Eger B `1/K` (65e-6) ve A micro/bar (45)
karistirilirsa sonuc `1e-6 bar` mertebesinde cikar; yani 6 buyukluk mertebesi
hata yapilir.

SI yazimi:

```text
dP[bar] = B[1/K] * dT[K] / (A[1/bar] + 0.884*ri/S * 1e-6[1/bar])
```

Bu, micro yazimla ayni sonucu verir; cunku pay ve payda ayni `1e-6` ile
olceklenmistir.

### 2.5 Sayisal ornek (16" OD, s=8.74 mm)

Girdiler:

- `OD = 406.4 mm`, `s = 8.74 mm`
- `ri = 406.4/2 - 8.74 = 194.46 mm`
- `Vt = 118.798357 m3` (1000 m uzunluk)
- `A = 45 micro/bar`
- `B = 65 micro/K`
- `P = 1 bar`, `dT = 1 K`, `K = 1.00`

El hesabi:

```text
0.884*ri/s = 0.884 * 194.46 / 8.74 = 19.668494
parantez   = 19.668494 + 45 = 64.668494  (micro/bar)

Vp = 64.668494 * 1e-6 * 118.798357 * 1 * 1
   = 0.007682511 m3
   = 7.682511 L

dP = 65 * 1 / 64.668494
   = 1.005126 bar
```

Kod ile karsilastirma (`evaluate_air_content_test`,
`evaluate_pressure_variation_test`):

```text
Vp_kod = 0.0076825108912622255 m3
dP_kod = 1.0051262322483137 bar
```

Fark: `Vp` icin `~5e-13 m3`, `dP` icin `~1e-16 bar`; yani ayni sonuc.
Kodun `elasticity_term` degeri `19.6684942791762`, `internal_volume_m3`
degeri `118.79835732832362`'dir.

Kabul siniri ve marj:

```text
Vp_kabul = 1.06 * Vp = 0.008143462 m3
marj     = 0.000460951 m3 = 0.461 L
```

### 2.6 A'nin CoolProp/IAPWS'ten alinmasi ve `1e6` cevrimi

CoolProp `ISOTHERMAL_COMPRESSIBILITY` ciktisi `1/Pa`'dir. Donusum:

```text
1/Pa -> 1/bar:  x 1e5   (1 bar = 1e5 Pa)
1/bar -> micro/bar: x 1e6
toplam: x 1e11
```

`water_properties.py` icindeki
`MICRO_BAR_INVERSE_PER_PA_INVERSE = 1e11` sabiti tam olarak bunu yapar.
Ornek (20 degC, 50 bar):

```text
kappa_T = 4.531748563556084e-10 1/Pa
A = 4.531748563556084e-10 * 1e11 = 45.3174856 micro/bar
```

Kontrol: `1 / (2.207e9 Pa) ~= 4.53e-10 1/Pa`; suyun bulk modulu
mertebesiyle uyumludur. `45.3 micro/bar = 4.53e-5 1/bar`; 100 bar'da
hacimce `%0.453` sikisma demektir. Bu fiziksel olarak dogrudur.

**Sonuc:** A'yi `1/bar` olarak alip `1e6` ile micro/bar'a cevirmek
dogrudur; mevcut kodun `1e11` carpani da bu cevrimin eksiksiz halidir.
`1/K` yorumu ne fiziksel tanima ne de boyuta uyar.

---

## 3. B'nin Fiziksel Tanimi: Lineer mi, Hacimsel mi?

### 3.1 Tanimlar

- Suyun izobarik hacimsel genlesme katsayisi:

```text
beta = (1/V) * (dV/dT)_P = -(1/rho) * (drho/dT)_P    [1/K]
```

- Celigin lineer genlesme katsayisi `alpha` [1/K].
- Izotropik, serbest celik icin hacimsel genlesme:

```text
beta_celik = 3*alpha
```

- Eksenel olarak tam tutulmus (gomulu/ankrajli) boru icin, Poisson etkisiyle
  radyal genlesme `(1+nu)*alpha` olur; hacimsel karsiligi:

```text
beta_celik,tutulmus = 2*(1+nu)*alpha = 2.6*alpha   (nu=0.3)
```

Sartname "suyun termal genlesmesinin celigin termal genlesmesiyle farki"
diyor; lineer/hacimsel ayrimi yapmiyor. Bu yuzden dogru yorumu tablolar ve
formulun yapisi belirler.

**Onemli gozlem:** `0.884*ri/s` terimi, eksenel tutulmus ince cidarli boru
icin `2*(1-nu^2)/E` ile birebir uyusur (bkz. 2.2). Bu, formuldaki elastik
terimin "tutulmus boru" varsayimina dayandigini **kuvvetle dusundurur**.
Ancak alternatif bir yorum da mumkundur: `0.884 = 2/E` kabul edilirse
`E ~= 226 GPa` (tipik 206 GPa'dan yuksek) ve serbest boru/`3*alpha`
tutarli olur. Sartnamenin hangi yorumu kastettigi acik degildir; bu
nedenle asagidaki karsilastirma ampirik tablolara dayandirilmalidir.
Tutulmus boru yorumunda mekanik olarak tutarli karsilik `2.6*alpha`
olurdu. Sayisal olarak `2.6*alpha`, kurum ici
tabloda MAE'de (4.29) `3*alpha`'dan (4.80) cok az daha iyidir; ancak GAIL'de
belirgin sekilde kotudur (6.19 vs 3.80) ve maksimum hatasi daha buyuktur
(14.50 vs 9.70). Iki tablo birlikte degerlendirildiginde ve standart
varsayim olarak `3*alpha` secilir; `2.6*alpha` muhendislik onayi ile
opsiyonel sunulmalidir. Bu celiski, sartnamenin kendi icinde cozulmemis bir
varsayim farkidir.

### 3.2 Dort referans noktada sayisal karsilastirma

Asagidaki tabloda:

- `beta`: CoolProp IAPWS-95, micro/K.
- `A_CP`: CoolProp izotermal sikistirilabilirlik, micro/bar.
- `A_tab`, `B_tab`: kurum ici A/B kontrol tablosu (ham).
- `A_gail`, `B_gail`: GAIL referans tablosu (bilinear).
- `b-a`: `beta - 12`.
- `b-3a`: `beta - 36`.
- `b-3a(T)`: `beta - 3*(10.8 + 0.012*T)`.

| T (degC) | P (bar) | beta | A_CP | A_tab | B_tab | A_gail | B_gail | b-a | b-3a | b-3a(T) | hata b-a | hata b-3a | hata b-3a(T) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 50 | -15.67 | 49.469 | 49.005 | -59.45 | 48.992 | -63.84 | -27.67 | -51.67 | -48.14 | +31.78 | +7.78 | +11.31 |
| 10 | 50 | 99.62 | 47.193 | 46.775 | 64.92 | 46.824 | 60.45 | 87.62 | 63.62 | 66.86 | +22.70 | -1.30 | +1.94 |
| 20 | 100 | 221.15 | 44.744 | 44.421 | 191.43 | 44.443 | 186.80 | 209.15 | 185.15 | 188.03 | +17.72 | -6.28 | -3.40 |
| 25 | 30 | 260.50 | 44.911 | 44.620 | 232.59 | 44.640 | 227.80 | 248.50 | 224.50 | 227.20 | +15.91 | -8.09 | -5.39 |

Hata sutunlari **kurum ici B_tab'e gore** micro/K farktir.

Yuzde olarak (kurum ici / GAIL):

| Nokta | b-a | b-3a | b-3a(T) |
|---|---:|---:|---:|
| 2 degC / 50 bar | +53.5% / +56.7% | +13.1% / +19.1% | +19.0% / +24.6% |
| 10 degC / 50 bar | +35.0% / +45.0% | -2.0% / +5.3% | +3.0% / +10.6% |
| 20 degC / 100 bar | +9.3% / +12.0% | -3.3% / -0.9% | -1.8% / +0.7% |
| 25 degC / 30 bar | +6.8% / +9.1% | -3.5% / -1.4% | -2.3% / -0.3% |

**Yorum:**

- `beta - alpha` her noktada belirgin sekilde yuksek; 10 degC'de %35,
  2 degC'de %53 hata. Lineer model kullanilamaz.
- `beta - 3*alpha` 10-25 degC araliginda her iki tabloya da %5'in altinda
  yaklasir. 2 degC'de yuzde buyuktur cunku `B` sifira yakindir; mutlak
  fark 7.8 micro/K'dir ve yuzde gostergesi yanilticidir.
- `beta - 3*alpha(T)` 20-25 degC'de kurum ici tabloya daha yakindir, fakat
  2-10 degC'de daha kotudur.

### 3.3 Tum izgara uzerinde hata istatistigi

Karsilastirma, kurum ici tablonun `T=1-25 degC`, `P=30-120 bar`
(2275 nokta) ve GAIL tablosunun `T=2-30 degC`, `P=30-120 bar`
(150 nokta) izgarasinda yapildi. Hata: `model B - tablo B`, micro/K.

| Model | Kurum ici MAE | Kurum ici max | Kurum ici APE* | GAIL MAE | GAIL max | GAIL APE* |
|---|---:|---:|---:|---:|---:|---:|
| `beta - alpha` (alpha=12) | 22.16 | 33.70 | 18.69% | 25.39 | 36.41 | 19.15% |
| `beta - 2*alpha` | 10.16 | 21.70 | - | 13.39 | 24.41 | - |
| `beta - 2.6*alpha` | 4.29 | 14.50 | - | 6.19 | 17.21 | - |
| **`beta - 3*alpha` (alpha=12)** | **4.80** | **9.70** | **3.92%** | **3.80** | **12.41** | **2.59%** |
| `beta - 3*alpha(T)` | 4.37 | 13.26 | 3.25% | 4.68 | 15.94 | 3.63% |

\* APE yalnizca `|B_tab| > 50 micro/K` olan noktalarda hesaplandi; `B` sifira
yakinken yuzde patlar. MAE ve max tum noktalar icindir.

`T >= 5 degC` alt kumesinde (soguk su uc noktalari haric):

| Model | Kurum ici MAE | Kurum ici max | GAIL MAE | GAIL max |
|---|---:|---:|---:|---:|
| `beta - alpha` | 20.44 | 27.81 | 23.93 | 31.04 |
| **`beta - 3*alpha`** | **4.35** | **8.09** | **2.72** | **7.04** |
| `beta - 3*alpha(T)` | 3.17 | 7.23 | 3.20 | 10.42 |

**Sonuc:** `3*alpha` hipotezi, `alpha` hipotezine gore 4.5-6 kat daha
iyidir. `3*alpha(T)` kurum ici tablonun orta-sicaklik bolgesinde biraz daha
iyidir, fakat GAIL'de ve soguk bolgede daha kotudur; robust bir kazanc
degildir.

### 3.4 Tablolarin "etkin alpha"si ve su ozelligi farki

`k(T) = beta(T,P) - B_tab(T,P)` tanimlayalim. Eger tablo `B = beta - 3*alpha`
ile uretilseydi `k = 3*alpha` sabit (alpha=12 icin 36) olurdu. Gercek durum
(P=50 bar, kurum ici / GAIL):

| T (degC) | beta | B_kurum | B_GAIL | k_kurum | k_GAIL | k_kurum/3 | k_GAIL/3 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | -15.67 | -59.45 | -63.84 | 43.78 | 48.17 | 14.59 | 16.06 |
| 6 | 45.32 | 6.79 | 2.36 | 38.53 | 42.96 | 12.84 | 14.32 |
| 10 | 99.62 | 64.92 | 60.45 | 34.70 | 39.17 | 11.57 | 13.06 |
| 15 | 160.06 | 128.62 | 123.92 | 31.44 | 36.14 | 10.48 | 12.05 |
| 20 | 213.97 | 184.56 | 179.93 | 29.42 | 34.04 | 9.81 | 11.35 |
| 25 | 262.71 | 234.53 | 229.72 | 28.18 | 32.98 | 9.39 | 10.99 |

Iki onemli cikarim:

1. **Tablolar arasi fark sabittir:** `B_kurum - B_GAIL` orneklenen
   `2-24 degC / 30-120 bar` izgarasinda `3.45-4.90 micro/K`, ortalama
   `4.51 micro/K`. Bu, `3*(alpha_GAIL - alpha_kurum)` farkina karsilik gelir;
   yani yaklasik `1.2-1.6 micro/K` celik alpha farki. En kucuk kareler
   tahmini: kurum ici `alpha ~= 10.8`, GAIL `alpha ~= 12.0` (T>=5 icin).
   `public_ab_source_comparison.md`'deki "farkli celik genlesme varsayimi"
   cikarimi bu sekilde sayisal olarak dogrulanir.

2. **Tablolarin su terimi IAPWS-95'ten kayar:** `k(T)` sabit degil,
   43.8'den 28.2'ye dusuyor. Sabit bir `alpha` ile bu egilim aciklanamaz.
   Tablolarin su `beta`'si, IAPWS-95'e gore sicakliga bagli bir sapma
   tasiyor; en buyuk sapma 4 degC civarinda (beta sifira yakin oldugu icin
   yuzde olarak buyuk) ve 20-25 degC'de `%1-2` mertebesinde. Bu, eski/kolon
   bazli su property tablolarindan veya grafik dijitizasyonundan gelen bir
   fark olabilir; **kesin nedeni bu calismada dogrulanamadi.**

Basinc egimi kontrolu: kurum ici B, 20 degC'de 30->120 bar arasinda
`0.137 micro/K/bar` egimle degisiyor; CoolProp `beta` egimi
`0.144 micro/K/bar`. Yani tablo, suyun basinca bagliligi dogru mertebede
tasiyor; fark basinc ekseninde degil, sicaklik/olcek tarafinda.

### 3.5 `alpha(T)` modeli neden varsayilan olmamali?

Onerilen model `alpha(T) = 10.8 + 0.012*T` (micro/K):

| T (degC) | alpha(T) | 3*alpha(T) |
|---:|---:|---:|
| 2 | 10.824 | 32.47 |
| 10 | 10.920 | 32.76 |
| 20 | 11.040 | 33.12 |
| 25 | 11.100 | 33.30 |

Fiziksel olarak karbon celigi icin alpha sicaklikla **artar**; bu model de
artiriyor. Ancak tablolarin davranisi tersini ima ediyor: etkin alpha
`14.6`'dan `9.4`'e **dusuyor** (3.4 tablosu). Bu nedenle `alpha(T)`,
tablolarin su-terimi sapmasini telafi etmek icin "yanlis yonde" calisiyor:
20-25 degC'de iyilestiriyor, 2-10 degC'de kotulestiriyor. Kurum ici MAE
4.80 -> 4.37 (kazanc 0.43), GAIL 3.80 -> 4.68 (kayip 0.88). Robust degil.

Ayrica `alpha(T)` modeli, `alpha(20) = 11.04 micro/K` ile tipik karbon
celigi degerinin (`~11.7 micro/K`) altinda kalir. Bu, modelin bir
"kalibrasyon" oldugunu, yeni bir fiziksel dogruluk olmadigini gosterir.

### 3.6 B icin oneri

**Otomatik model varsayilani:**

```text
B = beta_su(T,P) - 3*alpha_celik
alpha_celik = 12.0 micro/K  (varsayilan)
```

Gerekce:

- B hacimsel bir farktir; celik tarafi `3*alpha`'dir.
- Kurum ici ve GAIL tablolarina en yakin basit model budur (MAE 4.8 / 3.8;
  lineer modelde 22 / 25).
- `alpha=12`, GAIL'in etkin degerine (`~12.0`) ve tipik karbon celigi
  araligina (`10.8-12.5`) yakindir.
- `3*alpha(T)` opsiyonel kalmali; varsayilan yapilmasini hakli kilacak
  tutarli bir kazanc yok.

**Opsiyonel kalibrasyon:** Kurum ici tabloya daha yakin bir otomatik model
istenirse `alpha = 10.8` (veya T>=5 icin en kucuk kareler `10.81`)
kullanilabilir; bu, "fiziksel model" degil "kurum ici tabloya kalibre
model" olarak etiketlenmelidir. `alpha=10.8` ile 20-25 degC'de hata
azalir, 10 degC'de artar; tek bir sabit ile her nokta tutturulamaz.

**Eski raporla mutabakat:** `docs/remediation_report.md` "otomatik
`beta - alpha`, kurum ici tablo ve GAIL arasinda %26-45 fark" diyor. Bu
ifade lineer `beta - alpha` modeline aittir. `3*alpha` varsayilani ile
otomatik model-kurum ici fark tipik olarak `1-8 micro/K` (ortalama
`4.8`, cogu noktada `<%4`) olur; 2 degC civarinda `B` sifira yakin
oldugu icin yuzde buyur. Yani 3*alpha gecisi, eski rapordaki buyuk farkin
buyuk kismini giderir.

---

## 4. Kaynak Secimi

### 4.1 Uc kaynagin karsilastirmasi

| Kaynak | Guclu yon | Zayif yon | Izlenebilirlik | Belirsizlik (gecici) |
|---|---|---|---|---|
| **Kurum ici A/B kontrol tablosu** (`ab_control_table_v1.csv`, varsayilan) | Resmi/kurumsal; 1 degC x 1 bar yogun izgara; 1-25 degC, 30-120 bar; saha pratigiyle uyumlu | Kaynagi kapali workbook; 7 degC A anomalisi; GAIL'e gore ~4.5 micro/K yuksek; yayinlanmis belirsizlik yok | `A ve B Katsayisi.xlsx` -> CSV + meta; hucresel provenance yok | ~5 micro/K (tablo-otomatik farkindan turetilmis, resmi degil) |
| **GAIL referans tablosu** (`gail_reference_table_v1.csv`) | Kamuya acik, bagimsiz; B exact 10 bar dugumlerinde; A grafik dijitizasyonu; 2-30 degC | 2 degC / 10 bar kaba izgara (bilinear); A tahmini; kurum onayi yok; T=1 kapsam disi, 25-30 degC 2 degC izgara (25 tam dugum degil) | GAIL-STD-PL-DOC-TS-012 Table-1 + Fig.1; CSV/meta mevcut | ~5 micro/K (A icin ~%0.6-1.2) |
| **Otomatik fiziksel model** | Surekli T/P; formulu seffaf; IAPWS-95'e dayali; tablo bosluklari yok; duyarlilik analizine uygun | Tablolari tam tutturamiyor (MAE ~4-5, max ~10-13 micro/K); `alpha` ve su property basisine duyarli; resmi onay yok | IAPWS-95 + CoolProp + `alpha` modeli; her adim loglanabilir | ~5 micro/K (model-tablo farki); `beta` belirsizligi < %0.5 |

Not: Kurum ici tablo ile GAIL arasindaki fark, `2-24 degC` ortak
izgarasinda `|dB| = 3.45-4.90 micro/K` (ortalama 4.51). Bu sistematik fark,
"iki tablo ayni aile ama ayni veri degil" tespitiyle uyumludur.

### 4.2 Kullaniciya sunum

Tek bir **"B kaynagi"** secici:

1. `Kurum ici A/B tablosu (varsayilan)` -> `BSource.INSTITUTIONAL`
2. `GAIL referans tablosu (karsilastirma)` -> `BSource.GAIL`
3. `Otomatik model: beta - 3*alpha` -> `BSource.AUTO`

Kurallar:

- Yeni testte varsayilan **her zaman** kurum ici kaynaktir; onceki secim
  sessizce yeni teste tasinmamalidir. Secim test bazinda kaydedilir.
- Secilen kaynak, kaynak etiketi, T/P, A ve B degerleri, provenance ve
  varsa onarim notu **raporda zorunlu** satirlar olarak yer alir. Ornek:

```text
B kaynagi : Kurum ici A/B kontrol tablosu (institutional)
T/P       : 10.0 degC / 50.0 bar
A         : 46.775 x10^-6/bar  (exact grid)
B         : 64.923 x10^-6/K    (exact grid)
A onarimi : yok
Kaynak farki: GAIL dB = +4.47 (+6.9%) | Otomatik dB = -1.30 (-2.0%)
```

- GAIL secildiginde kapsam disi T/P icin **ekstrapolasyon yapilmaz**;
  "kapsam disi" hatasi verilir ve kurum ici kaynaga donus onerilir.
- Otomatik model secildiginde `beta`, `alpha`, `steel_model` ve
  "tablo degeri degil" etiketi gorunur.
- A onarimi uygulanmissa `A onarildi` rozeti ve `ham -> onarilmis` degeri
  gosterilir.

### 4.3 Uyari esikleri

Oneri: iki kademeli esik.

| Kademe | Kosul | Davranis |
|---|---|---|
| Bilgi | Her zaman | Secilen kaynak ile kurum ici kaynak arasindaki `dB` ve `%` raporda gorunur |
| Yumusak uyari | `abs(dB) >= 5 micro/K` **veya** `abs(dB) / abs(B_kurum) >= %5` | Sari uyari kutusu; iki deger ve kaynak adi; kullanici devam edebilir |
| Sert uyari | `abs(dB) >= 10 micro/K` **veya** `>= %10` | Kirmizi kutu + acik onay (checkbox/dialog); rapora "kullanici onayladi" notu |

Gerekce: mevcut kurum ici-GAIL farki max `4.90 micro/K` oldugu icin
`5 micro/K` esigi normalde alarm uretmez; ancak `%5` kosulu, dusuk `B`
bolgesinde (orn. 10 degC'de `4.47/64.92 = %6.9`) devreye girer ve gercek
bir kaynak farkini gorunur kilar. Otomatik model 25 degC'de kurum ici
tablodan `~8.1 micro/K` sapabilir; bu da yumusak uyariyi tetikler.
Esikler **kaynak secimini otomatik degistirmemeli**; sadece uyarir.

---

## 5. `7 degC / 90-98 bar` A Anomalisi

### 5.1 Gercek durum

Kurum ici tabloda `T=7 degC` satirinda A, `P=80 bar`'dan `P=90 bar`'a
normalden ~17 kat hizli dusuyor (`-0.1701 micro/bar/bar`), sonra
`P=90 -> 100 bar` arasinda **artiyor** (`+0.1499 micro/bar/bar`). Bu,
fiziksel olarak beklenen yumusak, monoton azalan egilimle celisir ve
tipik bir veri girisi/transkripsiyon artefaktidir.

Sayisal olarak:

| P (bar) | A ham | A_CP (IAPWS) | Ham sapma | Komsu satir ort. (T=6/8) | Komsuya gore |
|---:|---:|---:|---:|---:|---:|
| 80 | 47.216 | 47.568 | -0.74% | 47.222 | -0.01% |
| 85 | 46.365 | 47.505 | -2.40% | 47.171 | -1.71% |
| 90 | 45.515 | 47.441 | **-4.06%** | 47.121 | **-3.41%** |
| 95 | 46.265 | 47.378 | -2.35% | 47.070 | -1.71% |
| 100 | 47.014 | 47.315 | -0.64% | 47.020 | -0.01% |
| 101 | 47.004 | 47.303 | -0.63% | 47.010 | -0.01% |

Etkilenen bant: `P=81-100` (20 hucre). Bunlardan `81-99` anlamli sekilde
bozuktur; `P=100`'de ham deger dogruya cok yakindir (`47.014` vs dogru
`47.0141`). Tepe sapma `P=90`'dadir.

Not: `remediation_report.md` "dokuz hucrede ~%4" diyor. Bu ifade merkezi
bolgeyi (yaklasik `90-98`) kastediyor olabilir; gercek bant daha genistir
ve tepe sapma IAPWS-95'e gore `%4.06`'dir. Rapor metni "20 hucre, tepe
~%4" olarak duzeltilmelidir.

B tarafi etkilenmemistir: `T=7, P=90` icin `B=32.663`; komsu satir
ortalamasi `(17.919+46.944)/2 = 32.43`; fark `+0.7%`, egilim duzgun.
Bu nedenle onarim **yalnizca A**'ya uygulanmalidir.

Ayni bant, kalite kontrolunde `T=7 -> 8` kolon karsilastirmasinda 17 adet
`a_temperature_monotonicity` bulgusu da uretir (`P=82-98`). Bunlar ayni
anomalinin yan etkisidir; A onarildiginda kaybolur ve ek bir onarim
gerektirmez.

### 5.2 Onerilen onarim: ayni satirda lineer kopru

Algoritma (mevcut `_load_ab_control_repair_grid` ile uyumlu):

1. `find_ab_control_table_issues()` ile `a_monotonicity` ve `a_step`
   bulgularini topla.
2. Her bulgu icin `(T_index, P_index)`'i isaretle.
3. Ayni T satirinda, isaretli hucrelerin bitisik bloklarini bul.
4. Her blok icin blok disindaki en yakin saglikli alt/ust komsuyu capa al.
5. Blok icindeki her hucreyi bu iki capa arasinda lineer interpolasyonla
   degistir.
6. B'ye dokunma; ham CSV'yi degistirme; maskeyi ve provenance'i sakla.

`T=7` icin capalar `P=80` (`A=47.216`) ve `P=101` (`A=47.004`):

```text
A_onarilmis(P) = 47.216 + (P-80) * (47.004-47.216)/(101-80)
               = 47.216 - 0.0100952 * (P-80)
```

Sonuclar:

- `P=90`: `47.115` (ham `45.515`; fark `+1.600`, `+3.52%`).
- `P=100`: `47.0141` (ham `47.014`; fark `+0.0001`).
- Komsu satir ortalamasina gore maksimum artakalan sapma:
  `0.006 micro/bar` (`P=81`'de); yani `%0.013`.
- IAPWS-95'e gore `P=90` sapmasi `-4.06%`'den `-0.69%`'a iner.

Onarim 20 hucreyi degistirir; bunlardan yalnizca `81-99` anlamli degisir.

### 5.3 Alternatifler ve denetim riski

| Yaklasim | Arti | Eksi / denetim riski | Oneri |
|---|---|---|---|
| **Calisma zamaninda satir ici lineer kopru** | Ham veri korunur; kucuk, sinirli, tekrarlanabilir; kolay test edilir; mevcut uygulama | "Sihirli" gorunebilir; capa secimi ve esik dokumante edilmeli; interpolation penceresine giren sorgularda provenance zorunlu | **Secilen yol** (varsayilan acik) |
| Ayri duzeltilmis turev CSV | Denetci ham ve duzeltilmis dosyayi yan yana gorur; diff alinabilir | Iki veri kaynagi birbirinden ayrisma riski; hangisinin resmi oldugu belirsizlesir; surum senkronu gerekir | Yalnizca resmi onay sonrasi; ayri `*_corrected_v1.csv` + meta + hash |
| Monotonik regresyon (isotonic) | Parametresiz; tum satiri tutarli hale getirir | Bircok hucreyi degistirir; fiziksel/muhendislik gerekcesi yok; hangi hucrenin degistigi zor izlenir; B ve A iliskisini bozabilir | Onerilmez |
| Kurum onayli yeni tablo | En yuksek otorite; kalici cozum | Tedarik/onay dongusu; gecikme | **Nihai hedef** |

**Secim:** Kisa vadede calisma zamaninda satir ici lineer kopru; ham CSV
ve B korunur; her rapor provenance tasir. Kurum onayli tablo geldiginde
onarim kapatilir, tablo surumu artirilir ve eski/yeni fark raporlanir.

### 5.4 Provenance alani onerisi

`ABControlPoint`'e (veya yeni bir `ABRepairProvenance`'a) su alanlar
eklenmeli:

```python
@dataclass(frozen=True)
class ABRepairProvenance:
    policy: str                      # "row_linear_bridge_v1"
    table_key: str                   # "ab_control_table_1_25c_30_120bar_v1"
    table_sha256: str                # ham CSV'nin hash'i (surum izi)
    cells: tuple[tuple[float, float], ...]   # onarilan (T, P) listesi
    span_bar: tuple[float, float]    # (81.0, 100.0)
    anchors: tuple[tuple[float, float], tuple[float, float]]
                                     # ((80.0, 47.216), (101.0, 47.004))
    max_abs_delta_micro_per_bar: float       # 1.600
    raw_a_micro_per_bar: float       # sorgu noktasindaki ham deger
    repaired_a_micro_per_bar: float  # sorgu noktasindaki onarilmis deger
```

Mevcut `repaired: bool` ve `repair_note: str` alanlari geriye donuk
uyumluluk icin kalabilir; yeni yapi bunlari besler. Raporda en azindan
`policy`, `span_bar`, `cells` sayisi ve `raw -> repaired` gorunmelidir.

---

## 6. Daha Iyi Bir A/B Yontemi Var mi?

### 6.1 A ve B icin referans formulasyon

- **Su tarafi:** IAPWS-95 (CoolProp varsayilani) bu aralikta referanstir.
  `A = kappa_T`, `beta = alpha_v` dogrudan analitik turev olarak alinir.
- **Celik tarafi:** `3*alpha` (serbest) veya `2*(1+nu)*alpha` (tutulmus).
  `alpha` icin tek bir "dogru" deger yoktur; karbon celigi icin
  `10.8-12.5 micro/K` araligi makuldir. Teknik kaynaklarda
  `a = 1.116e-5/degC` (Technical Toolboxes) ve `6.5e-6/degF = 11.7e-6/K`
  (Proper Pigging) degerleri geciyor.
- **Basinc/elastik terim:** `0.884*ri/s`, `E~=206 GPa`, `nu=0.3` ile
  tutulmus ince cidarli boru kompliyansidir (2.2). Formulun geri kalaninda
  da bu varsayim korunmalidir.

### 6.2 Bagimsiz capraz kontrol

Bu calismada yapilan kontrol:

| Nokta | A CoolProp (micro/bar) | A IF97 (micro/bar) | Fark | beta CoolProp (micro/K) | beta IF97 (micro/K) | Fark |
|---|---:|---:|---:|---:|---:|---:|
| 2/50 | 49.469 | 49.479 | +0.020% | -15.67 | -15.52 | -0.91% |
| 10/50 | 47.193 | 47.187 | -0.013% | 99.62 | 100.01 | +0.39% |
| 20/100 | 44.744 | 44.719 | -0.057% | 221.15 | 221.34 | +0.08% |
| 25/30 | 44.911 | 44.838 | -0.162% | 260.50 | 260.24 | -0.10% |

IF97 degerleri, `rho(T,P)` uzerinden merkezi fark ile turetildi; bu
bagimsiz bir formulasyondur (IAPWS-IF97 vs IAPWS-95), ancak sayisal
turevdir. `iapws` kutuphanesi de IAPWS-95'in bir implementasyonudur;
CoolProp ile **formulasyon olarak** bagimsiz degildir (bu nedenle
"ikinci bagimsiz backend" iddiasi icin yeterli degildir). Repo'daki
`table_v1` backend'i CoolProp'tan uretilmis bir grid'dir; dugumlerde
CoolProp ile birebir ayni oldugu icin bagimsiz kaynak sayilamaz.

**Oneri:** Runtime'da CoolProp/IAPWS-95; testlerde IF97 numerik turev
ile tolerans kontrolu (A icin `%0.2`, beta icin `%1`). NIST REFPROP
lisansi varsa, gercek ikinci bagimsiz kaynak olarak kullanilabilir.
GPL `iapws` paketi mevcut kararla dagitima girmemeli; sadece gelistirme
capraz kontrolu icin kalmalidir.

### 6.3 Tablolarin IAPWS-95 ile dogrulanmasi

- Kurum ici A: `MAPE = %0.76`, `max = %1.11` (T=7 haric); T=7 dahil
  `max = %4.06` (anomali). Bu, A tablosunun IAPWS-95 ailesiyle uyumlu
  oldugunu gosterir.
- GAIL A: `MAPE = %0.62`, `max = %1.15`.
- Kurum ici B: `beta - 3*alpha` ile `MAE = 4.80 micro/K`; tablo-otomatik
  farkin buyuk kismi su property basisi farkindan gelir (3.4).
- GAIL B: `MAE = 3.80 micro/K`.

Yani A tarafi guvenilir; B tarafinda tablolar kendi aralarinda ve
IAPWS-95'e gore birkac micro/K mertebesinde sistematik fark tasiyor.
Bu fark, 1 K icin `~0.07 bar`, 5 K icin `~0.35 bar` demektir; yani uzun
sicaklik degisimlerinde `0.3 bar` kabul esigine yaklasir. Yine de ayni
`dT` icin sicaklik olcum belirsizligi (`~0.5 bar`) daha buyuktur (6.4).

### 6.4 Olcum belirsizligi ve yuvarlama

Ornek geometri (`epsilon_s + A = 64.668 micro/bar`, `B = 65 micro/K`):

```text
d(dP)/d(dT) = B / (epsilon_s + A) = 65/64.668 = 1.005 bar/K
d(dP)/dB    = dT / (epsilon_s + A) = 1/64.668 = 0.0155 bar per micro/K
```

- `dT = +-0.5 degC` -> `dP = +-0.50 bar`. Bu, `0.3 bar` kabul
  esiginden buyuktur. **Sicaklik olcumu, B kaynagindan daha kritiktir.**
- Kaynaklar arasi `4.5 micro/K` fark, `1 K` icin `0.070 bar`;
  `5 K` icin `0.35 bar` yapar. Uzun `dT`'lerde kaynak secimi onemlidir.
- A anomalisi `1.6 micro/bar`, `Vp`'yi `%2.45` degistirir; bu, `%6`
  kabul marjinin `%41`'idir. Ornek: `Vp_onarilmis=0.007934 m3`,
  `Vp_ham=0.007744 m3`, fark `0.000190 m3 = 0.19 L`. Ham degerle
  `Vpa/Vp` orani `%2.45` fazla gorunur; `1.035` olan gercek oran
  `1.060` gorunup yanlislikla FAIL uretebilir.
- Yuvarlama: ara hesaplarda yuvarlama yapilmamali. A 3 ondalik
  (`0.001 micro/bar`), B 2 ondalik (`0.01 micro/K`) saklanabilir;
  `Vp` en az `1e-5 m3` (0.01 L), `dP` `0.001 bar` hassasiyetle
  raporlanmali. Ekranda `dP` 2 ondalik gosterilebilir; karar icin
  yuvarlanmamis deger kullanilmalidir.

### 6.5 "Daha iyi" bir yontem var mi?

Kisa cevap: **Formul degismemeli; veri ve belirsizlik yonetimi
iyilestirilmeli.** A/B yaklasimi, kapali hacimde suyun sikismasi ile
celik kompliyansini ayirmanin dogru muhendislik yoludur. Alternatif
"tek katsayili" modeller (sadece `beta`, sadece bulk modulus) celik
kompliyansini ihmal eder ve daha kotudur. Yapilabilecek iyilestirmeler:

1. A/B tablolarini IAPWS-95 ile periyodik dogrulama (regresyon testi).
2. Kurum ici tablo icin resmi bir alpha varsayimini (10.8 mi, 12.0 mi)
   ve su property basisini dokumante etmek.
3. Olcum zincirini iyilestirmek: `dT` icin `0.1 K` cozunurluk ve ayni
   zaman tabani; basinc icin dead-weight/calibrated transmitter.
4. Her raporda A/B kaynagi, onarim ve belirsizlik satiri.
5. Gerekirse `2*(1+nu)*alpha` (tutulmus boru) modelini opsiyonel sunmak;
   varsayilan `3*alpha` kalmali cunku iki tablo birlikte ve maksimum hata
   acisindan onu destekliyor.

---

## 7. Belirsizlikler ve Muhendislik Onayi Gerekenler

1. **A birimi:** Sartnamenin 13. maddesindeki `(1/K)` ifadesi icin
   yazili kurum onayi/erratum. Bu dokuman `1/bar` kabul ediyor.
2. **B celik modeli:** `3*alpha` (serbest) mi, `2*(1+nu)*alpha` (tutulmus)
   mi? `0.884` terimi muhtemelen tutulmus boruya isaret ediyor (alternatif
   `2/E` yorumu icin E~=226 GPa gerekir); iki tablo birlikte
   degerlendirildiginde `3*alpha` daha uyumlu. Kurum ici tablonun gercek
   alpha varsayimi (gorunurda ~10.8) ve su property kaynagi acik degil.
3. **Tablolarin su property basisi:** Kurum ici ve GAIL tablolarinin
   IAPWS-95'ten sicakliga bagli sapmasi (ozellikle 4 degC civari ve
   20-25 degC'de %1-2) dogrulanmadi. Tablo sahibinden formul/uretim
   notu istenmeli.
4. **7 degC onarim politikasi:** Satir ici lineer kopru icin resmi
   onay; capa secimi (`80`/`101`) ve `a_step` esigi (`0.05 micro/bar/bar`)
   dokumante edilmeli. Nihai cozum kurum onayli tablodur.
5. **Kaynak otoritesi:** Kurum ici tablo mu, GAIL mi, yoksa yeni bir
   resmi tablo mu? Bu dokuman kurum ici tabloyu varsayilan kabul ediyor.
6. **Belirsizlik degerleri:** Tablo ve model icin verilen `~5 micro/K`
   degerleri bu calismada turetilmis gecici degerlerdir; metroloji
   onayi gerekir.
7. **ASME B31.8 / B31.4:** Bu calismada standart metinlerine erisilmedi
   (paywall). NGTL 5007 ve GAIL/EIL ailesi esas alindi; ASME uyumu
   ayrica dogrulanmalidir.
8. **GAIL/BGGL URL'leri:** Bu calismada GAIL PDF URL'si HTTP 406,
   BGGL URL'si HTTP 404 dondurdu (2026-11-15). Repo icindeki extract
   CSV'leri izlenebilir artefakt olarak kullanildi; orijinal PDF'lerin
   arsiv kopyasi saklanmalidir.

---

## 8. Kaynakca

1. NGTL 5007, `4-NGTL 0-GN-P-002-5007 R4 Hidrostatik Test ve Icten
   Denetleme Sartnamesi`; repo extract: `docs/spec/ngtl_5007_raw_extract.txt`
   (madde 13: satir 342-357; madde 15.2: satir 388-416).
2. GAIL, `GAIL-STD-PL-DOC-TS-012`, Technical Volume 3 (hydrotest
   specification). Repo notu:
   `https://gailtenders.in/Gailtenders/writereaddata/Tender/technicalvol3_20240827_123931.pdf`
   (2026-11-15: HTTP 406; extract: `docs/spec/gail_*`).
3. BGGL, Vol-2 hydrotest specification:
   `https://www.bglgas.com/downloads/620-VOL-2.pdf`
   (2026-11-15: HTTP 404).
4. EIL, `Specification for Hydrostatic Testing of Onshore Pipelines`,
   Format No. EIL 1641-1924 Rev.1, Table 1 "Difference between the water
   thermal expansion factor and the steel thermal expansion factor
   (degC^-1) 10^-6". Public copies:
   `https://pdfcoffee.com/specification-of-hydro-testing-for-onshore-pdf-free.html`
   ve `https://www.scribd.com/doc/27955717/Specification-of-Hydro-Testing-for-Onshore`
   (erisim bu ortamda dogrulanamadi; baslik ve tablo tanimi arama
   sonucundan alindi).
5. APGDC, `Specification for Hydrostatic Testing of Pipelines`,
   Annexure-1 Technical:
   `https://apgdc.in/pdf/SR%203057/Annexure-1%20Technical.pdf`
   (0.884 ri/t + A formulu; erisim bu ortamda dogrulanamadi).
6. Technical Toolboxes, "Pipeline Hydrostatic Testing - Liquid":
   `https://help.technicaltoolboxes.com/knowledge-base/pipeline-hydrostatic-testing-liquid`
   (2026-11-15 erisildi). Formul:
   `dP = (B - 2a) / (D(1-nu^2)/(Et) + C)`, `a = 1.116e-5/degC`,
   `B*1e6 = -64.268 + 17.0105T - 0.20369T^2 + 0.0016048T^3`.
7. Proper Pigging, "Pressure-temperature analysis, and why half a degree
   decides the test":
   `https://properpigging.com/pressure-temperature-analysis-explained`
   (2026-11-15 erisildi). Formul:
   `dP = dT[gamma - 2(1+nu)alpha] / [(D/(Et))(1-nu^2) + C]`;
   `alpha = 6.5e-6/degF`, `E = 29e6 psi`, `nu = 0.3`.
8. IAPWS, `R6-95(2018)`: Revised Release on the IAPWS Formulation 1995
   for the Thermodynamic Properties of Ordinary Water Substance for
   General and Scientific Use:
   `https://iapws.org/relguide/IAPWS-95.html`
9. IAPWS, `R7-97(2012)`: Revised Release on the IAPWS Industrial
   Formulation 1997:
   `https://iapws.org/relguide/IF97-Rev.html`
10. NIST Chemistry WebBook, Thermophysical Properties of Fluid Systems:
    `https://webbook.nist.gov/chemistry/fluid/`
11. Bell, I.H. et al., CoolProp: `http://www.coolprop.org/`
12. "Prediction of bulk modulus and volumetric expansion coefficient of
    water for leak tightness test of pipelines", ScienceDirect:
    `https://www.sciencedirect.com/science/article/pii/S0308016109000301`
    (yalnizca metadata/abstract erisimi; tam metin bu calismada
    dogrulanmadi).
13. NBS IR 77-1214 / API 1101, "Evaluation of metal volumetric standards
    used in the measurement of liquid hydrocarbons":
    `https://doi.org/10.6028/nbs.ir.77-1214`
    (celik genlesme denklemleri ve temperature-pressure correction
    gelenegi icin tarihsel referans).
14. ASME B31.8, Gas Transmission and Distribution Piping Systems;
    ASME B31.4, Pipeline Transportation Systems for Liquids and Slurries.
    Bu calismada metinlere erisilmedi (paywall); yalnizca baglam
    olarak anildi.

**Dogrulanamayan iddialar:** ASME B31.8'in bu A/B tablosunu birebir
tanimladigi; kurum ici workbook'un hangi su property tablosundan
uretildigi; GAIL tablosunun `alpha=12.0` ile uretildigi; 7 degC
anomalisinin olusma nedeni. Bunlar bu dokumanda "cikarim" olarak
isaretlendi.

---

## 9. Uygulama Icin Somut API Onerisi

Bu bolum, `domain`, `data` ve `UI` ajanlarinin dogrudan uygulayabilecegi
sozlesmeyi tanimlar. Mevcut paralel uygulama (`BSource`,
`resolve_b_value`, `repair_anomalies`) ile uyumludur; farklar "ekleme"
olarak isaretlendi.

### 9.1 `BSource` enum

```python
from enum import Enum

class BSource(str, Enum):
    INSTITUTIONAL = "institutional"   # kurum ici A/B kontrol tablosu (varsayilan)
    GAIL = "gail"                     # GAIL referans tablosu
    AUTO = "auto"                     # beta - 3*alpha (fiziksel model)

DEFAULT_B_SOURCE = BSource.INSTITUTIONAL
```

Etiketler (UI):

```python
BSOURCE_LABELS = {
    BSource.INSTITUTIONAL: "Kurum ici A/B tablosu (varsayilan)",
    BSource.GAIL: "GAIL referans tablosu (karsilastirma)",
    BSource.AUTO: "Otomatik model (beta - 3*alpha)",
}
```

Kurallar:

- `normalize_b_source(source: BSource | str) -> BSource` string/enum
  kabul etmeli; gecersizde `ValidationError`.
- Yeni testte varsayilan `INSTITUTIONAL`; secim test bazinda saklanir,
  yeni teste sessizce tasinmaz.
- `AUTO` secildiginde `steel_model` ve `steel_alpha_micro_per_c` de
  secilebilir olmali (gelismis ayar).

### 9.2 `resolve_b_value(...)`

```python
@dataclass(frozen=True)
class BSourceResult:
    b_micro_per_c: float
    source: BSource
    label: str
    note: str
    repaired_table: bool = False

    # --- eklenmesi onerilen alanlar ---
    a_micro_per_bar: float | None = None
    a_source_note: str = ""
    a_repaired: bool = False
    a_repair_note: str = ""
    uncertainty_micro_per_c: float | None = None
    warnings: tuple[str, ...] = ()

    # AUTO icin teshis
    water_beta_micro_per_c: float | None = None
    steel_alpha_micro_per_c: float | None = None
    steel_model: str = ""


def resolve_b_value(
    source: BSource | str,
    temp_c: float,
    pressure_bar: float,
    steel_alpha_micro_per_c: float = 12.0,
    steel_model: str = DEFAULT_STEEL_MODEL,
    *,
    backend: str | None = None,        # AUTO icin su property backend'i
    repair_anomalies: bool = True,     # INSTITUTIONAL A gorunumu
) -> BSourceResult:
    ...
```

Davranis:

- `INSTITUTIONAL`: `lookup_ab_control_point(..., repair_anomalies=...)`;
  `b_micro_per_c` ham tablodan, `a_micro_per_bar` onarilmis gorunumden.
  `repaired_table`/`a_repaired` ve `note` provenance'i tasir.
- `GAIL`: `lookup_gail_reference_point`; kapsam disi ise
  `ValidationError` (ekstrapolasyon yok).
- `AUTO`: `beta = calculate_water_thermal_expansion_beta(T,P,backend)`;
  `b = calculate_b_coefficient(beta, alpha, steel_model=..., temp_c=T)`.
- `uncertainty_micro_per_c`: gecici olarak `5.0` (tablolar), `5.0`
  (auto); alan `None` de olabilir, UI "belirsizlik onaylanmadi" der.
- `warnings`: `|dB| >= 5` veya `>= %5` ise "Kaynak farki..." metni;
  `>= 10` veya `>= %10` ise "Yuksek kaynak farki" metni.
- Hicbir kaynak otomatik degistirilmez; `warnings` yalnizca bilgi.

### 9.3 `calculate_b_coefficient(..., steel_model=...)`

```python
STEEL_MODEL_LINEAR = "linear"
STEEL_MODEL_VOLUMETRIC = "volumetric"
STEEL_MODEL_VOLUMETRIC_TEMPERATURE = "volumetric_temperature"
STEEL_MODELS = (
    STEEL_MODEL_LINEAR,
    STEEL_MODEL_VOLUMETRIC,
    STEEL_MODEL_VOLUMETRIC_TEMPERATURE,
)
DEFAULT_STEEL_MODEL = STEEL_MODEL_VOLUMETRIC  # mevcut calisma agacinda boyle


def calculate_b_coefficient(
    water_beta_micro_per_c: float,
    steel_alpha_micro_per_c: float,
    steel_model: str = DEFAULT_STEEL_MODEL,
    temp_c: float | None = None,
) -> float:
    ...
```

Davranis:

- `linear`: `B = beta - alpha`. Geriye donuk uyumluluk icin kalir;
  **varsayilan degildir**, UI'de "eski/lineer (onaylanmaz)" etiketi alir.
- `volumetric` (varsayilan): `B = beta - 3*alpha`.
- `volumetric_temperature`: `B = beta - 3*(10.8 + 0.012*T)`;
  `temp_c` zorunlu; `steel_alpha_micro_per_c` steel terimi icin
  kullanilmaz (dokumante edilmeli). Alternatif olarak bu modelde
  `steel_alpha_micro_per_c=None` kabul edilebilir.
- `beta` negatif olabilir (4 degC alti); `B` negatif olabilir; ikisi de
  hata degildir. `alpha < 0` hata; `NaN/inf` hata.
- Fonksiyon yuvarlama yapmaz; tam float dondurur.
- `normalize_steel_model` gecersiz modelde `ValidationError`.

### 9.4 `lookup_ab_control_point(..., repair_anomalies=...)`

```python
@dataclass(frozen=True)
class ABControlPoint:
    temp_c: float
    pressure_bar: float
    a_micro_per_bar: float
    b_micro_per_c: float
    source_note: str
    repaired: bool = False
    repair_note: str = ""
    repair: ABRepairProvenance | None = None   # eklenmesi onerilen


def lookup_ab_control_point(
    temp_c: float,
    pressure_bar: float,
    csv_path: Path = DEFAULT_CONTROL_TABLE_CSV_PATH,
    metadata_path: Path = DEFAULT_CONTROL_TABLE_METADATA_PATH,
    repair_anomalies: bool = True,
) -> ABControlPoint:
    ...
```

Davranis:

- `repair_anomalies=True` (varsayilan, operasyonel): A hucrelerinden
  `a_monotonicity`/`a_step` ile isaretlenenler, ayni T satirinda en
  yakin saglikli komsular arasinda lineer interpolasyonla degistirilir.
  Yalnizca A degisir; B ham kalir; CSV dosyasina yazilmaz.
- `repair_anomalies=False`: ham workbook degerleri; denetim/regresyon
  icin.
- Sorgu penceresi onarilmis bir hucreye dokunuyorsa `repaired=True`;
  `repair_note` ham ve onarilmis A'yi, capalari ve politikayi icerir.
- `ABControlTableError`: kapsam disi T/P, eksik hucre, gecersiz tablo.
  Sessiz ekstrapolasyon yok.
- `count_repaired_ab_control_points()`: onarilan hucre sayisi (mevcut
  durumda 20). Testlerde beklenen deger olarak kullanilabilir.
- `clear_ab_control_table_cache()`: hem ham grid hem onarim grid
  cache'ini temizler.

**Provenance kurali:** Rapor, onarim varsa `policy`, `span_bar`,
`cells` sayisi, `anchors` ve `raw -> repaired` degerlerini gostermek
zorundadir. Onarim yoksa "A onarimi: yok" satiri gorunmelidir.

### 9.5 UI etiketleri ve varsayilanlari

| UI alani | Deger / davranis |
|---|---|
| `B kaynagi` secici | 3 secenek (9.1); varsayilan `Kurum ici A/B tablosu` |
| Kaynak aciklamasi | Her secenek icin 1 satir: kapsam, birim, "tablo/model" etiketi |
| Kapsam disi | GAIL icin `T/P` disinda hata; kurum ici icin 1-25 degC / 30-120 bar |
| `A onarimi` rozeti | `repaired=True` ise "A onarildi (7 degC / 81-100 bar)" + ham/onarilmis |
| `B = ...` satiri | `10^-6/K` birimiyle, 2 ondalik; kaynak etiketiyle |
| `A = ...` satiri | `10^-6/bar` birimiyle, 3 ondalik; provenance ile |
| Kaynak farki | Her zaman `dB` ve `%`; esiklerde sari/kirmizi uyari |
| Otomatik model detayi | `beta`, `alpha`, `steel_model`, backend; "tablo degil" etiketi |
| Rapor zorunlu satirlari | Kaynak, T/P, A, B, A provenance, B provenance, onarim, kaynak farki, belirsizlik |
| Varsayilan kaliciligi | Yeni testte kurum ici; onceki secim otomatik tasinmaz |

### 9.6 Testler (onerilen)

1. **Birim testi:** 16" OD / s=8.74 / Vt=118.798 / A=45 / B=65 /
   `dT=1` icin `Vp=0.007682511 m3`, `dP=1.005126 bar`.
2. **A donusumu:** `kappa=4.531748563556084e-10 1/Pa` ->
   `45.3174856 micro/bar`.
3. **B modelleri:** `beta=99.622`, `alpha=12` icin
   `linear=87.622`, `volumetric=63.622`,
   `volumetric_temperature(T=10)=66.862`.
4. **Onarim:** `count_repaired_ab_control_points()==20`;
   `lookup(7,90)` -> `repaired=True`, `A=47.115` (ham `45.515`);
   `lookup(7,90,repair_anomalies=False)` -> `45.515`;
   B her iki modda `32.663`.
5. **Kaynak uyarilari:** `compare_b_sources(10,50)` -> `dB=+4.47`
   (yumusak uyari, `%6.9`); `compare_b_sources(25,30)` -> otomatik
   `dB=-8.09` (yumusak uyari); `|dB|>=10` senaryosu sert uyari.
6. **Kapsam:** GAIL `T=26` -> `ValidationError`; kurum ici `T=26` ->
   `ABControlTableError`.
7. **Regresyon:** Dort referans noktada A/B tablo degerleri ve
   IAPWS-95 karsilastirmasi (tolerans: A `%0.2`, beta `%1`).

---

## Ek A. Sayisal Sonuclarin Yeniden Uretimi

Kullanilan ortam:

```text
Python 3.13
CoolProp 7.2.0
iapws 1.5.5
```

Temel kontroller:

```python
from CoolProp.CoolProp import PropsSI

def A_micro_per_bar(T, P):
    return PropsSI("ISOTHERMAL_COMPRESSIBILITY", "T", T + 273.15,
                   "P", P * 1e5, "Water") * 1e11

def beta_micro_per_K(T, P):
    return PropsSI("ISOBARIC_EXPANSION_COEFFICIENT", "T", T + 273.15,
                   "P", P * 1e5, "Water") * 1e6

def b_models(T, P, alpha=12.0):
    beta = beta_micro_per_K(T, P)
    return {
        "beta-alpha": beta - alpha,
        "beta-3alpha": beta - 3 * alpha,
        "beta-3alpha(T)": beta - 3 * (10.8 + 0.012 * T),
    }
```

IF97 capraz kontrolu icin `rho(T,P)` merkezi fark:

```python
def rho_if97(T, P):
    return PropsSI("D", "T", T + 273.15, "P", P * 1e5, "IF97::Water")

# A = (1/rho) * (drho/dP)_T ; beta = -(1/rho) * (drho/dT)_P
```

Not: IF97 backend'i CoolProp'ta `ISOTHERMAL_COMPRESSIBILITY` ve
`ISOBARIC_EXPANSION_COEFFICIENT` analitik turevlerini desteklemez;
yukaridaki gibi sayisal turev gerekir.

## Ek B. Terimler

| Terim | Anlam | Birim |
|---|---|---|
| `A` | Suyun izotermal sikistirilabilirligi `kappa_T` | `1/bar` (formulde micro/bar) |
| `B` | Suyun hacimsel genlesmesi - celigin hacimsel genlesmesi | `1/K` (formulde micro/K) |
| `beta` | Suyun izobarik hacimsel genlesme katsayisi | `1/K` |
| `alpha` | Celigin lineer termal genlesme katsayisi | `1/K` |
| `epsilon_s` | Boru elastik kompliyansi `0.884*ri/s*1e-6` | `1/bar` |
| `Vt` | Test bolumunun geometrik hacmi | `m3` |
| `Vp` | 1 bar artis icin teorik su hacmi | `m3` |
| `dP` | Sicaklik degisiminden kaynaklanan teorik basinc degisimi | `bar` |
