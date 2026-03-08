"""
Root Assistant Tab — guided rooting workflow.

Supports: Magisk (stable/canary/delta), KernelSU, APatch.

Context Flow:
  Select Root Method → Check BL Status → Backup boot →
  Download App → Push boot → Patch on device → Pull → Flash → Verify
"""
import os
import webbrowser
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QFileDialog,
    QComboBox, QLineEdit, QTextEdit, QMessageBox,
    QProgressBar, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor

from core import FlashEngine, OpType, ADBBridge

# ── Root method database ──────────────────────────────────────────────────────
ROOT_METHODS = {
    "Magisk (Stable)": {
        "url":     "https://github.com/topjohnwu/Magisk/releases/latest",
        "apk_name":"Magisk.apk",
        "patch_path": "/sdcard/Download/magisk_patched*.img",
        "description": (
            "The industry standard. Systemless root with module support, "
            "Zygisk, and universal SafetyNet/Play Integrity bypass via modules. "
            "Best for most users."
        ),
        "pros":  "✓ Most stable  ✓ Largest module ecosystem  ✓ Zygisk built-in",
        "cons":  "✗ Needs boot.img patching  ✗ Detected by some banking apps",
    },
    "Magisk Canary": {
        "url":     "https://github.com/topjohnwu/Magisk/releases",
        "apk_name":"Magisk-canary.apk",
        "patch_path": "/sdcard/Download/magisk_patched*.img",
        "description": (
            "Pre-release Magisk with the latest features. "
            "May be less stable but has newest Zygisk APIs and fixes."
        ),
        "pros":  "✓ Latest features  ✓ Fastest bug fixes",
        "cons":  "✗ May be unstable  ✗ Not recommended for daily driver",
    },
    "Magisk Delta (HuskyDG)": {
        "url":     "https://github.com/HuskyDG/magisk-files/releases",
        "apk_name":"Magisk-delta.apk",
        "patch_path": "/sdcard/Download/magisk_patched*.img",
        "description": (
            "Magisk fork with extra features: built-in SuSFS support, "
            "better GMS/banking app hiding, and MagiskHide re-enabled. "
            "Good for users needing root hiding."
        ),
        "pros":  "✓ Better root hiding  ✓ MagiskHide  ✓ SuSFS",
        "cons":  "✗ Third-party fork  ✗ Smaller community",
    },
    "KernelSU": {
        "url":     "https://github.com/tiann/KernelSU/releases/latest",
        "apk_name":"KernelSU.apk",
        "patch_path": "/sdcard/Download/kernelsu_patched*.img",
        "description": (
            "Kernel-level root solution. Root is granted at the kernel level "
            "rather than userspace — much harder to detect by apps. "
            "Requires a KernelSU-compatible kernel (or patch your own)."
        ),
        "pros":  "✓ Kernel-level root  ✓ Very hard to detect  ✓ No Zygisk needed",
        "cons":  "✗ Needs compatible kernel  ✗ Less module support",
    },
    "APatch": {
        "url":     "https://github.com/bmax121/APatch/releases/latest",
        "apk_name":"APatch.apk",
        "patch_path": "/sdcard/Download/apatch_patched*.img",
        "description": (
            "Android kernel patch system. Patches the kernel directly "
            "from boot.img like Magisk but with kernel-level privilege. "
            "Supports KernelPatch modules and Android modules."
        ),
        "pros":  "✓ Kernel + userspace root  ✓ Works without custom kernel",
        "cons":  "✗ Newer project  ✗ Smaller community than Magisk",
    },
}

BOOT_PARTITION_NAMES = ["boot", "init_boot", "boot_a", "boot_b", "recovery"]


class ADBWorker(QThread):
    """Runs a blocking ADB operation in background."""
    result = pyqtSignal(bool, str)   # (success, message)
    log    = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs

    def run(self):
        try:
            out = self._fn(*self._args, **self._kwargs)
            if isinstance(out, tuple):
                ok, msg = out[0], str(out[1]) if len(out) > 1 else ""
            else:
                ok, msg = bool(out), ""
            self.result.emit(ok, msg)
        except Exception as e:
            self.result.emit(False, str(e))


