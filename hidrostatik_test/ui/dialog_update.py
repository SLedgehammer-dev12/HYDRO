from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING

from ..app_metadata import APP_NAME, APP_VERSION, RELEASES_PAGE_URL, SPEC_DOCUMENT_CODE, SPEC_DOCUMENT_TITLE
from ..services.updater import UpdateError, UpdateInfo, fetch_latest_update_info, install_update, open_release_page

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class UpdateDialogMixin:
    def _check_for_updates_on_startup(self: HydrostaticTestApp) -> None:
        self._start_update_check(user_requested=False)

    def _check_for_updates_manually(self: HydrostaticTestApp) -> None:
        self._start_update_check(user_requested=True)

    def _start_update_check(self: HydrostaticTestApp, user_requested: bool) -> None:
        if self.update_check_in_progress:
            if user_requested:
                messagebox.showinfo("Bilgi", "Guncelleme kontrolu zaten devam ediyor.")
            return
        self.update_check_in_progress = True
        self.update_status_var.set("Guncelleme kontrol ediliyor...")
        self.update_detail_var.set("GitHub release listesi sorgulaniyor.")
        worker = threading.Thread(
            target=self._perform_update_check,
            args=(user_requested,),
            daemon=True,
        )
        worker.start()

    def _perform_update_check(self: HydrostaticTestApp, user_requested: bool) -> None:
        try:
            update_info = fetch_latest_update_info()
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_check_error(str(exc), user_requested))
            return
        self.root.after(0, lambda: self._handle_update_check_result(update_info, user_requested))

    def _handle_update_check_error(self: HydrostaticTestApp, message: str, user_requested: bool) -> None:
        self.update_check_in_progress = False
        self.update_status_var.set("Guncelleme kontrolu tamamlanamadi.")
        self.update_detail_var.set(message)
        if user_requested:
            self._set_banner(message, "warning")
            messagebox.showwarning("Guncelleme Kontrolu", message)

    def _handle_update_check_result(self: HydrostaticTestApp, update_info: UpdateInfo, user_requested: bool) -> None:
        self.update_check_in_progress = False
        self.latest_update_info = update_info
        if update_info.update_available:
            asset_name = update_info.asset.name if update_info.asset is not None else "uygun zip asset bulunamadi"
            self.update_status_var.set(
                f"Yeni surum bulundu: {update_info.latest_version} ({update_info.tag_name})"
            )
            self.update_detail_var.set(
                f"Kaynak repo: {update_info.source_repository} | Yayin tarihi: {update_info.published_at or '-'} | Paket: {asset_name}"
            )
            self._set_banner(
                f"Yeni surum bulundu: {update_info.latest_version}. Isterseniz uygulama icinden guncellemeyi baslatabilirsiniz.",
                "warning",
            )
            if messagebox.askyesno(
                "Guncelleme Bulundu",
                (
                    f"Yeni surum bulundu: {update_info.latest_version}\n\n"
                    "Simdi indirip uygulamak ister misiniz?"
                ),
            ):
                self._apply_available_update()
            elif user_requested:
                self._set_banner(
                    "Yeni surum bulundu ancak kurulum kullanici onayi olmadan baslatilmadi.",
                    "info",
                )
            return

        self.update_status_var.set(f"Guncel surum kullaniyorsunuz: {APP_VERSION}")
        self.update_detail_var.set(
            f"Bu uygulama icin daha yeni bir release bulunmadi. Kontrol edilen birincil kaynak: {update_info.source_repository}"
        )
        if user_requested:
            self._set_banner("En guncel surumu kullaniyorsunuz.", "success")
            messagebox.showinfo("Guncelleme Kontrolu", "En guncel surumu kullaniyorsunuz.")

    def _apply_available_update(self: HydrostaticTestApp) -> None:
        if self.update_install_in_progress:
            messagebox.showinfo("Bilgi", "Guncelleme kurulumu zaten devam ediyor.")
            return
        if self.latest_update_info is None:
            self._check_for_updates_manually()
            return
        if not self.latest_update_info.update_available:
            messagebox.showinfo("Bilgi", "Kurulacak yeni bir surum bulunmuyor.")
            return
        try:
            download_root = self._resolve_update_download_dir(create=True)
        except OSError as exc:
            messagebox.showerror("Guncelleme", f"Indirme klasoru hazirlanamadi: {exc}")
            return
        folder_choice = messagebox.askyesnocancel(
            "Guncelleme Indirme Klasoru",
            (
                "Guncelleme paketinin nereye indirilecegini secin.\n\n"
                f"Mevcut klasor:\n{download_root}\n\n"
                "Evet: farkli klasor sec\n"
                "Hayir: mevcut klasorle devam et\n"
                "Iptal: islemi durdur"
            ),
        )
        if folder_choice is None:
            self._set_banner("Guncelleme kurulumu kullanici tarafindan iptal edildi.", "info")
            return
        if folder_choice:
            if not self._choose_update_download_dir():
                self._set_banner("Guncelleme indirme klasoru secilmedigi icin islem baslatilmadi.", "warning")
                return
            try:
                download_root = self._resolve_update_download_dir(create=True)
            except OSError as exc:
                messagebox.showerror("Guncelleme", f"Indirme klasoru hazirlanamadi: {exc}")
                return
        info = self.latest_update_info
        confirm = messagebox.askyesno(
            "Guncelleme Onayi",
            (
                f"Guncelleme kurulumu onayinizi bekliyor.\n\n"
                f"Mevcut surum: {APP_VERSION}\n"
                f"Yeni surum:    {info.latest_version}\n"
                f"Kaynak repo:   {info.source_repository}\n"
                f"Indirme yolu:  {download_root}\n\n"
                "Kurulum sirasinda uygulama kapanacak ve dosyalar yenilenecektir. Devam etmek istiyor musunuz?"
            ),
        )
        if not confirm:
            self._set_banner("Guncelleme kurulumu kullanici tarafindan onaylanmadi.", "info")
            return
        self.update_install_in_progress = True
        self.update_status_var.set(f"Guncelleme indiriliyor: {self.latest_update_info.latest_version}")
        self.update_detail_var.set(
            f"Release paketi indiriliyor ve kurulum hazirlaniyor. Indirme klasoru: {download_root}"
        )
        worker = threading.Thread(target=self._perform_update_install, args=(download_root,), daemon=True)
        worker.start()

    def _perform_update_install(self: HydrostaticTestApp, download_root: Path) -> None:
        if self.latest_update_info is None:
            self.root.after(0, lambda: self._handle_update_install_error("Guncel release bilgisi bulunamadi."))
            return
        try:
            install_mode = install_update(self.latest_update_info, download_root=download_root)
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_install_error(str(exc)))
            return
        self.root.after(0, lambda: self._handle_update_install_result(install_mode))

    def _handle_update_install_error(self: HydrostaticTestApp, message: str) -> None:
        self.update_install_in_progress = False
        self.update_status_var.set("Guncelleme kurulumu basarisiz oldu.")
        self.update_detail_var.set(message)
        self._set_banner(message, "error")
        messagebox.showerror("Guncelleme", message)

    def _handle_update_install_result(self: HydrostaticTestApp, install_mode: str) -> None:
        self.update_install_in_progress = False
        if install_mode == "browser":
            self.update_status_var.set("Tarayici uzerinden guncelleme yonlendirmesi acildi.")
            self.update_detail_var.set(
                "Bu ortam kendini otomatik guncelleyemiyor. Release sayfasi tarayicida acildi."
            )
            self._set_banner("Release sayfasi acildi. Guncel paketi indirip mevcut klasorun yerine koyabilirsiniz.", "warning")
            messagebox.showinfo(
                "Guncelleme",
                "Bu calisma ortami kendini otomatik guncelleyemiyor. Release sayfasi acildi.",
            )
            return
        if install_mode == "up_to_date":
            self.update_status_var.set(f"Guncel surum kullaniyorsunuz: {APP_VERSION}")
            self.update_detail_var.set("Kurulacak yeni bir surum bulunmuyor.")
            messagebox.showinfo("Guncelleme", "Kurulacak yeni bir surum bulunmuyor.")
            return
        self.update_status_var.set("Guncelleme baslatildi. Uygulama yeniden acilacak.")
        self.update_detail_var.set("Indirme tamamlandi. Uygulama kapanirken yeni surum uygulanacak.")
        self._set_banner("Guncelleme indirildi. Uygulama kapatilip yeni surumle yeniden baslatilacak.", "success")
        messagebox.showinfo(
            "Guncelleme",
            "Indirme tamamlandi. Uygulama kapanacak ve guncelleme uygulanacaktir.",
        )
        self.root.after(250, self.root.destroy)

    def _open_release_page(self: HydrostaticTestApp) -> None:
        target_url = RELEASES_PAGE_URL
        if self.latest_update_info is not None and self.latest_update_info.html_url:
            target_url = self.latest_update_info.html_url
        open_release_page(target_url)

    def _show_about_dialog(self: HydrostaticTestApp) -> None:
        messagebox.showinfo(
            "Hakkinda",
            (
                f"{APP_NAME}\n"
                f"Surum: {APP_VERSION}\n\n"
                f"Referans sartname: {SPEC_DOCUMENT_CODE}\n"
                f"{SPEC_DOCUMENT_TITLE}\n\n"
                "Bu uygulama hidrostatik test degerlendirmesi icin gelistirildi.\n"
                "Geometri manuel girilebilir, ASME B36.10 katalog listesinden secilebilir\n"
                "ve farkli et kalinliklarina sahip segmentler birlikte modellenebilir."
            ),
        )
