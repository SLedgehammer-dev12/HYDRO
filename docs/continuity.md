# Sureklilik Notu

## Mevcut Durum

- Kod tabani paket yapisina tasindi: `hidrostatik_test/`
- Kokte sadece launcher, build dosyalari ve ust seviye dokumanlar kaldi
- Build artefact'i `dist/windows/` altina ayrildi
- Eski prototip ve onceki calisma notlari `docs/legacy/` altina arsivlendi
- Otomatik test paketi 66 test ile geciyor
- Updater birincil olarak `SLedgehammer-dev12/HYDRO`, gecis icin ikinci kaynak olarak `SLedgehammer-dev12/Programlar` release'lerini tarayacak sekilde hazirlandi

## Teknik Gercekler

- Hesap cekirdegi `hidrostatik_test/domain/hydrotest_core.py`
- UI `hidrostatik_test/ui/app.py`
- Katalog ve referans veriler `hidrostatik_test/data/`
- Updater `hidrostatik_test/services/updater.py`
- Girdi akisini kolaylastirmak icin aktif teste ozel akis kontrol listesi eklendi
- Repo ayrisma gecisi icin updater kaynak secimi `hidrostatik_test/services/updater.py` icinde merkezilestirildi

## Acik Riskler

- 14.2 basinc-hacim `%0.2` limiti henuz modellenmedi
- 24 saatlik zaman serisi ve saha form akisi henuz yok
- Segmentli geometri yaklasimi icin kurum ici metod onayi alinmadi
- A birimi dokumanda tutarsiz gorunuyor; saha oncesi tablo ile teyit edilmeli
- `HYDRO` reposu bu oturumda olusturulamadi; GitHub CLI auth veya bos repo gerekecek

## Sonraki Oturumda Ilk Okunacaklar

1. `tasks/todo.md`
2. `tasks/lessons.md`
3. `docs/spec/ngtl_5007_hydrostatic_analysis.md`
4. `docs/ui_ergonomics.md`
5. `docs/repo_migration.md`

## Calisma Kuralı

Formul, katsayi veya kabul kriteri degisikligi yapilacaksa once spec analizi,
sonra test, sonra UI/rapor duzenlemesi yapilmalidir.
