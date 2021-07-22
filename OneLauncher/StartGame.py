# coding=utf-8
###########################################################################
# Game launcher for OneLauncher.
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
from OneLauncher import Settings
from sys import path
from PySide6 import QtCore, QtWidgets
from PySide6.QtUiTools import QUiLoader
from OneLauncher.OneLauncherUtils import QByteArray2str
from pathlib import Path
import logging


class StartGame:
    def __init__(
        self,
        appName: Path,
        clientType,
        argTemplate,
        account,
        server,
        ticket,
        chatServer,
        language,
        runDir: Path,
        wineProgram: Path,
        wineDebug,
        winePrefix: Path,
        hiResEnabled: bool,
        builtInPrefixEnabled: bool,
        crashreceiver,
        DefaultUploadThrottleMbps,
        bugurl,
        authserverurl,
        supporturl,
        supportserviceurl,
        glsticketlifetime,
        worldName,
        accountText,
        parent,
        data_folder: Path,
        startupScripts,
        gameConfigDir: Path,
    ):

        # Fixes binary path for 64-bit client
        if clientType == "WIN64":
            appName = "x64"/appName

        self.worldName = worldName
        self.accountText = accountText
        self.parent = parent
        self.logger = logging.getLogger("main")
        self.startupScripts = startupScripts
        self.gameConfigDirPath = Settings.documentsDir/gameConfigDir

        self.winLog = QUiLoader().load(str(data_folder/"ui/winLog.ui"), parentWidget=parent)
        self.winLog.setWindowFlags(
            QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)

        if Settings.usingWindows:
            self.winLog.setWindowTitle("Output")
        else:
            self.winLog.setWindowTitle("Launch Game - Wine output")

        # self.winLog.btnStart.setVisible(False)
        self.winLog.btnStart.setText("Back")
        self.winLog.btnStart.setEnabled(False)
        self.winLog.btnSave.setText("Save")
        self.winLog.btnSave.setEnabled(False)
        self.winLog.btnStop.setText("Exit")
        self.winLog.btnStart.clicked.connect(self.btnStartClicked)
        self.winLog.btnSave.clicked.connect(self.btnSaveClicked)
        self.winLog.btnStop.clicked.connect(self.btnStopClicked)

        self.aborted = False
        self.finished = False
        self.command = ""
        self.arguments = []

        gameParams = (
            argTemplate.replace("{SUBSCRIPTION}", account)
            .replace("{LOGIN}", server)
            .replace("{GLS}", ticket)
            .replace("{CHAT}", chatServer)
            .replace("{LANG}", language)
            .replace("{CRASHRECEIVER}", crashreceiver)
            .replace("{UPLOADTHROTTLE}", DefaultUploadThrottleMbps)
            .replace("{BUGURL}", bugurl)
            .replace("{AUTHSERVERURL}", authserverurl)
            .replace("{GLSTICKETLIFETIME}", glsticketlifetime)
            .replace("{SUPPORTURL}", supporturl)
            .replace("{SUPPORTSERVICEURL}", supportserviceurl)
        )

        if not hiResEnabled:
            gameParams += " --HighResOutOfDate"

        self.process = QtCore.QProcess()
        self.process.readyReadStandardOutput.connect(self.readOutput)
        self.process.readyReadStandardError.connect(self.readErrors)
        self.process.finished.connect(self.resetButtons)

        if Settings.usingWindows:
            self.command = str(appName)
            self.process.setWorkingDirectory(str(runDir))

            for arg in gameParams.split(" "):
                self.arguments.append(arg)

        else:
            processEnvironment = QtCore.QProcessEnvironment.systemEnvironment()

            if wineDebug != "":
                processEnvironment.insert("WINEDEBUG", wineDebug)

            if winePrefix != "":
                processEnvironment.insert("WINEPREFIX", str(winePrefix))

            self.command = str(wineProgram)
            self.process.setWorkingDirectory(str(runDir))

            self.arguments.append(str(appName))

            for arg in gameParams.split(" "):
                self.arguments.append(arg)

            # Applies needed settings for the builtin wine prefix
            if builtInPrefixEnabled:
                # Enables ESYNC if open file limit is high enough
                path = Path("/proc/sys/fs/file-max")
                if path.exists():
                    with path.open() as file:
                        file_data = file.read()
                        if int(file_data) >= 524288:
                            processEnvironment.insert("WINEESYNC", "1")

                # Enables FSYNC. It overides ESYNC and will only be used if
                # the required kernel patches are installed.
                processEnvironment.insert("WINEFSYNC", "1")

                # Adds dll overrides for DirectX, so DXVK is used instead of wine3d
                processEnvironment.insert(
                    "WINEDLLOVERRIDES", "d3d11=n;dxgi=n;d3d10=n")

            self.process.setProcessEnvironment(processEnvironment)

        self.winLog.txtLog.append("Connecting to server: " + worldName)
        self.winLog.txtLog.append("Account: " + accountText)
        self.winLog.txtLog.append("Game Directory: " + str(runDir))
        self.winLog.txtLog.append("Game Client: " + str(appName))

        self.winLog.show()

        self.runStatupScripts()

    def readOutput(self):
        text = QByteArray2str(self.process.readAllStandardOutput())
        self.winLog.txtLog.append(text)
        self.logger.debug("Game: " + text)

    def readErrors(self):
        text = QByteArray2str(self.process.readAllStandardError())
        self.winLog.txtLog.append(text)
        self.logger.debug("Game: " + text)

    def resetButtons(self, exitCode, exitStatus):
        self.finished = True
        self.winLog.btnStop.setText("Exit")
        self.winLog.btnSave.setEnabled(True)
        self.winLog.btnStart.setEnabled(True)
        if self.aborted:
            self.winLog.txtLog.append("<b>***  Aborted  ***</b>")
        else:
            self.winLog.txtLog.append("<b>***  Finished  ***</b>")

    def btnStartClicked(self):
        if self.finished:
            self.winLog.close()

    def btnStopClicked(self):
        if self.finished:
            self.parent.close()
        else:
            self.aborted = True
            self.process.kill()

    # Saves a file with the debug log generated by running the game
    def btnSaveClicked(self):
        filename = QtWidgets.QFileDialog.getSaveFileName(
            self.winLog, "Save log file", str(Settings.platform_dirs.user_log_dir)
        )[0]

        if filename != "":
            with open(filename, "w") as outfile:
                outfile.write(self.winLog.txtLog.toPlainText())

    def runStatupScripts(self):
        """Runs Python scripts from add-ons with one that is approved by user"""
        for script in self.startupScripts:
            file_path = self.gameConfigDirPath/script
            if file_path.exists():
                self.winLog.txtLog.append(
                    f"Running '{script}' startup script...")

                with file_path.open() as file:
                    code = file.read()

                try:
                    exec(code, {"__file__": str(file_path)})
                except SyntaxError as e:
                    self.winLog.txtLog.append(
                        f"'{script}' ran into syntax error: {e}")
            else:
                self.winLog.txtLog.append(
                    f"'{script}' startup script does not exist")

    def Run(self):
        self.finished = False

        self.winLog.btnStop.setText("Abort")
        self.process.start(self.command, self.arguments)
        self.logger.info("Game started with: " +
                         str([self.command, self.arguments]))

        return self.winLog.exec_()
