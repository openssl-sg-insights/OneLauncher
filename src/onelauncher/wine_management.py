# coding=utf-8
###########################################################################
# Main window for OneLauncher.
#
# Based on PyLotRO
# (C) 2009 AJackson <ajackson@bcs.org.uk>
#
# Based on LotROLinux
# (C) 2007-2008 AJackson <ajackson@bcs.org.uk>
#
#
# (C) 2019-2021 June Stepp <contact@JuneStepp.me>
#
# This file is part of OneLauncher
#
# OneLauncher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# OneLauncher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OneLauncher.  If not, see <http://www.gnu.org/licenses/>.
###########################################################################
# Imports for extracting function
from onelauncher.ui_utilities import raise_warning_message
import logging
import lzma
import tarfile
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib import request
from pathlib import Path
from shutil import move, rmtree

from PySide6 import QtCore, QtWidgets

from onelauncher.settings import game_settings
from onelauncher.config import platform_dirs

# To use Proton, replace link with Proton build and uncomment
# `self.proton_documents_symlinker()` in wine_setup in wine_management
WINE_URL = "https://github.com/Kron4ek/Wine-Builds/releases/download/6.7/wine-6.7-staging-tkg-amd64.tar.xz"
DXVK_URL = (
    "https://github.com/doitsujin/dxvk/releases/download/v1.8.1/dxvk-1.8.1.tar.gz"
)


class WineManagement:
    def __init__(self):
        self.is_setup = False

        (platform_dirs.user_data_path /
         "wine").mkdir(parents=True, exist_ok=True)

        self.wine_path: Optional[Path] = None
        self.prefix_path = platform_dirs.user_cache_path / "wine/prefix"
        self.prefix_path.mkdir(exist_ok=True, parents=True)
        self.downloads_path = platform_dirs.user_data_path / "wine"
        self.downloads_path.mkdir(exist_ok=True, parents=True)
        self._dlgDownloader = None

    @property
    def dlgDownloader(self) -> QtWidgets.QProgressDialog:
        if self._dlgDownloader is None:
            self.create_progress_dialog()

        return self._dlgDownloader

    @dlgDownloader.setter
    def dlgDownloader(self, new_value: QtWidgets.QProgressDialog):
        self._dlgDownloader = new_value

    def create_progress_dialog(self):
        dialog = QtWidgets.QProgressDialog(
            "Checking for updates...",
            "",
            0,
            100,
            QtCore.QCoreApplication.instance().activeWindow(),
            QtCore.Qt.FramelessWindowHint,
        )
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setAutoClose(False)
        dialog.setCancelButton(None)
        self.dlgDownloader = dialog

    def wine_setup(self):
        """Sets wine program and downloads wine if it is not there or a new version is needed"""

        # Uncomment line below when using Proton
        # self.proton_documents_symlinker()

        self.latest_wine_version = WINE_URL.split(
            "/download/")[1].split("/")[0]
        latest_wine_path = platform_dirs.user_data_path / \
            ("wine/wine-" + self.latest_wine_version)

        if latest_wine_path.exists():
            self.wine_path = latest_wine_path / "bin/wine"
            return

        self.dlgDownloader.setLabelText("Downloading Wine...")
        latest_wine_path_tar = latest_wine_path.parent / \
            (latest_wine_path.name + ".tar.xz")

        if not self._downloader(WINE_URL, latest_wine_path_tar):
            return

        self.dlgDownloader.reset()
        self.dlgDownloader.setLabelText("Extracting Wine...")
        self.dlgDownloader.setValue(99)
        self._wine_extractor(latest_wine_path_tar)
        self.dlgDownloader.setValue(100)

        self.wine_path = (
            platform_dirs.user_data_path /
            ("wine/wine-" + self.latest_wine_version) / "bin/wine"
        )

    def dxvk_setup(self):
        self.latest_dxvk_version = DXVK_URL.split(
            "download/v")[1].split("/")[0]
        self.latest_dxvk_path = (
            platform_dirs.user_data_path /
            ("wine/dxvk-" + self.latest_dxvk_version)
        )
        if self.latest_dxvk_path.exists():
            if not (
                    self.prefix_path /
                    "drive_c/windows/system32/d3d11.dll").is_symlink():
                self._dxvk_injector()
            return

        self.dlgDownloader.setLabelText("Downloading DXVK...")
        latest_dxvk_path_tar = (self.latest_dxvk_path.parent /
                                (self.latest_dxvk_path.name + ".tar.gz"))
        if self._downloader(DXVK_URL, latest_dxvk_path_tar):
            self.dlgDownloader.reset()
            self.dlgDownloader.setLabelText("Extracting DXVK...")
            self.dlgDownloader.setValue(99)
            self._dxvk_extracor(latest_dxvk_path_tar)
            self.dlgDownloader.setValue(100)

            self._dxvk_injector()

    def _downloader(self, url, path: Path) -> bool:
        """Downloads file from url to path and shows progress with self.handle_download_progress"""
        try:
            request.urlretrieve(  # nosec
                url, str(path), self._handle_download_progress
            )
            return True
        except (URLError, HTTPError) as error:
            logger.error(error.reason, exc_info=True)
            raise_warning_message(
                f"There was an error downloading '{url}'. "
                "You may want to check your network connection.", self)
            return False

    def _handle_download_progress(self, index, frame, size):
        """Updates progress bar with download progress"""
        percent = 100 * index * frame // size
        self.dlgDownloader.setValue(percent)

    def _wine_extractor(self, path: Path):
        path_no_suffix = path.parent / \
            (path.with_suffix("").with_suffix(""))

        # Extracts tar.xz file
        with lzma.open(path) as file:
            with tarfile.open(fileobj=file) as tar:
                tar.extractall(path_no_suffix)

        # Moves files from nested directory to main one
        source_dir = [path for path in path_no_suffix.glob("*")
                      if path.is_dir()][0]
        move(source_dir, platform_dirs.user_data_path / "wine")
        source_dir = platform_dirs.user_data_path / "wine" / source_dir.name
        path_no_suffix.rmdir()
        source_dir.rename(source_dir.parent / path_no_suffix.name)

        # Removes downloaded tar.xz
        path.unlink()

        # Removes old wine versions
        for dir in (platform_dirs.user_data_path / "wine").glob("*"):
            if not dir.is_dir():
                continue

            if dir.name.startswith("wine") and not dir.name.endswith(
                    self.latest_wine_version):
                rmtree(dir)

    def _dxvk_extracor(self, path: Path):
        path_no_suffix = path.parent / \
            (path.with_suffix("").with_suffix(""))

        # Extracts tar.gz file
        with tarfile.open(path, "r:gz") as file:
            file.extractall(path_no_suffix.with_name(
                path_no_suffix.name + "_TEMP"))

        # Moves files from nested directory to main one
        source_dir = [dir for dir in path_no_suffix.with_name(
            path_no_suffix.name + "_TEMP").glob("*") if dir.is_dir()][0]
        move(
            path_no_suffix.with_name(
                path_no_suffix.name +
                "_TEMP") /
            source_dir,
            platform_dirs.user_data_path /
            "wine",
        )
        path_no_suffix.with_name(path_no_suffix.name + "_TEMP").rmdir()

        # Removes downloaded tar.gz
        path.unlink()

        # Removes old dxvk versions
        for dir in (platform_dirs.user_data_path / "wine").glob("*"):
            if not dir.is_dir():
                continue

            if str(
                    dir.name).startswith("dxvk") and not str(
                    dir.name).endswith(
                    self.latest_dxvk_version):
                rmtree(dir)

    def _dxvk_injector(self):
        """Adds dxvk to the wine prefix"""
        # Makes directories for dxvk dlls in case wine prefix hasn't been run
        # yet
        (self.prefix_path / "drive_c/windows/system32").mkdir(parents=True, exist_ok=True)
        (self.prefix_path / "drive_c/windows/syswow64").mkdir(parents=True, exist_ok=True)

        dll_list = ["dxgi.dll", "d3d10core.dll", "d3d11.dll", "d3d9.dll"]

        for dll in dll_list:
            system32_dll = self.prefix_path / "drive_c/windows/system32" / dll
            syswow64_dll = self.prefix_path / "drive_c/windows/syswow64" / dll

            # Removes current dlls
            (system32_dll).unlink(missing_ok=True)
            (syswow64_dll).unlink(missing_ok=True)

            # Symlinks dxvk dlls in to wine prefix
            system32_dll.symlink_to(self.latest_dxvk_path / "x64" / dll)
            syswow64_dll.symlink_to(self.latest_dxvk_path / "x32" / dll)

    def proton_documents_symlinker(self):
        """
        Symlinks prefix documents folder to system documents folder.path
        This is needed for Proton.
        """
        prefix_documents_folder = self.prefix_path / \
            "drive_c/users/steamuser/My Documents"

        # Will assume that the user has set something else up for now if the
        # folder already exists
        if prefix_documents_folder.exists():
            return

        # Make sure system documents folder and prefix documents root folder
        # exists
        platform_dirs.user_documents_path.mkdir(exist_ok=True)
        prefix_documents_folder.parent.mkdir(exist_ok=True, parents=True)

        # Make symlink to system documents folder
        platform_dirs.user_documents_path.symlink_to(
            prefix_documents_folder, target_is_directory=True)

    def setup_files(self):
        self.wine_setup()
        self.dlgDownloader.reset()
        self.dxvk_setup()
        self.dlgDownloader.close()
        self.is_setup = True


