# A/B Backend Arastirmasi

## Kapsam

Bu not, sadece `A` ve `B` katsayilarinin ikinci bir su ozelligi motoru ile
dogrulanmasi konusunu kapsar.

## Arastirma Sonucu

- Mevcut program `A` icin suyun izotermal sikistirilabilirligini,
  `B` icin ise `su beta - celik alpha` yaklasimini kullanir.
- `myiapws`, IAPWS-95 tabanli bagimsiz bir su ozelligi kutuphanesidir.
- `myiapws` ile yapilan noktasal ve kucuk izgara capraz kontrollerde
  CoolProp ile pratikte ayni sonuclar alinmistir.
- Teknik olarak ikinci dogrulama motoru olabilir; ancak `T,P` yerine `rho,T`
  calistigi icin yogunluk cozumleyicisi gerekir.

## Dagitim Karari

- `myiapws` ve benzer `iapws` GitHub projeleri GPLv3 lisanslidir.
- Bu uygulamanin dagitimi ihtimal dahilinde oldugu icin GPL tabanli bir ikinci
  motorun exe veya dagitilan paket icine gomulmesi varsayilan yol olarak
  secilmemistir.
- Bu nedenle kod tabani `water_properties.py` backend katmani ile
  hazirlanmis, ancak ikinci motor simdilik bundle edilmemistir.

## Sonraki Guvenli Yol

- Dagitima uygun ikinci motor icin oncelikli yol:
  resmi/prosedurel A-B tablolarini veya kurum ici dogrulanmis veri setini
  kullanarak GPL olmayan bir `table interpolation backend` yazmaktir.
- Bu backend ayni arayuze baglanabilir ve mevcut formulleri degistirmeden
  ikinci dogrulama sunabilir.

## Uygulanan Adim

- `table_v1` backend'i ve offline grid uretim akisi kod tabanina eklenmistir.
- Baslangic grid `0-40 degC` ve `1-150 bar` araliginda `6150` nokta icin
  `water_property_table_v1.csv` dosyasina uretilmistir.
