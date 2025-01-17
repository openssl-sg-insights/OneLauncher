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
import logging
import sqlite3
import urllib
import zipfile
from pathlib import Path
from shutil import copy, copytree, move, rmtree
from tempfile import TemporaryDirectory
from time import localtime, strftime
from typing import List, Optional, Tuple
from xml.dom import EMPTY_NAMESPACE
from xml.dom.minidom import Document, Element  # nosec

import defusedxml.minidom
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtUiTools import QUiLoader
from vkbeautify import xml as prettify_xml

import onelauncher
from onelauncher import settings, resources, logger, game_settings
from onelauncher.settings import CaseInsensitiveAbsolutePath
from onelauncher.utilities import GetText
from onelauncher.ui_resources import icon_font
from onelauncher.ui.addon_manager_uic import Ui_winAddonManager


class AddonManager(QtWidgets.QDialog):
    # ID is from the order plugins are found on the filesystem. InterfaceID is
    # the unique ID for plugins on lotrointerface.com
    # Don't change order of list
    COLUMN_LIST = [
        "ID",
        "Name",
        "Category",
        "Version",
        "Author",
        "LatestRelease",
        "File",
        "InterfaceID",
        "Dependencies",
        "StartupScript",
    ]
    # Don't change order of list
    TABLE_LIST = [
        "tablePluginsInstalled",
        "tableSkinsInstalled",
        "tableMusicInstalled",
        "tablePlugins",
        "tableSkins",
        "tableMusic",
        "tableSkinsDDO",
        "tableSkinsDDOInstalled",
    ]

    PLUGINS_URL = "https://api.lotrointerface.com/fav/OneLauncher-Plugins.xml"
    SKINS_URL = "https://api.lotrointerface.com/fav/OneLauncher-Themes.xml"
    MUSIC_URL = "https://api.lotrointerface.com/fav/OneLauncher-Music.xml"
    SKINS_DDO_URL = "https://api.lotrointerface.com/fav/OneLauncher-Themes-DDO.xml"

    def __init__(
        self,
        gameDocumentsDir: CaseInsensitiveAbsolutePath,
    ):
        super(
            AddonManager,
            self).__init__(
            QtCore.QCoreApplication.instance().activeWindow(),
            QtCore.Qt.FramelessWindowHint)

        self.ui = Ui_winAddonManager()
        self.ui.setupUi(self)

        if game_settings.current_game.game_type == "DDO":
            # Removes plugin and music tabs when using DDO.
            # This has to be done before the tab switching signals are
            # connected.
            self.ui.tabWidgetRemote.removeTab(0)
            self.ui.tabWidgetRemote.removeTab(1)
            self.ui.tabWidgetInstalled.removeTab(0)
            self.ui.tabWidgetInstalled.removeTab(1)

        # Creates backround color for addons that are installed already in
        # remote tables
        self.installed_addons_color = QtGui.QColor()
        self.installed_addons_color.setRgb(63, 73, 83)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            self.contextMenuRequested
        )
        self.ui.actionShowOnLotrointerface.triggered.connect(
            self.actionShowOnLotrointerfaceSelected
        )

        self.ui.btnBox.rejected.connect(self.btnBoxActivated)

        self.ui.btnAddonsMenu = QtWidgets.QMenu()
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionAddonImport
        )
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionShowSelectedOnLotrointerface
        )
        self.ui.actionAddonImport.triggered.connect(
            self.actionAddonImportSelected
        )
        self.ui.actionShowSelectedOnLotrointerface.triggered.connect(
            self.showSelectedOnLotrointerface
        )
        self.ui.actionShowAddonInFileManager.triggered.connect(
            self.actionShowAddonInFileManagerSelected
        )
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionShowPluginsFolderInFileManager
        )
        self.ui.actionShowPluginsFolderInFileManager.triggered.connect(
            self.actionShowPluginsFolderSelected
        )
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionShowSkinsFolderInFileManager
        )
        self.ui.actionShowSkinsFolderInFileManager.triggered.connect(
            self.actionShowSkinsFolderSelected
        )
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionShowMusicFolderInFileManager
        )
        self.ui.actionShowMusicFolderInFileManager.triggered.connect(
            self.actionShowMusicFolderSelected
        )
        self.ui.btnAddonsMenu.addAction(
            self.ui.actionUpdateAllSelectedAddons
        )
        self.ui.actionUpdateAllSelectedAddons.triggered.connect(
            self.updateAllSelectedAddons
        )

        self.updateAddonFolderActions(0)

        self.ui.actionInstallAddon.triggered.connect(
            self.actionInstallAddonSelected
        )
        self.ui.actionUninstallAddon.triggered.connect(
            self.actionUninstallAddonSelected
        )
        self.ui.actionUpdateAddon.triggered.connect(
            self.actionUpdateAddonSelected
        )

        self.ui.actionEnableStartupScript.triggered.connect(
            self.actionEnableStartupScriptSelected
        )
        self.ui.actionDisableStartupScript.triggered.connect(
            self.actionDisableStartupScriptSelected
        )

        self.ui.btnCheckForUpdates.setFont(icon_font)
        self.ui.btnCheckForUpdates.setText("\uf2f1")
        self.ui.btnCheckForUpdates.pressed.connect(
            self.checkForUpdates)
        self.ui.btnUpdateAll.pressed.connect(self.updateAll)

        self.ui.btnAddons.setMenu(
            self.ui.btnAddonsMenu)
        self.ui.btnAddons.clicked.connect(self.btnAddonsClicked)
        self.ui.btnAddons.setFont(icon_font)
        self.ui.btnAddons.setText("\uf068")

        self.ui.tabWidget.currentChanged.connect(
            self.tabWidgetIndexChanged
        )
        self.ui.tabWidgetInstalled.currentChanged.connect(
            self.tabWidgetInstalledIndexChanged
        )
        self.ui.tabWidgetRemote.currentChanged.connect(
            self.tabWidgetRemoteIndexChanged
        )

        self.ui.txtLog.hide()
        self.ui.btnLog.clicked.connect(self.btnLogClicked)

        self.ui.txtSearchBar.setFocus()
        self.ui.txtSearchBar.textChanged.connect(
            self.txtSearchBarTextChanged
        )

        for table in self.TABLE_LIST[:-2]:
            # Gets callable form from the string
            table = getattr(self.ui, table)

            # Hides ID column
            table.hideColumn(0)

            # Sort tables by addon name
            table.sortItems(1)

        self.openDB()

        self.data_folder = gameDocumentsDir
        if game_settings.current_game.game_type == "DDO":
            self.data_folder_skins = self.data_folder / "ui/skins"

            self.ui.tableSkinsInstalled.setObjectName(
                "tableSkinsDDOInstalled"
            )
            self.ui.tableSkins.setObjectName("tableSkinsDDO")
            self.getInstalledSkins()
        else:
            self.data_folder_plugins = self.data_folder / "Plugins"
            self.data_folder_skins = self.data_folder / "ui/skins"
            self.data_folder_music = self.data_folder / "Music"

            # Loads in installed plugins
            self.getInstalledPlugins()

    def getInstalledSkins(self, folders_list: Optional[List[Path]] = None):
        if self.isTableEmpty(self.ui.tableSkinsInstalled):
            folders_list = None

        self.data_folder_skins.mkdir(parents=True, exist_ok=True)

        if not folders_list:
            folders_list = [
                path for path in self.data_folder_skins.glob("*") if path.is_dir()]

        skins_list = []
        skins_list_compendium = []
        for folder in folders_list:
            skins_list.append(folder)
            for file in folder.iterdir():
                if file.suffix == ".skincompendium":
                    skins_list_compendium.append(file)
                    skins_list.remove(folder)
                    break

        self.addInstalledSkinsToDB(skins_list, skins_list_compendium)

    def addInstalledSkinsToDB(
            self,
            skins_list: List[Path],
            skins_list_compendium: List[Path]):
        table = self.ui.tableSkinsInstalled

        # Clears rows from db table if needed (This function is called to add
        # newly installed skins after initial load as well)
        if self.isTableEmpty(table):
            self.c.execute(
                "DELETE FROM {table}".format(table=table.objectName())  # nosec
            )

        for skin in skins_list_compendium:
            items_row = self.parseCompendiumFile(skin, "SkinConfig")
            items_row = self.getOnlineAddonInfo(
                items_row, self.ui.tableSkins.objectName()
            )
            self.addRowToDB(table, items_row)

        for skin in skins_list:
            items_row = [""] * (len(self.COLUMN_LIST) - 1)

            items_row[0] = skin.name
            items_row[5] = str(skin)
            items_row[1] = "Unmanaged"

            self.addRowToDB(table, items_row)

        # Populate user visible table
        self.reloadSearch(self.ui.tableSkinsInstalled)

    def getInstalledMusic(self, folders_list: Optional[List[Path]] = None):
        if self.isTableEmpty(self.ui.tableMusicInstalled):
            folders_list = None

        self.data_folder_music.mkdir(parents=True, exist_ok=True)

        if not folders_list:
            folders_list = [
                path for path in self.data_folder_music.glob("*") if path.is_dir()]

        music_list = []
        music_list_compendium = []
        for folder in folders_list:
            music_list.append(folder)
            for file in folder.iterdir():
                if file.suffix == ".musiccompendium":
                    music_list_compendium.append(
                        folder / file
                    )
                    music_list.remove(folder)
                    break

        for file in self.data_folder_music.iterdir():
            if file.suffix == ".abc":
                music_list.append(file)

        self.addInstalledMusicToDB(music_list, music_list_compendium)

    def parse_abc_file(self, abc_path: Path) -> Tuple[str, str]:
        with abc_path.open() as file:
            song_name = ""
            author = ""
            for _ in range(3):
                line = file.readline().strip()
                if line.startswith("T: "):
                    song_name = line[3:]
                if line.startswith("Z: "):
                    author = (
                        line[18:]
                        if line.startswith("Z: Transcribed by ")
                        else line[3:]
                    )

            return song_name, author

    def addInstalledMusicToDB(
            self,
            music_list: List[Path],
            music_list_compendium: List[Path]):
        table = self.ui.tableMusicInstalled

        # Clears rows from db table if needed (This function is called
        # to add newly installed music after initial load as well)
        if self.isTableEmpty(table):
            self.c.execute("DELETE FROM tableMusicInstalled")

        for music in music_list_compendium:
            items_row = self.parseCompendiumFile(music, "MusicConfig")
            items_row = self.getOnlineAddonInfo(items_row, "tableMusic")
            self.addRowToDB(table, items_row)

        for music in music_list:
            items_row = [""] * (len(self.COLUMN_LIST) - 1)

            items_row[0] = music.stem
            if music.suffix == ".abc":
                song_name, items_row[3] = self.parse_abc_file(music)
                if song_name:
                    items_row[0] = song_name

            items_row[5] = str(music)
            items_row[1] = "Unmanaged"

            self.addRowToDB(table, items_row)

        # Populate user visible table
        self.reloadSearch(table)

    def getInstalledPlugins(self, folders_list: Optional[List[Path]] = None):
        if self.isTableEmpty(self.ui.tablePluginsInstalled):
            folders_list = None

        self.data_folder_plugins.mkdir(parents=True, exist_ok=True)

        if not folders_list:
            folders_list = [
                path for path in self.data_folder_plugins.glob("*") if path.is_dir()]

        # Finds all plugins and adds their .plugincompendium files to a list
        plugins_list_compendium = []
        plugins_list = []
        for folder in folders_list:
            for file in folder.glob("**/*.plugin*"):
                if file.suffix == ".plugincompendium":
                    # .plugincompenmdium file should be in author folder of plugin
                    if file.parent == folder:
                        plugins_list_compendium.append(file)
                elif file.suffix == ".plugin":
                    plugins_list.append(file)

        self.removeManagedPluginsFromList(
            plugins_list, plugins_list_compendium
        )

        self.addInstalledPluginsToDB(plugins_list, plugins_list_compendium)

    def removeManagedPluginsFromList(
            self,
            plugin_files: List[CaseInsensitiveAbsolutePath],
            compendium_files: List[CaseInsensitiveAbsolutePath]) -> None:
        """Removes plugin files from plugin_files that aren't managed by a compendium file"""
        for compendium_file in compendium_files:
            doc = defusedxml.minidom.parse(str(compendium_file))
            nodes = doc.getElementsByTagName("Descriptors")[0].childNodes

            for node in nodes:
                if node.nodeName == "descriptor":
                    descriptor_path = self.data_folder_plugins / \
                        (GetText(node.childNodes).replace("\\", "/"))

                    # Remove descriptor plugin file from plugin_files
                    descriptor_plugin_files = [
                        file for file in plugin_files if file == descriptor_path]
                    for file in descriptor_plugin_files:
                        plugin_files.remove(file)

                    if not descriptor_path.exists():
                        self.addLog(
                            f"{compendium_file} has misconfigured descriptors")

    def addInstalledPluginsToDB(
            self,
            plugin_files: List[CaseInsensitiveAbsolutePath],
            compendium_files: List[CaseInsensitiveAbsolutePath]):
        table = self.ui.tablePluginsInstalled

        # Clears rows from db table if needed (This function is called to
        # add newly installed plugins after initial load as well)
        if self.isTableEmpty(table):
            self.c.execute("DELETE FROM tablePluginsInstalled")

        for file in compendium_files + plugin_files:
            # Sets tag for plugin file xml search and category for unmanaged
            # plugins
            if file.suffix == ".plugincompendium":
                items_row = self.parseCompendiumFile(file, "PluginConfig")
                items_row = self.getOnlineAddonInfo(items_row, "tablePlugins")
            else:
                items_row = self.parseCompendiumFile(file, "Information")
                items_row[1] = "Unmanaged"

            self.addRowToDB(table, items_row)

        # Populate user visible table
        self.reloadSearch(self.ui.tablePluginsInstalled)

    def getAddonDependencies(self, dependencies_node: Element):
        dependencies = ""
        for node in dependencies_node.childNodes:
            if node.nodeName == "dependency":
                dependencies = dependencies + "," + (GetText(node.childNodes))
        return dependencies[1:]

    def parseCompendiumFile(self, file: Path, tag: str) -> List[str]:
        """Returns list of common values for compendium or .plugin files"""
        items_row = [""] * (len(self.COLUMN_LIST) - 1)

        doc = defusedxml.minidom.parse(str(file))
        nodes = doc.getElementsByTagName(tag)[0].childNodes
        for node in nodes:
            if node.nodeName == "Name":
                items_row[0] = GetText(node.childNodes)
            elif node.nodeName == "Author":
                items_row[3] = GetText(node.childNodes)
            elif node.nodeName == "Version":
                items_row[2] = GetText(node.childNodes)
            elif node.nodeName == "Id":
                items_row[6] = GetText(node.childNodes)
            elif node.nodeName == "Dependencies":
                items_row[7] = self.getAddonDependencies(node)
            elif node.nodeName == "StartupScript":
                items_row[8] = GetText(node.childNodes)
        items_row[5] = str(file)

        return items_row

    def getOnlineAddonInfo(
            self,
            items_row: List[str],
            remote_addons_table: str) -> List[str]:
        for info in self.c.execute(
            "SELECT Category, LatestRelease FROM {table} WHERE InterfaceID == ?".format(  # nosec
                table=remote_addons_table
            ),
            (items_row[6],),
        ):
            items_row[1] = info[0]
            items_row[4] = info[1]

        # Unmanaged if not in online cache
        if not items_row[1]:
            items_row[1] = "Unmanaged"

        return items_row

    def openDB(self):
        """
        Opens addons_cache database and creates new database if
        one doesn't exist or the current one has an outdated structure
        """
        addons_cache_db_path = settings.platform_dirs.user_cache_path / "addons_cache.sqlite"
        if addons_cache_db_path.exists():
            # Connects to addons_cache database
            self.conn = sqlite3.connect(str(addons_cache_db_path))
            self.c = self.conn.cursor()

            # Replace old database if its structure is out of date
            if self.isCurrentDBOutdated():
                self.closeDB()
                addons_cache_db_path.unlink()
                self.createDB()
        else:
            self.createDB()

    def isCurrentDBOutdated(self):
        """
        Checks if currently loaded database's structure is up to date.
        Returns True if it is outdated and False otherwise.
        """

        tables_dict = {}
        # SQL returns all the columns in all the tables labled with what table
        # they're from
        for column_data in self.c.execute(
            "SELECT m.name as tableName, p.name as columnName FROM sqlite_master"
            " m left outer join pragma_table_info((m.name)) p on m.name <>"
                " p.name ORDER BY tableName, columnName"):
            # Ignore tables without actual information
            if column_data[0].endswith(
                ("_idx", "_docsize", "_data", "_content", "_config")
            ):
                continue

            if column_data[0] in tables_dict:
                tables_dict[column_data[0]].append(column_data[1])
            else:
                tables_dict[column_data[0]] = [column_data[1]]

        for table in self.TABLE_LIST:
            if table in tables_dict:
                for column in self.COLUMN_LIST[1:]:
                    try:
                        tables_dict[table].remove(column)
                    except ValueError:
                        return True

                # Return true if there are extra columns in table
                if tables_dict[table]:
                    return True

                # Delete table from dictionary, so program can
                # check if there are extra tables in tables_dict afterwards
                del tables_dict[table]
            else:
                return True

        # Only return False if there are no extra tables
        return bool(tables_dict)

    def createDB(self):
        """Creates ans sets up addons_cache database"""
        self.conn = sqlite3.connect(
            str(settings.platform_dirs.user_cache_path / "addons_cache.sqlite")
        )
        self.c = self.conn.cursor()

        for table in self.TABLE_LIST:
            self.c.execute(
                "CREATE VIRTUAL TABLE {tbl_nm} USING FTS5({clmA}, {clmB}, {clmC}, "
                "{clmD}, {clmE}, {clmF}, {clmG}, {clmH}, {clmI})".format(
                    tbl_nm=table,
                    clmA=self.COLUMN_LIST[1],
                    clmB=self.COLUMN_LIST[2],
                    clmC=self.COLUMN_LIST[3],
                    clmD=self.COLUMN_LIST[4],
                    clmE=self.COLUMN_LIST[5],
                    clmF=self.COLUMN_LIST[6],
                    clmG=self.COLUMN_LIST[7],
                    clmH=self.COLUMN_LIST[8],
                    clmI=self.COLUMN_LIST[9],
                ))

    def closeDB(self):
        self.conn.commit()
        self.conn.close()

    def actionAddonImportSelected(self):
        # DDO doesn't support playing music from .abc files
        if game_settings.current_game.game_type == "DDO":
            addon_formats = "*.zip *.rar"
        else:
            addon_formats = "*.zip *.rar *.abc"

        file_names = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Addon Files/Archives",
            str(Path("~").expanduser()),
            addon_formats,
        )

        if file_names[0]:
            for file in file_names[0]:
                self.installAddon(Path(file))

    def installAddon(self, addon_path: Path, interface_id: str = ""):
        # Install .abc files
        if addon_path.suffix == ".abc":
            self.installAbcFile(addon_path)
            return
        elif addon_path.suffix == ".rar":
            self.addLog(
                f"{onelauncher.__title__} does not support .rar archives, because it"
                " is a proprietary format that would require and external "
                "program to extract")
            return
        elif addon_path.suffix == ".zip":
            self.installZipAddon(addon_path, interface_id)

    def installAbcFile(self, addon_path: Path):
        if game_settings.current_game.game_type == "DDO":
            self.addLog("DDO does not support .abc/music files")
            return

        copy(str(addon_path), self.data_folder_music)
        logger.info(f"{addon_path} installed")

        # Plain .abc files are installed to base music directory,
        # so what is scanned can't be controlled
        self.ui.tableMusicInstalled.clearContents()
        self.getInstalledMusic()

    def installZipAddon(self, addon_path: Path, interface_id: str):
        with TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            # Extract addon to temporary directory.
            with zipfile.ZipFile(addon_path, "r") as archive:
                # Addons without any files aren't valid
                if all(zip_info.is_dir() for zip_info in archive.infolist()):
                    self.addLog("Add-on Zip is empty. Aborting")
                    return

                archive.extractall(tmp_dir)

            self.clean_temp_addon_folder(tmp_dir)

            for path in tmp_dir.glob("**/*.*"):
                if path.suffix == ".plugin":
                    self.install_plugin(
                        tmp_dir, interface_id)
                    return
                elif path.suffix == ".abc":
                    if (
                        self.install_music(
                            tmp_dir, interface_id, addon_path.stem
                        )
                        is False
                    ):
                        continue
                    else:
                        return
            self.install_skin(tmp_dir, interface_id, addon_path.stem)

    def install_plugin(self, tmp_dir: Path, interface_id: str) -> None:
        """Install plugin from temporary directory"""
        if game_settings.current_game.game_type == "DDO":
            self.addLog("DDO does not support plugins")
            return

        table = self.ui.tablePlugins

        author_folders = [path for path in tmp_dir.glob("*") if path.is_dir()]

        # Filter out common dependency folder names
        # that are sometimes included with plugins.
        filtered_author_folders = [
            folder for folder in author_folders if folder.name.lower() not in [
                "turbine", "turbineplugins"]]
        # Use non-filtered author folders if there are no author
        # folders left after filtering.
        # Ex. When installing the filtered libraries standalone.
        author_folders = filtered_author_folders or author_folders

        # There can only be one author folder. That is where the
        # compendium file goes. What appear to be extra author
        # folders are usually included dependencies (grr.. there
        # is compendium syntax for that). The true author folder
        # where the actual plugin files are must be determined.
        if len(author_folders) > 1:
            # The most likely author folder is where a
            # .plugincompendium file is.
            author_folders_compendium = [
                dir for dir in author_folders if list(
                    dir.glob("*.plugincompendium"))]
            if author_folders_compendium:
                author_folder = author_folders_compendium[0]
            else:
                # The next most likely author folder is where
                # .plugin files are. Dependencies may also
                # have .plugin files though.
                author_folders_plugin = [
                    dir for dir in author_folders if list(
                        dir.glob("*.plugin"))]
                if author_folders_plugin:
                    author_folder = author_folders_plugin[0]
                else:
                    self.addLog("Plugin doesn't have an author folder"
                                " with a .plugin file.")
                    return
        else:
            author_folder = author_folders[0]

        # .plugin files should always be in the author folder. All others
        # will be ignored by both me and the game.
        plugin_files = list(author_folder.glob("*.plugin"))

        existing_compendium_file = self.get_existing_compendium_file(
            author_folder)
        if existing_compendium_file is False:
            return

        compendium_files = []
        # Only make compendium file for addons installed from online
        if interface_id:
            compendium_file = self.generateCompendiumFile(
                author_folder,
                interface_id,
                "Plugin",
                table.objectName(),
                existing_compendium_file,
            )
            compendium_files.append(compendium_file)
        # Remove compendium files from manually installed addons.
        # This is to limit confusion since there is no way to verify
        # that compendium files from manually installed addons have
        # correct information. ex. They could have some random interface_id
        # suggesting they're the wrong addon and end up getting replaced
        # by the addon for that ID during the updating process.
        elif existing_compendium_file:
            existing_compendium_file.unlink()

        # Move plugin from temp directory to actual plugins directory
        for path in tmp_dir.glob("*"):
            copytree(path, self.data_folder_plugins /
                     path.name, dirs_exist_ok=True)

        # Make plugin and compendium file paths point to their new location
        plugin_files = [
            self.data_folder_plugins /
            str(file).replace(
                str(tmp_dir),
                "").strip("/") for file in plugin_files]
        compendium_files = [
            self.data_folder_plugins /
            str(file).replace(
                str(tmp_dir),
                "").strip("/") for file in compendium_files]

        self.removeManagedPluginsFromList(plugin_files, compendium_files)

        self.addInstalledPluginsToDB(plugin_files, compendium_files)

        self.handleStartupScriptActivationPrompt(table, interface_id)
        logger.info(
            "Installed addon corresponding to "
            f"{plugin_files} )"
            f"{compendium_files}")

        self.installAddonRemoteDependencies(
            table.objectName() + "Installed")

    def get_existing_compendium_file(self, tmp_search_dir: Path):
        """Return existing compendium file, None, or False
           if there are multiple.

        Args:
            tmp_search_dir (Path): Directory to check for compendium files in.
                                   It has to be a temporary folder the addon
                                   has been extracted to or compendium files
                                   from other addons will be detected.
        """
        existing_compendium_files = list(
            tmp_search_dir.glob("*.*compendium"))
        if len(existing_compendium_files) > 1:
            self.addLog(
                f"Addon has multiple compendium files.")
            return False
        elif len(existing_compendium_files) == 1:
            return existing_compendium_files[0]

    def install_music(self, tmp_dir: Path, interface_id: str, addon_name: str):
        if game_settings.current_game.game_type == "DDO":
            self.addLog("DDO does not support .abc/music files")
            return

        # Some plugins have .abc files, but music collections
        # shouldn't have .plugin files.
        if list(tmp_dir.glob("**/*.plugin")):
            return False

        table = self.ui.tableMusic

        root_dir = self.fix_improper_root_dir_addon(tmp_dir, addon_name)

        existing_compendium_file = self.get_existing_compendium_file(root_dir)
        if existing_compendium_file is False:
            return

        if interface_id:
            self.generateCompendiumFile(
                root_dir, interface_id, "Music", table.objectName(),
                existing_compendium_file)

        # Move the addon into the real data folder
        copytree(root_dir, self.data_folder_music /
                 root_dir.name, dirs_exist_ok=True)
        root_dir = self.data_folder_music / root_dir.name

        self.getInstalledMusic(folders_list=[root_dir])

        self.handleStartupScriptActivationPrompt(table, interface_id)

        logger.info(f"{root_dir} music installed")

        self.installAddonRemoteDependencies(table.objectName() + "Installed")

    def install_skin(self, tmp_dir: Path, interface_id, addon_name: str):
        table = self.ui.tableSkins

        root_dir = self.fix_improper_root_dir_addon(tmp_dir, addon_name)

        existing_compendium_file = self.get_existing_compendium_file(root_dir)
        if existing_compendium_file is False:
            return

        if interface_id:
            self.generateCompendiumFile(
                root_dir,
                interface_id,
                "Skin",
                table.objectName(),
                existing_compendium_file)

        # Move the addon into the real data folder
        copytree(root_dir, self.data_folder_skins /
                 root_dir.name, dirs_exist_ok=True)
        root_dir = self.data_folder_skins / root_dir.name

        self.getInstalledSkins(folders_list=[root_dir])

        self.handleStartupScriptActivationPrompt(table, interface_id)

        logger.info(f"{root_dir} skin installed")

        self.installAddonRemoteDependencies(table.objectName() + "Installed")

    def installAddonRemoteDependencies(self, table):
        """Installs the dependencies for the last installed addon"""
        # Gets dependencies for last column in db
        for item in self.c.execute(
            "SELECT Dependencies FROM {table} ORDER BY rowid DESC LIMIT 1".format(  # nosec
                table=table
            )
        ):
            dependencies = item[0]

        for dependency in dependencies.split(","):
            if dependency:
                # 0 is the arbitrary ID for Turbine Utilities. 1064 is the ID
                # of OneLauncher's upload of the utilities on LotroInterface
                if dependency == "0":
                    dependency = "1064"

                for item in self.c.execute(  # nosec
                    "SELECT File, Name FROM {table} WHERE InterfaceID = ? AND InterfaceID NOT IN "
                    "(SELECT InterfaceID FROM {table_installed})".format(
                        table=table.split("Installed")[
                            0], table_installed=table,
                    ),
                    (dependency,),
                ):
                    self.installRemoteAddon(item[0], item[1], dependency)

    def fix_improper_root_dir_addon(
            self,
            addon_tmp_dir: Path,
            addon_name: str) -> Path:
        """Moves addon to new folder if the top of the directory tree
           is anything but one folder and no files. This should only be
           used for skins and music.

        Args:
            addon_tmp_dir (Path): Temporary directory where the addon has been extracted.
            addon_name (str): Name to give the new folder if it is made.

        Returns:
            (Path): Root dir of the addon. Where the compendium file should go.
        """
        temp_dir_contents = list(addon_tmp_dir.glob("*"))

        # If there is already a root dir and nothing else
        if len(temp_dir_contents) == 1 and temp_dir_contents[0].is_dir():
            return temp_dir_contents[0]

        with TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            # Move addon_tmp_dir contents to new temporary folder.
            # This is to prevent issues with addon_name being the
            # same as one of the existing folders in addon_tmp_dir.
            for path in temp_dir_contents:
                move(path, tmp_dir)

            # Make new folder to be the addon root dir
            new_addon_root_dir = addon_tmp_dir / addon_name
            new_addon_root_dir.mkdir()

            # Move all of the original contents of addon_tmp_dir
            # into the new root dir.
            for path in tmp_dir.glob("*"):
                move(path, new_addon_root_dir)

        return new_addon_root_dir

    def clean_temp_addon_folder(self, addon_dir: Path) -> None:
        """Scans temp folder for invalid folder names like "ui" or
           "plugins" and moves stuff out of them. Addon authors put
           files in invalid folders when they want the user to extract
           the file somewere higher up the folder tree than where their
           work ends up. This is usually done for user convenience.

        Args:
            addon_dir (Path): Temporary folder where addon has been extracted.
        """
        invalid_folder_names = [
            "ui",
            "skins",
            "Plugins",
            "Music",
            "My Documents",
            "Documents",
            "The Lord of the Rings Online",
            "Dungeons and Dragons Online",
            "Dungeons & Dragons Online",
        ]
        with TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            while True:
                invalid_dir = None
                for potential_invalid_path in addon_dir.glob("*"):
                    if (potential_invalid_path.is_dir() and
                            potential_invalid_path.name in invalid_folder_names):
                        invalid_dir = potential_invalid_path
                        # Move everything from the invalid directory to a temporary one.
                        # This is done to prevent issues when a folder in the invalid folder
                        # has the same name as the invalid folder.
                        for path in invalid_dir.glob("*"):
                            move(str(path), str(tmp_dir))

                        invalid_dir.rmdir()

                        # Move files that were originally in the invalid folder
                        # to the root addon_dir
                        for path in tmp_dir.glob("*"):
                            move(str(path), str(addon_dir))

                # Stop loop if there were no more invalid folders discovered.
                if invalid_dir is None:
                    break

    def generateCompendiumFile(
            self,
            tmp_addon_root_dir: Path,
            interface_id: str,
            addon_type: str,
            table: str,
            existing_compendium_file: Path = None):
        """Generate compendium file for addon. If there is an existing one
           data that can only be gotten from it will be gathered and put
           in the new file. The old one will be removed.

        Args:
            tmp_addon_root_dir (Path): Where the compendium file goes. In the
                                       case of plugins it should be the author's
                                       name. This has to be the addon root dir
                                       while it is still in a temporary directory
                                       for propper .plugin file detection.
            interface_id (str): [description]
            addon_type (str): The type of the addon. ("Plugin", "Music", "Skin")
            table (str): The database table name for the addon type. Used to get remote
                         addon information.
            existing_compendium_file (Path, optional): An existing compendium file to
                                                       extract data from. Defaults to None.
        """
        dependencies = ""
        startup_python_script = ""
        # Get dependencies and startup_python_script from existing compendium
        # file if present.
        if existing_compendium_file:
            existing_compendium_values = self.parseCompendiumFile(
                existing_compendium_file, f"{addon_type.title()}Config"
            )
            dependencies = existing_compendium_values[7]
            startup_python_script = existing_compendium_values[8]
            existing_compendium_file.unlink()

        for row in self.c.execute(
                f"SELECT * FROM {table} WHERE InterfaceID = ?", (interface_id,)):  # nosec
            if row[0]:
                doc = Document()
                mainNode = doc.createElementNS(
                    EMPTY_NAMESPACE, addon_type.title() + "Config")
                doc.appendChild(mainNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "Id")
                tempNode.appendChild(doc.createTextNode("%s" % (row[6])))
                mainNode.appendChild(tempNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "Name")
                tempNode.appendChild(doc.createTextNode("%s" % (row[0])))
                mainNode.appendChild(tempNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "Version")
                tempNode.appendChild(doc.createTextNode("%s" % (row[2])))
                mainNode.appendChild(tempNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "Author")
                tempNode.appendChild(doc.createTextNode("%s" % (row[3])))
                mainNode.appendChild(tempNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "InfoUrl")
                tempNode.appendChild(
                    doc.createTextNode(
                        "%s" % (self.getInterfaceInfoUrl(row[5])))
                )
                mainNode.appendChild(tempNode)

                tempNode = doc.createElementNS(EMPTY_NAMESPACE, "DownloadUrl")
                tempNode.appendChild(doc.createTextNode("%s" % (row[5])))
                mainNode.appendChild(tempNode)

                if addon_type.title() == "Plugin":
                    # Add plugin's .plugin file descriptors
                    descriptorsNode = doc.createElementNS(
                        EMPTY_NAMESPACE, "Descriptors"
                    )
                    mainNode.appendChild(descriptorsNode)
                    for plugin_file in tmp_addon_root_dir.glob("*.plugin"):
                        tempNode = doc.createElementNS(
                            EMPTY_NAMESPACE, "descriptor"
                        )
                        tempNode.appendChild(
                            doc.createTextNode(
                                "%s" %
                                (f"{tmp_addon_root_dir.name}\\{plugin_file.name}")))
                        descriptorsNode.appendChild(tempNode)

                # Can't add dependencies, because they are defined in
                # compendium files
                dependenciesNode = doc.createElementNS(
                    EMPTY_NAMESPACE, "Dependencies")
                mainNode.appendChild(dependenciesNode)

                # If compendium file from add-on already existed with
                # dependencies
                if dependencies:
                    for dependency in dependencies.split(","):
                        tempNode = doc.createElementNS(
                            EMPTY_NAMESPACE, "dependency")
                        tempNode.appendChild(
                            doc.createTextNode("%s" % (dependency)))
                        dependenciesNode.appendChild(tempNode)

                # Can't add startup script, because it is defined in compendium
                # files
                startupScriptNode = doc.createElementNS(
                    EMPTY_NAMESPACE, "StartupScript"
                )
                # If compendium file from add-on already existed with startup
                # script
                if startup_python_script:
                    startupScriptNode.appendChild(
                        doc.createTextNode("%s" % (startup_python_script))
                    )
                mainNode.appendChild(startupScriptNode)

                # Write compendium file
                compendium_file = tmp_addon_root_dir / \
                    f"{row[0]}.{addon_type.lower()}compendium"
                with compendium_file.open("w+") as file:
                    pretty_xml = prettify_xml(doc.toxml())
                    file.write(pretty_xml)

                return compendium_file

    def getInterfaceInfoUrl(self, download_url: str):
        """Replaces "download" with "info" in download url to make info url

        An example is: https://www.lotrointerface.com/downloads/download1078-VitalTarget
                   to: https://www.lotrointerface.com/downloads/info1078-VitalTarget
        """
        return download_url.replace("/downloads/download", "/downloads/info")

    def txtSearchBarTextChanged(self, text):
        if game_settings.current_game.game_type == "LOTRO":
            # If in Installed tab
            if self.ui.tabWidget.currentIndex() == 0:
                index_installed = self.ui.tabWidgetInstalled.currentIndex()

                # If in PluginsInstalled tab
                if index_installed == 0:
                    self.searchDB(
                        self.ui.tablePluginsInstalled, text)
                # If in SkinsInstalled tab
                elif index_installed == 1:
                    self.searchDB(
                        self.ui.tableSkinsInstalled, text)
                # If in MusicInstalled tab
                elif index_installed == 2:
                    self.searchDB(
                        self.ui.tableMusicInstalled, text)
            # If in Find More tab
            elif self.ui.tabWidget.currentIndex() == 1:
                index_remote = self.ui.tabWidgetRemote.currentIndex()
                # If in Plugins tab
                if index_remote == 0:
                    self.searchDB(self.ui.tablePlugins, text)
                # If in Skins tab
                elif index_remote == 1:
                    self.searchDB(self.ui.tableSkins, text)
                # If in Music tab
                elif index_remote == 2:
                    self.searchDB(self.ui.tableMusic, text)
        else:
            # If in Installed tab
            if self.ui.tabWidget.currentIndex() == 0:
                self.searchDB(self.ui.tableSkinsInstalled, text)
            # If in Find More tab
            elif self.ui.tabWidget.currentIndex() == 1:
                self.searchDB(self.ui.tableSkins, text)

    def searchDB(self, table, text):
        table.clearContents()
        table.setRowCount(0)

        if text:
            for word in text.split():
                search_word = "%" + word + "%"

                for row in self.c.execute(
                    # nosec
                    "SELECT rowid, * FROM {table} WHERE Author LIKE ? OR Category"
                    " LIKE ? OR Name LIKE ?".format(table=table.objectName()),
                    (search_word, search_word, search_word),
                ):
                    # Detects duplicates from multi-word search
                    duplicate = False
                    for item in table.findItems(
                            row[1], QtCore.Qt.MatchExactly):
                        if int((table.item(item.row(), 0)).text()) == row[0]:
                            duplicate = True
                            break
                    if not duplicate:
                        self.addRowToTable(table, row)
        else:
            # Shows all plugins if the search bar is empty
            for row in self.c.execute(
                # nosec
                "SELECT rowid, * FROM {table}".format(table=table.objectName())
            ):
                self.addRowToTable(table, row)

    def isTableEmpty(self, table):
        return not table.item(0, 1)

    def reloadSearch(self, table):
        """Re-searches the current search"""
        self.searchDB(table, self.ui.txtSearchBar.text())

    def resetRemoteAddonsTables(self):
        for i in range(self.ui.tabWidgetRemote.count()):
            tab = self.ui.tabWidgetRemote.widget(i)
            table = getattr(
                self.ui, tab.objectName().replace("tab", "table")
            )
            if not self.isTableEmpty(table):
                self.searchDB(table, "")

    def setRemoteAddonToUninstalled(self, addon, remote_table):
        self.c.execute(
            "UPDATE {table} SET Name = ? WHERE InterfaceID == ?".format(  # nosec
                table=remote_table.objectName()
            ),
            (addon[2], addon[0],),
        )

        # Removes indicator that a new version of an installed addon is out if present.
        # This is important, because addons are uninstalled and then reinstalled
        # during the update process.
        self.c.execute(
            # nosec
            "UPDATE {table} SET Version = REPLACE(Version,'(Updated) ', '') WHERE "
            "Version LIKE '(Updated) %'".format(
                table=remote_table.objectName())
        )

    def setRemoteAddonToInstalled(self, addon, remote_table):
        self.c.execute(
            "UPDATE {table} SET Name = ? WHERE InterfaceID == ?".format(  # nosec
                table=remote_table.objectName()
            ),
            ("(Installed) " + addon[2], addon[0],),
        )

    # Adds row to a visible table. First value in list is row name
    def addRowToTable(self, table, list):
        table.setSortingEnabled(False)

        disable_row = False

        rows = table.rowCount()
        table.setRowCount(rows + 1)

        # Sets row name
        tbl_item = QtWidgets.QTableWidgetItem()
        tbl_item.setText(str(list[0]))

        # Adds items to row
        for column, item in enumerate(list):
            tbl_item = QtWidgets.QTableWidgetItem()

            tbl_item.setText(str(item))
            # Sets color to red if addon is unmanaged
            if item == "Unmanaged" and column == 2:
                tbl_item.setForeground(QtGui.QColor("darkred"))
            # Disable row if addon is Installed. This is only applicable to
            # remote tables.
            elif str(item).startswith("(Installed) ") and column == 1:
                tbl_item.setText(item.split("(Installed) ")[1])
                disable_row = True
            elif str(item).startswith("(Updated) ") and column == 3:
                tbl_item.setText(item.split("(Updated) ")[1])
                tbl_item.setForeground(QtGui.QColor("green"))
            elif str(item).startswith("(Outdated) ") and column == 3:
                tbl_item.setText(item.split("(Outdated) ")[1])
                tbl_item.setForeground(QtGui.QColor("crimson"))

            table.setItem(rows, column, tbl_item)

        if disable_row:
            for i in range(table.columnCount()):
                table.item(rows, i).setFlags(QtCore.Qt.ItemIsEnabled)
                table.item(rows, i).setBackground(self.installed_addons_color)

        table.setSortingEnabled(True)

    def addRowToDB(self, table, list):
        question_marks = "?"
        for _ in range(len(list) - 1):
            question_marks += ",?"

        self.c.execute(
            "INSERT INTO {table} VALUES({})".format(
                question_marks, table=table.objectName()
            ),
            (list),  # nosec
        )

    def btnBoxActivated(self):
        self.accept()

    def btnLogClicked(self):
        if self.ui.txtLog.isHidden():
            self.ui.txtLog.show()
        else:
            self.ui.txtLog.hide()

    def addLog(self, message):
        self.ui.lblErrors.setText(
            "Errors: " +
            str(int(self.ui.lblErrors.text()[-1]) + 1)
        )
        logger.warning(message)
        self.ui.txtLog.append(message + "\n")

    def btnAddonsClicked(self):
        table = self.getCurrentTable()

        # If on installed tab which means remove addons
        if table.objectName().endswith("Installed"):
            uninstall_function = self.getUninstallFunctionFromTable(table)

            uninstallConfirm, addons = self.getUninstallConfirm(table)
            if uninstallConfirm:
                uninstall_function(addons, table)
                self.resetRemoteAddonsTables()

        elif self.ui.tabWidget.currentIndex() == 1:
            self.installRemoteAddons()

    def getUninstallFunctionFromTable(self, table):
        """Gives function to uninstall addon type for table"""
        if "Skins" in table.objectName():
            uninstall_function = self.uninstallSkins
        elif "Plugins" in table.objectName():
            uninstall_function = self.uninstallPlugins
        elif "Music" in table.objectName():
            uninstall_function = self.uninstallMusic
        else:
            raise IndexError(
                table.objectName() + " doesn't correspond to add-on type tab"
            )

        return uninstall_function

    def installRemoteAddons(self):
        table = self.getCurrentTable()

        addons, details = self.getSelectedAddons(table)
        if addons and details:
            for addon in addons:
                self.installRemoteAddon(addon[1], addon[2], addon[0])
                self.setRemoteAddonToInstalled(addon, table)

            self.resetRemoteAddonsTables()
            self.searchSearchBarContents()

    def getCurrentTable(self):
        """Return the table that the user currently sees based on what tabs they are in"""
        if self.ui.tabWidget.currentIndex() == 0:
            if game_settings.current_game.game_type == "LOTRO":
                index_installed = self.ui.tabWidgetInstalled.currentIndex()

                if index_installed == 0:
                    table = self.ui.tablePluginsInstalled
                elif index_installed == 1:
                    table = self.ui.tableSkinsInstalled
                elif index_installed == 2:
                    table = self.ui.tableMusicInstalled
            else:
                table = self.ui.tableSkinsInstalled
        elif self.ui.tabWidget.currentIndex() == 1:
            if game_settings.current_game.game_type == "DDO":
                table = self.ui.tableSkins
            else:
                index_remote = self.ui.tabWidgetRemote.currentIndex()

                if index_remote == 0:
                    table = self.ui.tablePlugins
                elif index_remote == 1:
                    table = self.ui.tableSkins
                elif index_remote == 2:
                    table = self.ui.tableMusic
        else:
            raise IndexError(
                str(self.ui.tabWidget.currentIndex())
                + " isn't valid main tab index"
            )

        return table

    def installRemoteAddon(self, url, name: str, interface_id):
        with TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            path = tmp_dir / f"{name}.zip"
            status = self.downloader(url, path)
            if status:
                self.installAddon(path, interface_id=interface_id)
                path.unlink()

    def getUninstallConfirm(self, table):
        addons, details = self.getSelectedAddons(table)
        if addons and details:
            num_depends = len(details.split("\n")) - 1
            if num_depends == 1:
                plural, plural1 = "this ", " addon?"
            else:
                plural, plural1 = "these ", " addons?"
            text = (
                "Are you sure you want to remove " +
                plural + str(len(addons)) + plural1
            )
            if self.confirmationPrompt(text, details):
                return True, addons
            else:
                return False, addons
        else:
            return False, addons

    def getSelectedAddons(self, table):
        if not table.selectedItems():
            return None, None
        selected_addons = []
        details = ""
        # Column count is minus one because of hidden ID column
        for item in table.selectedItems()[0:: (table.columnCount() - 1)]:
            # Gets db row id for selected row
            selected_row = int((table.item(item.row(), 0)).text())

            selected_name = table.item(item.row(), 1).text()

            for selected_addon in self.c.execute(
                "SELECT InterfaceID, File, Name FROM {table} WHERE rowid = ?".format(  # nosec
                    table=table.objectName()
                ),
                (selected_row,),
            ):
                selected_addons.append(selected_addon)
                details = details + selected_name + "\n"

        return selected_addons, details

    def uninstallPlugins(self, plugins, table: QtWidgets.QTableWidget):
        for plugin in plugins:
            if plugin[1].endswith(".plugin"):
                plugin_files = [Path(plugin[1])]
            else:
                plugin_files = []
                if self.checkAddonForDependencies(plugin, table):
                    doc = defusedxml.minidom.parse(plugin[1])
                    nodes = doc.getElementsByTagName(
                        "Descriptors")[0].childNodes
                    for node in nodes:
                        if node.nodeName == "descriptor":
                            plugin_files.append(
                                self.data_folder_plugins /
                                (GetText(node.childNodes).replace("\\", "/")))

                    # Check for startup scripts to remove them
                    nodes = doc.getElementsByTagName(
                        "PluginConfig")[0].childNodes
                    for node in nodes:
                        if node.nodeName == "StartupScript":
                            script = GetText(node.childNodes)
                            self.uninstallStartupScript(
                                script, self.data_folder_plugins
                            )
                else:
                    continue

            for plugin_file in plugin_files:
                if plugin_file.exists():
                    doc = defusedxml.minidom.parse(str(plugin_file))
                    nodes = doc.getElementsByTagName("Plugin")[0].childNodes
                    for node in nodes:
                        if node.nodeName == "Package":
                            plugin_folder = (self.data_folder_plugins / (
                                "/".join(GetText(node.childNodes).split(".")[0:2])))

                            # Removes plugin and all related files
                            if plugin_folder.exists():
                                rmtree(plugin_folder)

                    plugin_file.unlink(missing_ok=True)
            Path(plugin[1]).unlink(missing_ok=True)

            # Remove author folder if there are no other plugins in it
            author_dir = plugin_folder.parent
            if not list(author_dir.glob("*")):
                author_dir.rmdir()

            logger.info(f"{plugin} plugin uninstalled")

            self.setRemoteAddonToUninstalled(
                plugin, self.ui.tablePlugins)

        # Reloads plugins
        table.clearContents()
        self.getInstalledPlugins()

    def uninstallSkins(self, skins, table: QtWidgets.QTableWidget):
        for skin in skins:
            if skin[1].endswith(".skincompendium"):
                skin_path = Path(skin[1]).parent

                items_row = self.parseCompendiumFile(
                    Path(skin[1]), "SkinConfig")
                script = items_row[8]
                self.uninstallStartupScript(script, self.data_folder_skins)
            else:
                skin_path = Path(skin[1])
            rmtree(skin_path)

            logger.info(f"{skin} skin uninstalled")

            self.setRemoteAddonToUninstalled(
                skin, self.ui.tableSkins)

        # Reloads skins
        table.clearContents()
        self.getInstalledSkins()

    def uninstallMusic(self, music_list, table):
        for music in music_list:
            if music[1].endswith(".musiccompendium"):
                music_path = Path(music[1]).parent

                items_row = self.parseCompendiumFile(
                    Path(music[1]), "MusicConfig")
                script = items_row[8]
                self.uninstallStartupScript(script, self.data_folder_music)
            else:
                music_path = Path(music[1])

            if music_path.suffix == ".abc":
                music_path.unlink()
            else:
                rmtree(music_path)

            logger.info(f"{music} music uninstalled")

            self.setRemoteAddonToUninstalled(
                music, self.ui.tableMusic)

        # Reloads music
        table.clearContents()
        self.getInstalledMusic()

    def checkAddonForDependencies(self, addon, table: QtWidgets.QTableWidget):
        # Turbine Utilities is treated as having ID 0
        addon_ID = "0" if addon[0] == "1064" else addon[0]
        details = ""

        for dependent in self.c.execute(
            'SELECT Name, Dependencies FROM {table} WHERE Dependencies != ""'.format(  # nosec
                table=table.objectName()
            )
        ):
            for dependency in dependent[1].split(","):
                if dependency == addon_ID:
                    details = details + dependent[0] + "\n"

        if details:
            num_depends = len(details.split("\n")) - 1
            plural = " addon depends" if num_depends == 1 else " addons deppend"
            text = (
                str(num_depends)
                + plural
                + " on "
                + addon[2]
                + ". Are you sure you want to remove it?"
            )
            return self.confirmationPrompt(text, details)
        else:
            return True

    def confirmationPrompt(self, text, details):
        messageBox = QtWidgets.QMessageBox(self)
        messageBox.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        messageBox.setIcon(QtWidgets.QMessageBox.Question)
        messageBox.setStandardButtons(messageBox.Apply | messageBox.Cancel)

        messageBox.setInformativeText(text)
        messageBox.setDetailedText(details)

        # Checks if user accepts dialogue
        return messageBox.exec() == 33554432

    def searchSearchBarContents(self):
        """
            Used to re-search users' search when new tabs are selected
        """
        user_search = self.ui.txtSearchBar.text()
        self.txtSearchBarTextChanged(user_search)

    def tabWidgetInstalledIndexChanged(self, index):
        self.updateAddonFolderActions(index)

        # Load in installed skins on first switch to tab
        if index == 1:
            self.loadSkinsIfNotDone()

        # Load in installed music on first switch to tab
        if index == 2:
            self.loadMusicIfNotDone()

        self.searchSearchBarContents()

    def loadSkinsIfNotDone(self):
        if self.isTableEmpty(self.ui.tableSkinsInstalled):
            self.getInstalledSkins()

    def loadMusicIfNotDone(self):
        if self.isTableEmpty(self.ui.tableMusicInstalled):
            self.getInstalledMusic()

    def tabWidgetRemoteIndexChanged(self, index):
        self.updateAddonFolderActions(index)

        self.searchSearchBarContents()

    def tabWidgetIndexChanged(self, index):
        if index == 0:
            self.ui.btnAddons.setText("\uf068")
            self.ui.btnAddons.setToolTip("Remove addons")

            index_installed = self.ui.tabWidgetInstalled.currentIndex()
            self.updateAddonFolderActions(index_installed)
        elif index == 1:
            self.ui.btnAddons.setText("\uf067")
            self.ui.btnAddons.setToolTip("Install addons")

            index_remote = self.ui.tabWidgetRemote.currentIndex()
            self.updateAddonFolderActions(index_remote)

            # Populates remote addons tables if not done already
            if (
                self.isTableEmpty(self.ui.tableSkins)
                and self.loadRemoteAddons()
            ):
                self.getOutOfDateAddons()

        self.searchSearchBarContents()

    def loadRemoteAddons(self):
        if game_settings.current_game.game_type == "LOTRO":
            # Only keep loading remote add-ons if the first load doesn't run
            # into issues
            if self.getRemoteAddons(
                self.PLUGINS_URL, self.ui.tablePlugins
            ):
                self.getRemoteAddons(
                    self.SKINS_URL, self.ui.tableSkins)
                self.getRemoteAddons(
                    self.MUSIC_URL, self.ui.tableMusic)
                return True
        else:
            if self.getRemoteAddons(
                self.SKINS_DDO_URL, self.ui.tableSkins
            ):
                return True

    def getRemoteAddons(self, favorites_url, table):
        # Clears rows from db table
        self.c.execute(f"DELETE FROM {table.objectName()}")  # nosec

        # Gets list of Interface IDs for installed addons
        installed_IDs = []
        for ID in self.c.execute(
            "SELECT InterfaceID FROM {table}".format(  # nosec
                table=table.objectName() + "Installed"
            )
        ):
            if ID[0]:
                installed_IDs.append(ID[0])

        try:
            addons_file = urllib.request.urlopen(  # nosec
                favorites_url).read().decode()
        except (urllib.error.URLError, urllib.error.HTTPError) as error:
            logger.error(error.reason, exc_info=True)
            self.addLog(
                "There was a network error. You may want to check your connection."
            )
            self.ui.tabWidget.setCurrentIndex(0)
            return False

        doc = defusedxml.minidom.parseString(addons_file)
        tags = doc.getElementsByTagName("Ui")
        for tag in tags:
            items_row = [""] * (len(self.COLUMN_LIST) - 1)
            nodes = tag.childNodes
            for node in nodes:
                if node.nodeName == "UIName":
                    items_row[0] = GetText(node.childNodes)
                    # Sanitize
                    items_row[0] = items_row[0].replace(
                        '/', '-').replace('\\', '-')
                elif node.nodeName == "UIAuthorName":
                    items_row[3] = GetText(node.childNodes)
                elif node.nodeName == "UICategory":
                    items_row[1] = GetText(node.childNodes)
                elif node.nodeName == "UID":
                    items_row[6] = GetText(node.childNodes)
                elif node.nodeName == "UIVersion":
                    items_row[2] = GetText(node.childNodes)
                elif node.nodeName == "UIUpdated":
                    items_row[4] = strftime(
                        "%Y-%m-%d", localtime(int(GetText(node.childNodes)))
                    )
                elif node.nodeName == "UIFileURL":
                    items_row[5] = GetText(node.childNodes)

            # Prepends name with (Installed) if already installed
            if items_row[6] in installed_IDs:
                items_row[0] = "(Installed) " + items_row[0]

            self.addRowToDB(table, items_row)

        # Populate user visible table. This should not reload the current
        # search.
        self.searchDB(table, "")

        return True

    # Downloads file from url to path and shows progress with
    # self.handleDownloadProgress
    def downloader(self, url, path):
        if url.lower().startswith("http"):
            try:
                urllib.request.urlretrieve(  # nosec
                    url, path, self.handleDownloadProgress
                )
            except (urllib.error.URLError, urllib.error.HTTPError) as error:
                logger.error(error.reason, exc_info=True)
                self.addLog(
                    "There was a network error. You may want to check your connection."
                )
                return False
        else:
            raise ValueError from None

        self.ui.progressBar.setValue(0)
        return True

    def handleDownloadProgress(self, index, frame, size):
        # Updates progress bar with download progress
        percent = 100 * index * frame // size
        self.ui.progressBar.setValue(percent)

    def Run(self):
        self.exec()
        self.closeDB()

    def contextMenuRequested(self, cursor_position):
        global_cursor_position = self.mapToGlobal(
            cursor_position)

        # It is not a local variable, because of garbage collection
        self.contextMenu = self.getContextMenu(
            global_cursor_position)
        if self.contextMenu:
            self.contextMenu.popup(global_cursor_position)

    def getContextMenu(self, global_cursor_position):
        menu = QtWidgets.QMenu()

        selected_widget = QtWidgets.QApplication.instance().widgetAt(
            global_cursor_position
        )

        parent_widget = selected_widget.parent()
        if parent_widget.objectName().startswith("table"):
            self.context_menu_selected_table = parent_widget
            selected_item = self.context_menu_selected_table.itemAt(
                selected_widget.mapFromGlobal(global_cursor_position)
            )
            if selected_item:
                self.context_menu_selected_row = selected_item.row()

                # If addon has online page
                self.context_menu_selected_interface_ID = self.getTableRowInterfaceID(
                    self.context_menu_selected_table, self.context_menu_selected_row)
                if self.context_menu_selected_interface_ID:
                    menu.addAction(
                        self.ui.actionShowOnLotrointerface)

                # If addon is installed
                if self.context_menu_selected_table.objectName().endswith("Installed"):
                    menu.addAction(self.ui.actionUninstallAddon)
                    menu.addAction(
                        self.ui.actionShowAddonInFileManager)
                else:
                    # If addon in remote table is installed
                    if (
                        selected_item.background().color()
                        == self.installed_addons_color
                    ):
                        menu.addAction(
                            self.ui.actionUninstallAddon)
                        menu.addAction(
                            self.ui.actionShowAddonInFileManager
                        )
                    else:
                        menu.addAction(self.ui.actionInstallAddon)

                # If addon has a new version available
                version_item = self.context_menu_selected_table.item(
                    self.context_menu_selected_row, 3
                )
                version_color = version_item.foreground().color()
                if version_color in [
                        QtGui.QColor("crimson"),
                        QtGui.QColor("green")]:
                    menu.addAction(self.ui.actionUpdateAddon)

                # If addon has a statup script
                if self.context_menu_selected_interface_ID:
                    relative_script_path = self.getRelativeStartupScriptFromInterfaceID(
                        self.context_menu_selected_table, self.context_menu_selected_interface_ID, )
                    if relative_script_path:
                        # If startup script is enabled
                        if relative_script_path in game_settings.current_game.startup_scripts:
                            menu.addAction(
                                self.ui.actionDisableStartupScript)
                        else:
                            menu.addAction(
                                self.ui.actionEnableStartupScript)

        # Only return menu if something has been added to it
        if not menu.isEmpty():
            return menu
        else:
            return None

    def getTableRowInterfaceID(
            self,
            table: QtWidgets.QTableWidget,
            row: int) -> Optional[str]:
        addon_db_id = table.item(row, 0).text()

        for interface_ID in self.c.execute(
            # nosec
            f"SELECT InterfaceID FROM {table.objectName()} WHERE rowid = ?",
            (addon_db_id,),
        ):
            if interface_ID[0]:
                return interface_ID[0]
            else:
                return None

    def actionShowOnLotrointerfaceSelected(self):
        table = self.context_menu_selected_table
        row = self.context_menu_selected_row
        addon_info = self.getAddonListObjectFromRow(table, row)
        if addon_info:
            interface_ID = addon_info[0]
        else:
            return

        url = self.getAddonUrlFromInterfaceID(interface_ID, table)

        if url:
            QtGui.QDesktopServices.openUrl(url)

    def getAddonUrlFromInterfaceID(
            self,
            interface_ID: str,
            table: QtWidgets.QTableWidget,
            download_url: bool = False) -> str:
        """Returns info URL for addon or download URL if download_url=True"""
        # URL is only in remote version of table
        table = self.getRemoteOrLocalTableFromOne(table, remote=True)

        for addon_url in self.c.execute(
            "SELECT File FROM {table} WHERE InterfaceID = ?".format(  # nosec
                table=table.objectName()
            ),
            (interface_ID,),
        ):
            if addon_url[0]:
                return (
                    addon_url[0]
                    if download_url
                    else self.getInterfaceInfoUrl(addon_url[0])
                )

    def getAddonFileFromInterfaceID(self, interface_ID, table):
        """Returns file location of addon"""
        # File is only in "Installed" version of table. The "File" field
        # has the download url in the remote tables.
        table = self.getRemoteOrLocalTableFromOne(table, remote=False)

        for file in self.c.execute(
            "SELECT File FROM {table} WHERE InterfaceID = ?".format(  # nosec
                table=table.objectName()
            ),
            (interface_ID,),
        ):
            if file[0]:
                return file[0]

    def showSelectedOnLotrointerface(self):
        table = self.getCurrentTable()
        selected_addons = self.getSelectedAddons(table)

        if selected_addons[0]:
            for addon in selected_addons[0]:
                info_url = self.getAddonUrlFromInterfaceID(
                    addon[0], table, download_url=False
                )
                QtGui.QDesktopServices.openUrl(info_url)

    def actionInstallAddonSelected(self):
        """
        Installs addon selected by context menu. This function
        should only be called while in one of the remote/find more
        tabs of the UI.
        """
        table = self.context_menu_selected_table
        row = self.context_menu_selected_row
        addon = self.getAddonListObjectFromRow(table, row)
        if not addon:
            return

        self.installRemoteAddon(addon[1], addon[2], addon[0])
        self.setRemoteAddonToInstalled(addon, table)

        self.resetRemoteAddonsTables()
        self.searchSearchBarContents()

    def actionUninstallAddonSelected(self):
        table = self.context_menu_selected_table
        row = self.context_menu_selected_row
        addon = self.getAddonListObjectFromRow(table, row, remote=False)
        if not addon:
            return

        if self.confirmationPrompt(
            "Are you sure you want to uninstall this addon?", addon[2]
        ):
            uninstall_function = self.getUninstallFunctionFromTable(table)

            table_installed = self.getRemoteOrLocalTableFromOne(
                table, remote=False)
            uninstall_function([addon], table_installed)

            self.resetRemoteAddonsTables()
            self.searchSearchBarContents()

    def getAddonListObjectFromRow(
        self, table: QtWidgets.QTableWidget, row, remote=True
    ):
        """
        Gives list of information for addon. The information is:
        [Interface ID, URL/File (depending on if remote = True or False), Name]
        """
        interface_ID = self.getTableRowInterfaceID(table, row)
        if not interface_ID:
            return

        if remote:
            table_remote = self.getRemoteOrLocalTableFromOne(
                table, remote=True)
            file = self.getAddonUrlFromInterfaceID(
                interface_ID, table_remote, download_url=True
            )
        else:
            table_installed = self.getRemoteOrLocalTableFromOne(
                table, remote=False)

            if table.objectName().endswith("Installed"):
                self.reloadSearch(table_installed)

                for item in self.c.execute(
                    "SELECT File FROM {table} WHERE rowid=?".format(  # nosec
                        table=table_installed.objectName()
                    ),
                    (table_installed.item(row, 0).text(),),
                ):
                    file = item[0]
            else:
                file = self.getAddonFileFromInterfaceID(
                    interface_ID, table_installed)

        return [interface_ID, file, table.item(row, 1).text()]

    def getRemoteOrLocalTableFromOne(
        self, input_table: QtWidgets.QTableWidget, remote: bool = False
    ):
        table_name = input_table.objectName()
        # UI table object names are renamed with DDO in them when the current game is
        # DDO for DB access, but the callable name for the UI tables stays the
        # same.
        table_name = table_name.replace("DDO", "")

        if remote:
            table = getattr(self.ui,
                            table_name.split("Installed")[0])
        else:
            if table_name.endswith("Installed"):
                table = input_table
            else:
                table = getattr(self.ui, table_name + "Installed")

        return table

    def actionShowAddonInFileManagerSelected(self):
        table = self.context_menu_selected_table
        row = self.context_menu_selected_row
        addon = self.getAddonListObjectFromRow(table, row, remote=False)
        if not addon:
            return

        if Path(addon[1]).is_file():
            addon_folder = Path(addon[1]).parent
        else:
            addon_folder = Path(addon[1])
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(addon_folder)))

    def actionShowPluginsFolderSelected(self):
        folder = self.data_folder_plugins
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

    def actionShowSkinsFolderSelected(self):
        folder = self.data_folder_skins
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

    def actionShowMusicFolderSelected(self):
        folder = self.data_folder_music
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

    def updateAddonFolderActions(self, index):
        """
        Makes action for opening addon folder associated with
        current tab the only addon folder opening action visible.
        """
        if game_settings.current_game.game_type == "DDO" or index == 1:
            self.ui.actionShowPluginsFolderInFileManager.setVisible(
                False)
            self.ui.actionShowSkinsFolderInFileManager.setVisible(
                True)
            self.ui.actionShowMusicFolderInFileManager.setVisible(
                False)
        elif index == 0:
            self.ui.actionShowPluginsFolderInFileManager.setVisible(
                True)
            self.ui.actionShowSkinsFolderInFileManager.setVisible(
                False)
            self.ui.actionShowMusicFolderInFileManager.setVisible(
                False)
        elif index == 2:
            self.ui.actionShowPluginsFolderInFileManager.setVisible(
                False)
            self.ui.actionShowSkinsFolderInFileManager.setVisible(
                False)
            self.ui.actionShowMusicFolderInFileManager.setVisible(
                True)

    def checkForUpdates(self):
        if self.loadRemoteAddons():
            self.getOutOfDateAddons()
            self.searchSearchBarContents()

    def getOutOfDateAddons(self):
        """
        Marks addons as out of date in database with '(Outdated) '
        in installed table and '(Updated) ' in remote table. These
        are prepended to the Version column.
        """
        if not self.loadRemoteDataIfNotDone():
            return

        if game_settings.current_game.game_type != "DDO":
            self.loadSkinsIfNotDone()
            self.loadMusicIfNotDone()

        if game_settings.current_game.game_type == "LOTRO":
            tables = self.TABLE_LIST[:3]
        else:
            tables = ["tableSkinsInstalled"]

        for db_table in tables:
            table_installed = getattr(self.ui, db_table)
            table_remote = self.getRemoteOrLocalTableFromOne(
                table_installed, remote=True
            )

            addons_info_remote = {
                addon[1]: (addon[0], addon[2])
                for addon in self.c.execute(
                    # nosec
                    "SELECT Version, InterfaceID, rowid FROM {table_remote} WHERE"
                    " Name LIKE '(Installed) %'".format(
                        table_remote=table_remote.objectName()
                    )
                )
            }

            out_of_date_addons = []
            for addon in self.c.execute(
                # nosec
                "SELECT Version, InterfaceID, rowid FROM {table_installed} WHERE"
                " InterfaceID != ''".format(
                    table_installed=table_installed.objectName()
                )
            ):
                # Will raise KeyError if addon has Interface ID that isn't in
                # remote table.
                try:
                    remote_addon_info = addons_info_remote[addon[1]]
                except KeyError:
                    continue

                latest_version = remote_addon_info[0]
                if addon[0] != latest_version:
                    rowid_remote = remote_addon_info[1]
                    out_of_date_addons.append(
                        (addon[2], rowid_remote, table_installed))

            for addon in out_of_date_addons:
                self.markAddonForUpdating(addon[0], addon[1], addon[2])

    def markAddonForUpdating(self, rowid_local, rowid_remote, table_installed):
        """
        Marks addon as having having updates
        available in installed and remote tables
        """
        table_remote = self.getRemoteOrLocalTableFromOne(
            table_installed, remote=True)

        self.c.execute(
            (
                "UPDATE {table} SET Version=('(Outdated) ' || Version) WHERE rowid=?".format(  # nosec
                    table=table_installed.objectName()
                )
            ),
            (str(rowid_local),),
        )
        self.c.execute(
            (
                "UPDATE {table} SET Version=('(Updated) ' || Version) WHERE rowid=?".format(  # nosec
                    table=table_remote.objectName()
                )
            ),
            (str(rowid_remote),),
        )

    def updateAll(self):
        if not self.loadRemoteDataIfNotDone():
            return

        if game_settings.current_game.game_type == "LOTRO":
            tables = self.TABLE_LIST[:3]
        else:
            tables = ["tableSkinsInstalled"]

        for db_table in tables:
            table = getattr(self.ui, db_table)
            for addon in self.c.execute(
                "SELECT InterfaceID, File, Name FROM {table} WHERE"  # nosec
                " Version LIKE '(Outdated) %'".format(table=table.objectName())
            ):
                self.updateAddon(addon, table)

        self.resetRemoteAddonsTables()
        self.searchSearchBarContents()

    def updateAddon(self, addon, table):
        uninstall_function = self.getUninstallFunctionFromTable(table)
        table_installed = self.getRemoteOrLocalTableFromOne(
            table, remote=False)
        table_remote = self.getRemoteOrLocalTableFromOne(table, remote=True)

        uninstall_function([addon], table_installed)

        for entry in self.c.execute(
            "SELECT File FROM {table} WHERE"  # nosec
            " InterfaceID = ?".format(table=table_remote.objectName()),
            (addon[0],),
        ):
            url = entry[0]
        self.installRemoteAddon(url, addon[2], addon[0])
        self.setRemoteAddonToInstalled(addon, table_remote)

    def actionUpdateAddonSelected(self):
        if not self.loadRemoteDataIfNotDone():
            return

        table = self.context_menu_selected_table
        row = self.context_menu_selected_row
        addon = self.getAddonListObjectFromRow(table, row, remote=False)

        self.updateAddon(addon, table)

        self.resetRemoteAddonsTables()
        self.searchSearchBarContents()

    def updateAllSelectedAddons(self):
        table = self.getCurrentTable()
        addons, details = self.getSelectedAddons(table)

        if not self.loadRemoteDataIfNotDone():
            return

        if addons:
            for addon in addons:
                if self.checkIfAddonHasUpdate(addon, table):
                    self.updateAddon(addon, table)

            self.resetRemoteAddonsTables()
            self.searchSearchBarContents()

    def checkIfAddonHasUpdate(self, addon, table):
        for entry in self.c.execute(
            "SELECT Version FROM {table} WHERE InterfaceID = ?".format(  # nosec
                table=table.objectName()
            ),
            (addon[0],),
        ):
            version = entry[0]
            return bool(
                version.startswith(
                    "(Outdated) ") or version.startswith("(Updated) ")
            )

    def loadRemoteDataIfNotDone(self):
        """
        Loads remote addons and checks if addons have updates if not done yet
        """
        # If remote addons haven't been loaded then out of date addons haven't
        # been found.
        if (
            self.isTableEmpty(self.ui.tableSkins)
            and self.loadRemoteAddons()
        ):
            self.getOutOfDateAddons()

        return True

    def actionEnableStartupScriptSelected(self):
        if not self.context_menu_selected_interface_ID:
            return
        script = self.getRelativeStartupScriptFromInterfaceID(
            self.context_menu_selected_table, self.context_menu_selected_interface_ID)
        full_script_path = self.data_folder / script
        if full_script_path.exists():
            game_settings.current_game.startup_scripts.append(script)
        else:
            self.addLog(
                f"'{full_script_path}' startup script does not exist, so it could not be enabled."
            )

    def actionDisableStartupScriptSelected(self):
        if self.context_menu_selected_interface_ID:
            script = self.getRelativeStartupScriptFromInterfaceID(
                self.context_menu_selected_table, self.context_menu_selected_interface_ID)
            game_settings.current_game.startup_scripts.remove(script)

    def getRelativeStartupScriptFromInterfaceID(
        self, table: QtWidgets.QTableWidget, interface_ID: str
    ) -> Path:
        """Returns path of startup script relative to game documents settings directory"""
        table_local = self.getRemoteOrLocalTableFromOne(table, remote=False)
        for entry in self.c.execute(
            # nosec
            f"SELECT StartupScript FROM {table_local.objectName()} WHERE InterfaceID = ?",
            (interface_ID,),
        ):
            if entry[0]:
                script = entry[0].replace("\\", "/")
                addon_data_folder_relative = Path(str(self.getAddonTypeDataFolderFromTable(
                    table_local)).split(str(self.data_folder))[1])

                return addon_data_folder_relative / script

    def getAddonTypeDataFolderFromTable(self, table: QtWidgets.QTableWidget):
        table_name = table.objectName()
        if "Plugins" in table_name:
            return self.data_folder_plugins
        elif "Skins" in table_name:
            return self.data_folder_skins
        elif "Music" in table_name:
            return self.data_folder_music
        else:
            return None

    def handleStartupScriptActivationPrompt(
        self, table: QtWidgets.QTableWidget, interface_ID: str
    ):
        """Asks user if they want to enable an add-on's startup script if present"""
        script = self.getRelativeStartupScriptFromInterfaceID(
            table, interface_ID)
        if script:
            script_contents = (self.data_folder / script).open().read()
            for name in self.c.execute(
                # nosec
                f"SELECT Name from {table.objectName()} WHERE InterfaceID = ?",
                (interface_ID,),
            ):
                addon_name = name[0]

            activate_script = self.confirmationPrompt(
                f"{addon_name} is requesting to run a Python script at every game launch."
                " It is highly recommended to review the script's code in the details"
                " box below to make sure it's safe.", script_contents, )
            if activate_script:
                game_settings.current_game.startup_scripts.append(script)

    def uninstallStartupScript(self, script: str, addon_data_folder: Path):
        if script:
            script_path = addon_data_folder / (script.replace("\\", "/"))

            relative_to_game_documents_dir_script = script_path.relative_to(
                self.data_folder)

            if relative_to_game_documents_dir_script in game_settings.current_game.startup_scripts:
                game_settings.current_game.startup_scripts.remove(
                    relative_to_game_documents_dir_script)

            script_path.unlink(missing_ok=True)
