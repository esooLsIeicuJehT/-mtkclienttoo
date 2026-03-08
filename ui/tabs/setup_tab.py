"""
Setup Tab — automated environment setup for Fedora, Ubuntu, Windows.
"""
import platform
import subprocess
import shutil
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QTextEdit, QProgressBar,
    QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from utils.platform_setup import PlatformSetup


class SetupWorker(QThread):
    log     = pyqtSignal(str)
    done    = pyqtSignal(bool)

    def __init__(self, cmd: str):
        super().__init__()
        self.cmd = cmd

    def run(self):
        try:
            proc = subprocess.Popen(
                self.cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True
            )
            for line in proc.stdout:
                self.log.emit(line.rstrip())
            proc.wait()
            self.done.emit(proc.returncode == 0)
        except Exception as e:
            self.log.emit(f"Error: {e}")
            self.done.emit(False)


class SetupTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup = PlatformSetup()
        self._worker = None
        self._build_ui()
        self._run_diagnostics()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Platform Info ─────────────────────────────────────────────────────
        sys_box = QGroupBox("System")
        sys_layout = QVBoxLayout(sys_box)
        self.sys_lbl = QLabel()
        self.sys_lbl.setStyleSheet("color:#80a0b8;")
        sys_layout.addWidget(self.sys_lbl)
        layout.addWidget(sys_box)

        # ── Diagnostics ───────────────────────────────────────────────────────
        diag_box = QGroupBox("Prerequisites Check")
        diag_layout = QVBoxLayout(diag_box)
        self.diag_output = QTextEdit()
        self.diag_output.setReadOnly(True)
        self.diag_output.setMaximumHeight(150)
        btn_check = QPushButton("⟳  Re-check")
        btn_check.clicked.connect(self._run_diagnostics)
        diag_layout.addWidget(self.diag_output)
        diag_layout.addWidget(btn_check)
        layout.addWidget(diag_box)

        # ── Install Commands ──────────────────────────────────────────────────
        install_box = QGroupBox("One-Click Install")
        install_layout = QVBoxLayout(install_box)

        system = platform.system()

        if system == "Linux":
            distro = self._detect_distro()
            if "fedora" in distro or "rhel" in distro or "centos" in distro:
                cmd = "sudo dnf install -y python3 python3-pip python3-pyqt5 libusb1 python3-pyserial && pip3 install pyusb requests cryptography --break-system-packages"
                self._add_install_btn(install_layout, "Install Dependencies (Fedora/RHEL)", cmd)
                udev_cmd = "echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0e8d\", MODE=\"0666\", GROUP=\"plugdev\", TAG+=\"uaccess\"' | sudo tee /etc/udev/rules.d/51-mtk-devices.rules && sudo udevadm control --reload-rules"
                self._add_install_btn(install_layout, "Install udev Rules", udev_cmd)
                mm_cmd = "echo 'SUBSYSTEM==\"usb\", ACTION==\"add\", ATTR{idVendor}==\"0e8d\", ENV{ID_MM_DEVICE_IGNORE}=\"1\"' | sudo tee /etc/udev/rules.d/20-mm-blacklist-mtk.rules && sudo udevadm control --reload-rules"
                self._add_install_btn(install_layout, "Block ModemManager", mm_cmd)
                grp_cmd = f"sudo usermod -aG plugdev,dialout $USER"
                self._add_install_btn(install_layout, "Add User to plugdev/dialout", grp_cmd)
            else:
                # Ubuntu/Debian
                cmd = "sudo apt update && sudo apt install -y python3 python3-pip python3-pyqt5 python3-usb python3-serial libusb-1.0-0"
                self._add_install_btn(install_layout, "Install Dependencies (Debian/Ubuntu)", cmd)

            self._add_install_btn(install_layout, "Install Python deps (pip)",
                                   "pip3 install pyusb pyserial requests cryptography --break-system-packages")
            self._add_install_btn(install_layout, "Stop ModemManager (session)",
                                   "sudo systemctl stop ModemManager")

        elif system == "Windows":
            lbl = QLabel(
                "Windows Setup:\n"
                "1. Install Python 3.10+ from python.org\n"
                "2. Run: pip install -r requirements.txt\n"
                "3. Install UsbDk: https://github.com/daynix/UsbDk/releases\n"
                "4. Install MediaTek VCOM drivers (from firmware folder)\n"
                "5. Install ADB platform-tools for ADB features"
            )
            lbl.setStyleSheet("color:#607080; line-height:160%;")
            install_layout.addWidget(lbl)
            self._add_install_btn(install_layout, "Install Python deps",
                                   "pip install -r requirements.txt")

        layout.addWidget(install_box)

        # ── ADB Setup ─────────────────────────────────────────────────────────
        adb_box = QGroupBox("ADB Platform Tools")
        adb_layout = QVBoxLayout(adb_box)
        adb_status = "✓ Found" if shutil.which("adb") else "✗ Not found (optional)"
        adb_color  = "#00c890" if shutil.which("adb") else "#886600"
        lbl_adb = QLabel(f"ADB: {adb_status}")
        lbl_adb.setStyleSheet(f"color:{adb_color};")
        adb_layout.addWidget(lbl_adb)
        if system == "Linux":
            self._add_install_btn(adb_layout, "Install ADB (Fedora)",
                                   "sudo dnf install -y android-tools")
            self._add_install_btn(adb_layout, "Install ADB (Ubuntu)",
                                   "sudo apt install -y android-tools-adb")
        layout.addWidget(adb_box)

        # ── Command Output ────────────────────────────────────────────────────
        out_box = QGroupBox("Command Output")
        out_layout = QVBoxLayout(out_box)
        self.cmd_output = QTextEdit()
        self.cmd_output.setReadOnly(True)
        self.cmd_output.setObjectName("log_view")
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(6)
        self.progress.setRange(0, 0)
        self.progress.hide()
        out_layout.addWidget(self.cmd_output)
        out_layout.addWidget(self.progress)
        layout.addWidget(out_box, 1)

    def _add_install_btn(self, parent_layout, label: str, cmd: str):
        row = QHBoxLayout()
        lbl = QLabel(f"<code style='color:#304555; font-size:10px'>{cmd[:80]}{'…' if len(cmd)>80 else ''}</code>")
        lbl.setWordWrap(True)
        btn = QPushButton(label)
        btn.clicked.connect(lambda _, c=cmd: self._run_cmd(c))
        row.addWidget(lbl, 1)
        row.addWidget(btn)
        parent_layout.addLayout(row)

    def _detect_distro(self) -> str:
        try:
            with open("/etc/os-release") as f:
                return f.read().lower()
        except Exception:
            return ""

    def _run_diagnostics(self):
        self._setup.ensure_prerequisites()
        status = self._setup.get_status()

        import platform, shutil
        lines = [
            f"OS: {platform.system()} {platform.release()}",
            f"Arch: {platform.machine()}",
            f"Python: {platform.python_version()}",
            f"pyusb: {'✓' if self._check_import('usb') else '✗'}",
            f"PyQt5: {'✓' if self._check_import('PyQt5') else '✗'}",
            f"pyserial: {'✓' if self._check_import('serial') else '✗'}",
            f"ADB: {'✓ ' + shutil.which('adb') if shutil.which('adb') else '✗ not found'}",
        ]

        if status["warnings"]:
            lines.append("\nWarnings:")
            for w in status["warnings"]:
                lines.append(f"  ⚠ {w}")
        if status["issues"]:
            lines.append("\nIssues:")
            for i in status["issues"]:
                lines.append(f"  ✗ {i}")
        if not status["warnings"] and not status["issues"]:
            lines.append("\n✓ All prerequisites met.")

        self.diag_output.setText("\n".join(lines))
        self.sys_lbl.setText(
            f"Platform: {status['system']}  |  "
            f"Status: {'✓ Ready' if status['ready'] else '⚠ Issues detected'}"
        )

    def _check_import(self, name: str) -> bool:
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    def _run_cmd(self, cmd: str):
        self.cmd_output.clear()
        self.progress.show()
        self._worker = SetupWorker(cmd)
        self._worker.log.connect(lambda l: self.cmd_output.append(l))
        self._worker.done.connect(self._cmd_done)
        self._worker.start()

    def _cmd_done(self, ok: bool):
        self.progress.hide()
        self.cmd_output.append(f"\n{'✓ Done.' if ok else '✗ Command failed.'}")
        self._run_diagnostics()
