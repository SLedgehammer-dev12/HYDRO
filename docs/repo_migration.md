# Repo Migration

## Hedef

- Yeni public kaynak repo: `https://github.com/SLedgehammer-dev12/HYDRO`
- Birincil updater kaynagi: `SLedgehammer-dev12/HYDRO`
- Gecis/bridge kaynagi: `SLedgehammer-dev12/Programlar`

## Uygulanan Kod Degisikligi

- `hidrostatik_test/app_metadata.py`
  - `GITHUB_REPO = "HYDRO"`
  - `LEGACY_GITHUB_REPOS = ("Programlar",)`
- `hidrostatik_test/services/updater.py`
  - Updater birden fazla release kaynagini tarar
  - En yuksek gecerli surumu secer
  - Secilen release'in hangi repo kaynakli oldugunu `source_repository` alaninda tasir
- `hidrostatik_test/ui/app.py`
  - Guncelleme detay paneli kaynak repo bilgisini gosterir

## Bridge Stratejisi

Eski sahadaki exe'ler yalnizca `SLedgehammer-dev12/Programlar` release akisini bilir.
Bu nedenle migration icin tek dogru yol bir kopru release yayinlamaktir:

1. `SLedgehammer-dev12/HYDRO` public repo olusturulur.
2. Guncel kaynak kod bu yeni repo'ya push edilir.
3. Yeni repo icinde normal release akisi baslatilir.
4. Ayrica `Programlar` repo'sunda bir kez daha bridge release yayinlanir.
5. Eski kurulum bridge release'e guncellenir.
6. Bridge surum bundan sonraki guncellemeleri `HYDRO` repo'sundan alir.

## Bu Oturumda Yapilamayanlar

- `HYDRO` reposu olusturulamadi.
- Bu ortamda `gh` CLI authenticated degil.
- Mevcut MCP GitHub araclari repo create islemi sunmuyor.

## Repo Acildiginda Kalan Operasyon

1. Bos public `HYDRO` reposunu olustur.
2. Bu klasorun icerigini yeni repo'ya push et.
3. Yeni release artefact'ini `HYDRO` icinde yayinla.
4. Ayni bridge build'i `Programlar` icinde bir kez daha release et.
5. Sonraki surumlerde yalnizca `HYDRO` repo kullan.