def edit_qprocess_to_use_wine(qprocess: QtCore.QProcess) -> None:
    """Reconfigures QProcess to use WINE. The program and arguments must be pre-set!"""
    processEnvironment = QtCore.QProcessEnvironment.systemEnvironment()

    if game_settings.current_game.builtin_wine_prefix_enabled:
        if not wine_management.is_setup:
            wine_management.setup_files()

        prefix_path = wine_management.prefix_path
        wine_path = wine_management.wine_path

        # Enables ESYNC if open file limit is high enough
        path = Path("/proc/sys/fs/file-max")
        if path.exists():
            with path.open() as file:
                file_data = file.read()
                if int(file_data) >= 524288:
                    processEnvironment.insert("WINEESYNC", "1")

        # Enables FSYNC. It overrides ESYNC and will only be used if
        # the required kernel patches are installed.
        processEnvironment.insert("WINEFSYNC", "1")

        # Adds dll overrides for DirectX, so DXVK is used instead of wine3d
        processEnvironment.insert(
            "WINEDLLOVERRIDES", "d3d11=n;dxgi=n;d3d10=n")
    else:
        prefix_path = game_settings.current_game.wine_prefix_path
        wine_path = game_settings.current_game.wine_path

    processEnvironment.insert("WINEPREFIX", str(prefix_path))

    if game_settings.current_game.wine_debug_level:
        processEnvironment.insert(
            "WINEDEBUG", game_settings.current_game.wine_debug_level)

    # Move current program to arguments and replace it with WINE.
    qprocess.setArguments([qprocess.program()] + qprocess.arguments())
    qprocess.setProgram(str(wine_path))

    qprocess.setProcessEnvironment(processEnvironment)


logger = logging.getLogger("main")
wine_management = WineManagement()