class RootTab(QWidget):
    """Full root assistant with method selection and guided workflow."""

    # Signal to update the guide panel
    guide_requested = pyqtSignal(str)

    def __init__(self, engine: FlashEngine, adb: ADBBridge, parent=None):
        super().__init__(parent)
        self._engine      = engine
        self._adb         = adb
        self._boot_backup = ""   # path to local boot.img backup
        self._patched_boot= ""   # path to patched boot.img
        self._worker      = None
        self._build_ui()
        self._update_method_info()

    def _build_ui(self):
        # Outer scroll so nothing gets squished
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        scroll.setWidget(inner)
        outer_layout.addWidget(scroll)

        # ── Method Selector ───────────────────────────────────────────────────
        method_box = QGroupBox("Root Method")
        method_layout = QGridLayout(method_box)
        method_layout.setSpacing(8)

        method_layout.addWidget(QLabel("Choose root solution:"), 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItems(list(ROOT_METHODS.keys()))
        self.method_combo.currentTextChanged.connect(self._update_method_info)
        self.method_combo.setMinimumWidth(220)
        method_layout.addWidget(self.method_combo, 0, 1)

        btn_download = QPushButton("🌐  Open Download Page")
        btn_download.setMinimumWidth(200)
        btn_download.setMinimumHeight(34)
        btn_download.clicked.connect(self._open_download)
        method_layout.addWidget(btn_download, 0, 2)

        self.method_desc = QLabel()
        self.method_desc.setWordWrap(True)
        self.method_desc.setStyleSheet("color:#607888; font-size:11px; padding:4px;")
        method_layout.addWidget(self.method_desc, 1, 0, 1, 3)

        self.method_pros = QLabel()
        self.method_pros.setStyleSheet("color:#408050; font-size:11px; padding:2px 4px;")
        self.method_cons = QLabel()
        self.method_cons.setStyleSheet("color:#805040; font-size:11px; padding:2px 4px;")
        method_layout.addWidget(self.method_pros, 2, 0, 1, 3)
        method_layout.addWidget(self.method_cons, 3, 0, 1, 3)
        layout.addWidget(method_box)

        # ── Prerequisites Check ───────────────────────────────────────────────
        prereq_box = QGroupBox("Prerequisites")
        prereq_layout = QVBoxLayout(prereq_box)

        self.bl_status = QLabel("⬤  Bootloader status: unknown")
        self.bl_status.setStyleSheet("color:#607080; font-size:12px;")
        self.adb_status = QLabel("⬤  ADB status: unknown")
        self.adb_status.setStyleSheet("color:#607080; font-size:12px;")

        btn_check = QPushButton("▶  Check Status via ADB")
        btn_check.setMinimumHeight(34)
        btn_check.clicked.connect(self._check_prerequisites)

        prereq_layout.addWidget(self.bl_status)
        prereq_layout.addWidget(self.adb_status)
        prereq_layout.addWidget(btn_check)
        layout.addWidget(prereq_box)

        # ── Workflow Steps ────────────────────────────────────────────────────
        workflow_box = QGroupBox("Root Workflow  —  Follow steps in order")
        workflow_layout = QGridLayout(workflow_box)
        workflow_layout.setSpacing(8)
        workflow_layout.setColumnStretch(1, 1)

        def step_label(n, text):
            lbl = QLabel(f"  Step {n}  ")
            lbl.setStyleSheet(
                "background:#0a1828; color:#00d4ff; font-weight:bold; "
                "border:1px solid #1a3050; border-radius:3px; padding:2px 6px; font-size:11px;"
            )
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(70)
            desc = QLabel(text)
            desc.setStyleSheet("color:#a0b4c8; font-size:12px;")
            return lbl, desc

        # Step 1 — Backup boot
        s1_num, s1_txt = step_label(1, "Backup stock boot.img from device")
        self.boot_path_lbl = QLabel("No backup yet")
        self.boot_path_lbl.setStyleSheet("color:#405060; font-size:11px; font-style:italic;")
        btn_backup_boot = QPushButton("💾  Backup boot.img")
        btn_backup_boot.setMinimumHeight(34)
        btn_backup_boot.setMinimumWidth(180)
        btn_backup_boot.clicked.connect(self._backup_boot)
        workflow_layout.addWidget(s1_num, 0, 0)
        workflow_layout.addWidget(s1_txt, 0, 1)
        workflow_layout.addWidget(self.boot_path_lbl, 1, 1)
        workflow_layout.addWidget(btn_backup_boot, 0, 2)

        self._add_divider(workflow_layout, 2)

        # Step 2 — Transfer to device
        s2_num, s2_txt = step_label(2, "Transfer boot.img to device /sdcard/")
        btn_push_boot = QPushButton("📤  Push boot.img to Device")
        btn_push_boot.setMinimumHeight(34)
        btn_push_boot.setMinimumWidth(180)
        btn_push_boot.clicked.connect(self._push_boot)
        workflow_layout.addWidget(s2_num, 3, 0)
        workflow_layout.addWidget(s2_txt, 3, 1)
        workflow_layout.addWidget(btn_push_boot, 3, 2)

        s2b = QLabel(
            "  → Then open the root manager APK on your phone:\n"
            "     Install → Select and Patch a File → choose /sdcard/boot.img\n"
            "     Wait for patching to complete before continuing."
        )
        s2b.setStyleSheet("color:#506070; font-size:11px; padding-left:10px;")
        workflow_layout.addWidget(s2b, 4, 1, 1, 2)

        self._add_divider(workflow_layout, 5)

        # Step 3 — Pull patched boot
        s3_num, s3_txt = step_label(3, "Pull patched boot.img back from device")
        self.patched_path_lbl = QLabel("No patched file yet")
        self.patched_path_lbl.setStyleSheet("color:#405060; font-size:11px; font-style:italic;")
        btn_pull_boot = QPushButton("📥  Pull Patched boot.img")
        btn_pull_boot.setMinimumHeight(34)
        btn_pull_boot.setMinimumWidth(180)
        btn_pull_boot.clicked.connect(self._pull_patched_boot)
        workflow_layout.addWidget(s3_num, 6, 0)
        workflow_layout.addWidget(s3_txt, 6, 1)
        workflow_layout.addWidget(self.patched_path_lbl, 7, 1)
        workflow_layout.addWidget(btn_pull_boot, 6, 2)

        self._add_divider(workflow_layout, 8)

        # Step 4 — Flash patched boot
        s4_num, s4_txt = step_label(4, "Flash patched boot.img to device")
        s4_warn = QLabel(
            "  ⚠  Device must be in BROM/Preloader mode — connect via MTK Client first."
        )
        s4_warn.setStyleSheet("color:#806020; font-size:11px; padding-left:10px;")
        btn_flash_boot = QPushButton("⚡  Flash Patched boot.img")
        btn_flash_boot.setObjectName("btn_flash")
        btn_flash_boot.setMinimumHeight(38)
        btn_flash_boot.setMinimumWidth(200)
        btn_flash_boot.clicked.connect(self._flash_patched_boot)
        workflow_layout.addWidget(s4_num, 9, 0)
        workflow_layout.addWidget(s4_txt, 9, 1)
        workflow_layout.addWidget(s4_warn, 10, 1)
        workflow_layout.addWidget(btn_flash_boot, 9, 2)

        self._add_divider(workflow_layout, 11)

        # Step 5 — Verify
        s5_num, s5_txt = step_label(5, "Verify root is working")
        self.verify_output = QLabel("—")
        self.verify_output.setStyleSheet("color:#607888; font-size:11px; padding-left:4px;")
        btn_verify = QPushButton("✅  Verify via ADB")
        btn_verify.setMinimumHeight(34)
        btn_verify.setMinimumWidth(180)
        btn_verify.clicked.connect(self._verify_root)
        workflow_layout.addWidget(s5_num, 12, 0)
        workflow_layout.addWidget(s5_txt, 12, 1)
        workflow_layout.addWidget(self.verify_output, 13, 1)
        workflow_layout.addWidget(btn_verify, 12, 2)

        layout.addWidget(workflow_box)

        # ── Extra Tools ───────────────────────────────────────────────────────
        extra_box = QGroupBox("Extra Root Tools")
        extra_layout = QGridLayout(extra_box)
        extra_layout.setSpacing(8)

        tools = [
            ("Install Magisk APK via ADB",   self._adb_install_magisk,
             "Installs the Magisk APK directly via ADB without touching storage."),
            ("Check su binary",               self._check_su,
             "Runs 'su -c id' via ADB to confirm su access is working."),
            ("Check Zygisk status",           self._check_zygisk,
             "Checks if Zygisk is active via Magisk module list."),
            ("Install LSPosed (Zygisk)",      self._install_lsposed,
             "Opens the LSPosed download page — the most popular Xposed framework for Zygisk."),
            ("Check SafetyNet / Play Integrity",self._check_safetynet,
             "Runs a basic SafetyNet check via ADB shell."),
            ("Restore stock boot (unroot)",   self._restore_stock_boot,
             "Flashes the stock boot.img backup back to remove root."),
        ]
        for i, (label, fn, tip) in enumerate(tools):
            btn = QPushButton(label)
            btn.setMinimumHeight(32)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            extra_layout.addWidget(btn, i // 2, i % 2)
        layout.addWidget(extra_box)

        # ── Log output ────────────────────────────────────────────────────────
        log_box = QGroupBox("Output")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("log_view")
        self.log_view.setMaximumHeight(160)
        btn_clear = QPushButton("Clear")
        btn_clear.setMaximumWidth(80)
        btn_clear.clicked.connect(self.log_view.clear)
        log_layout.addWidget(self.log_view)
        log_layout.addWidget(btn_clear, 0, Qt.AlignRight)
        layout.addWidget(log_box)

        # ── Status / Progress ─────────────────────────────────────────────────
        self.status_lbl = QLabel("Select a root method and follow the steps above.")
        self.status_lbl.setObjectName("lbl_status")
        outer_layout.addWidget(self.status_lbl)
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(10)
        self.progress.hide()
        outer_layout.addWidget(self.progress)

    def _add_divider(self, grid, row):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#1a2535;")
        grid.addWidget(line, row, 0, 1, 3)

    # ── Method Info ───────────────────────────────────────────────────────────
    def _update_method_info(self):
        method = self.method_combo.currentText()
        info   = ROOT_METHODS.get(method, {})
        self.method_desc.setText(info.get("description", ""))
        self.method_pros.setText(info.get("pros", ""))
        self.method_cons.setText(info.get("cons", ""))
        self.guide_requested.emit("ROOT_WORKFLOW")

    def _open_download(self):
        method = self.method_combo.currentText()
        url    = ROOT_METHODS.get(method, {}).get("url", "")
        if url:
            webbrowser.open(url)
            self._log(f"Opened download page: {url}")
        else:
            QMessageBox.warning(self, "No URL", "No download URL for this method.")

    # ── Prerequisites ─────────────────────────────────────────────────────────
    def _check_prerequisites(self):
        self._log("Checking prerequisites via ADB…")
        if not self._adb.available:
            self._set_status("ADB not available — install platform-tools.")
            self.adb_status.setText("⬤  ADB: NOT FOUND — install platform-tools")
            self.adb_status.setStyleSheet("color:#ff5555; font-size:12px;")
            return

        devs = self._adb.get_devices()
        if not devs:
            self.adb_status.setText("⬤  ADB: No device connected")
            self.adb_status.setStyleSheet("color:#886600; font-size:12px;")
            return
        self.adb_status.setText(f"⬤  ADB: {len(devs)} device(s) connected")
        self.adb_status.setStyleSheet("color:#00c890; font-size:12px;")

        serial = devs[0].get("serial", "")
        # Check bootloader
        bl = self._adb.get_prop("ro.boot.verifiedbootstate", serial)
        oem = self._adb.get_prop("ro.boot.flash.locked", serial)
        if bl in ("orange", "yellow") or oem == "0":
            self.bl_status.setText("⬤  Bootloader: UNLOCKED ✓")
            self.bl_status.setStyleSheet("color:#00c890; font-size:12px;")
        elif bl == "green" or oem == "1":
            self.bl_status.setText("⬤  Bootloader: LOCKED — unlock first!")
            self.bl_status.setStyleSheet("color:#ff5555; font-size:12px;")
        else:
            self.bl_status.setText(f"⬤  Bootloader: {bl or 'unknown'} (oem_lock={oem})")
            self.bl_status.setStyleSheet("color:#ffaa00; font-size:12px;")

        self._log(f"BL state: {bl}  OEM lock: {oem}")

    # ── Workflow Steps ────────────────────────────────────────────────────────
    def _backup_boot(self):
        """Backup boot partition via the flash engine."""
        from core.partition_manager import Partition
        # Ask user where to save
        path, _ = QFileDialog.getSaveFileName(
            self, "Save boot.img backup", "boot_stock.img",
            "Image files (*.img *.bin);;All Files (*)"
        )
        if not path:
            return

        # Build a minimal Partition object for the boot partition
        part = Partition()
        part.name = "boot"
        # Common boot partition address — actual address would come from scatter
        # We use address 0 here; the engine reads via protocol
        part.physical_start = 0x0
        part.size = 64 * 1024 * 1024  # 64MB max read (typical boot partition)

        self._boot_backup = path
        self.boot_path_lbl.setText(f"→ {os.path.basename(path)}")
        self.boot_path_lbl.setStyleSheet("color:#00c890; font-size:11px;")
        self._set_status(f"Backing up boot partition → {path}")
        self._log(f"Boot backup → {path}")
        self._engine.run(OpType.BACKUP_SINGLE, {"partition": part, "out_path": path})
        self.guide_requested.emit("BACKUP_SINGLE")

    def _push_boot(self):
        """Push local boot.img to device /sdcard/."""
        if not self._adb.available:
            self._warn_no_adb()
            return
        # Use backup if available, else ask for file
        local = self._boot_backup
        if not local or not os.path.exists(local):
            local, _ = QFileDialog.getOpenFileName(
                self, "Select boot.img to push", "",
                "Image files (*.img *.bin);;All Files (*)"
            )
        if not local:
            return

        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        self._set_status("Pushing boot.img to /sdcard/boot.img…")
        self._log(f"ADB push {local} → /sdcard/boot.img")
        self.progress.show()
        self.progress.setRange(0, 0)

        def do_push():
            return self._adb.push_file(local, "/sdcard/boot.img", serial)

        self._run_worker(do_push, on_done=self._on_push_done)

    def _on_push_done(self, ok: bool, _msg: str):
        self.progress.hide()
        if ok:
            self._set_status("boot.img pushed to /sdcard/boot.img ✓")
            self._log(
                "✓ Push complete. Now open the root manager app on your phone:\n"
                "  Install → Select and Patch a File → choose /sdcard/boot.img\n"
                "  Wait for patching to complete before pulling."
            )
        else:
            self._set_status("ADB push failed — check device connection.")
            self._log("✗ Push failed.")

    def _pull_patched_boot(self):
        """Pull the patched boot.img from device."""
        if not self._adb.available:
            self._warn_no_adb()
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save patched boot.img", "boot_patched.img",
            "Image files (*.img *.bin);;All Files (*)"
        )
        if not path:
            return

        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""

        # Try common patched file locations
        method  = self.method_combo.currentText()
        sources = [
            "/sdcard/Download/magisk_patched_*.img",
            "/sdcard/Download/kernelsu_patched_*.img",
            "/sdcard/Download/apatch_patched_*.img",
            "/sdcard/magisk_patched_*.img",
            "/sdcard/Download/boot_patched.img",
            "/sdcard/boot_patched.img",
        ]

        self._patched_boot = path
        self.patched_path_lbl.setText(f"→ {os.path.basename(path)}")
        self.patched_path_lbl.setStyleSheet("color:#ffaa00; font-size:11px;")
        self._set_status("Pulling patched boot.img from device…")
        self.progress.show()
        self.progress.setRange(0, 0)

        def do_pull():
            # Try each source path (use shell glob to find it)
            code, out = self._adb.shell(
                "ls /sdcard/Download/ 2>/dev/null || ls /sdcard/ 2>/dev/null", serial
            )
            self._log(f"Device /sdcard/Download/ contents:\n{out}")
            # Try wildcard via find
            code2, found = self._adb.shell(
                "find /sdcard -name 'magisk_patched*' -o -name 'kernelsu_patched*' "
                "-o -name 'apatch_patched*' -o -name 'boot_patched*' 2>/dev/null | head -1",
                serial
            )
            remote = found.strip()
            if not remote:
                # Last resort: user must specify
                return (False, "Could not auto-find patched file. "
                               "Check device /sdcard/Download/ manually and use ADB pull.")
            ok = self._adb.pull_file(remote, path, serial)
            return (ok, remote if ok else "Pull failed")

        self._run_worker(do_pull, on_done=self._on_pull_done)

    def _on_pull_done(self, ok: bool, msg: str):
        self.progress.hide()
        if ok:
            self.patched_path_lbl.setStyleSheet("color:#00c890; font-size:11px;")
            self._set_status(f"Patched boot.img pulled ✓ — from {msg}")
            self._log(f"✓ Pulled: {msg} → {self._patched_boot}")
        else:
            self.patched_path_lbl.setStyleSheet("color:#ff5555; font-size:11px;")
            self._set_status(f"Pull failed: {msg}")
            self._log(f"✗ {msg}")

    def _flash_patched_boot(self):
        """Flash the patched boot.img via the flash engine."""
        if not self._patched_boot:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select patched boot.img", "",
                "Image files (*.img *.bin);;All Files (*)"
            )
            if not path:
                return
            self._patched_boot = path

        if not os.path.exists(self._patched_boot):
            QMessageBox.warning(self, "File not found",
                f"Patched boot.img not found:\n{self._patched_boot}\n\n"
                "Complete Step 3 first (Pull Patched boot.img).")
            return

        if QMessageBox.question(
            self, "Flash Patched Boot",
            f"Flash patched boot.img to device?\n\nFile: {self._patched_boot}\n\n"
            "Device must be in BROM/Preloader mode (connected via MTK Client).",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        from core.partition_manager import Partition
        part = Partition()
        part.name = "boot"
        part.physical_start = 0x0
        part.size = os.path.getsize(self._patched_boot)
        part.file_name = self._patched_boot

        self._set_status("Flashing patched boot.img…")
        self._log(f"Flashing patched boot: {self._patched_boot}")
        self.guide_requested.emit("ROOT_WORKFLOW")
        self._engine.run(OpType.FLASH_SINGLE, {
            "partition": part,
            "file_path": self._patched_boot
        })

    def _verify_root(self):
        """Check if root is working via ADB."""
        if not self._adb.available:
            self._warn_no_adb()
            return
        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        self._log("Verifying root via ADB…")

        def do_check():
            code, out = self._adb.shell("su -c id 2>&1", serial)
            return (code == 0 or "uid=0" in out, out)

        self._run_worker(do_check, on_done=self._on_verify_done)

    def _on_verify_done(self, ok: bool, msg: str):
        if ok or "uid=0" in msg:
            self.verify_output.setText(f"✓ Root working!  {msg.strip()}")
            self.verify_output.setStyleSheet("color:#00c890; font-size:11px; font-weight:bold;")
            self._set_status("Root verified ✓")
            self._log(f"✓ Root active: {msg.strip()}")
        else:
            self.verify_output.setText(f"✗ No root access.  {msg.strip()}")
            self.verify_output.setStyleSheet("color:#ff5555; font-size:11px;")
            self._set_status("Root not detected — check installation steps.")
            self._log(f"✗ Root check failed: {msg.strip()}")

    # ── Extra Tools ───────────────────────────────────────────────────────────
    def _adb_install_magisk(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Magisk/KernelSU/APatch APK", "",
            "APK files (*.apk);;All Files (*)"
        )
        if not path:
            return
        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        self._log(f"Installing {os.path.basename(path)}…")

        def do_install():
            return self._adb.install_apk(path, serial)

        self._run_worker(do_install, on_done=lambda ok, msg:
            self._log(f"{'✓ Installed' if ok else '✗ Failed'}: {msg}"))

    def _check_su(self):
        if not self._adb.available:
            self._warn_no_adb(); return
        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        code, out = self._adb.shell("su -c 'id && whoami'", serial)
        self._log(f"su check:\n{out}")

    def _check_zygisk(self):
        if not self._adb.available:
            self._warn_no_adb(); return
        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        code, out = self._adb.shell(
            "su -c 'magisk --sqlite \"select * from modules\"' 2>&1", serial
        )
        self._log(f"Magisk modules:\n{out}")

    def _install_lsposed(self):
        webbrowser.open("https://github.com/LSPosed/LSPosed/releases/latest")
        self._log("Opened LSPosed download page.")

    def _check_safetynet(self):
        if not self._adb.available:
            self._warn_no_adb(); return
        devs   = self._adb.get_devices()
        serial = devs[0].get("serial", "") if devs else ""
        code, out = self._adb.shell(
            "su -c 'magisk --denylist status 2>&1; getprop ro.boot.verifiedbootstate'", serial
        )
        self._log(f"SafetyNet info:\n{out}")
        QMessageBox.information(self, "Play Integrity Info",
            "For full Play Integrity check, install 'YASNAC' or 'Play Integrity API Checker' "
            "from the Play Store.\n\nFor passing Play Integrity:\n"
            "• Magisk: install 'PlayIntegrityFix' module\n"
            "• KernelSU: install 'PlayIntegrityFix' or 'Tricky Store'\n"
            "• APatch: install 'PlayIntegrityFix' module"
        )

    def _restore_stock_boot(self):
        """Flash the original stock boot back to unroot."""
        if not self._boot_backup or not os.path.exists(self._boot_backup):
            path, _ = QFileDialog.getOpenFileName(
                self, "Select stock boot.img backup", "",
                "Image files (*.img *.bin);;All Files (*)"
            )
            if not path:
                return
            self._boot_backup = path

        if QMessageBox.question(
            self, "Restore Stock Boot",
            f"Flash stock boot.img to REMOVE root?\n\nFile: {self._boot_backup}",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        from core.partition_manager import Partition
        part = Partition()
        part.name = "boot"
        part.physical_start = 0x0
        part.size = os.path.getsize(self._boot_backup)
        part.file_name = self._boot_backup

        self._log("Restoring stock boot (removing root)…")
        self._engine.run(OpType.FLASH_SINGLE, {
            "partition": part,
            "file_path": self._boot_backup
        })

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _run_worker(self, fn, on_done=None):
        """Run a blocking function in a QThread."""
        self._worker = ADBWorker(fn)
        if on_done:
            self._worker.result.connect(on_done)
        self._worker.result.connect(lambda ok, msg: self.progress.hide())
        self._worker.start()

    def _warn_no_adb(self):
        QMessageBox.warning(self, "ADB Required",
            "ADB is not available or no device is connected.\n\n"
            "Install platform-tools and connect device via USB with USB Debugging enabled.")

    def _set_status(self, msg: str):
        self.status_lbl.setText(msg)

    def _log(self, msg: str):
        self.log_view.append(msg)
