"""
Tools Tab — advanced operations not in original MTK Client:
  FRP Bypass, Payload Sender, NVRAM Backup/Restore,
  Bootloader Unlock, Memory Test, ADB Tools, IMEI Repair hint.
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QFileDialog,
    QLineEdit, QTextEdit, QComboBox, QMessageBox,
    QProgressBar, QTabWidget, QSizePolicy,
    QScrollArea, QFrame
)
from PyQt5.QtCore import Qt
from core import FlashEngine, OpType, ADBBridge


class ToolsTab(QWidget):
    def __init__(self, engine: FlashEngine, adb: ADBBridge, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._adb    = adb
        self._build_ui()
        self._connect_engine()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        sub_tabs = QTabWidget()
        sub_tabs.addTab(self._build_device_tab(), "Device Ops")
        sub_tabs.addTab(self._build_payload_tab(), "Payload / Auth")
        sub_tabs.addTab(self._build_adb_tab(), "ADB Shell")
        sub_tabs.addTab(self._build_repair_tab(), "Repair")
        layout.addWidget(sub_tabs)

        # Status bar
        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setObjectName("lbl_status")
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(12)
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.progress)

    # ── Device Ops ────────────────────────────────────────────────────────────
    def _build_device_tab(self) -> QWidget:
        from PyQt5.QtWidgets import QScrollArea
        # Outer widget with scroll so nothing gets squished
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(inner)
        outer_layout.addWidget(scroll)

        # ── Power Control (2×3 grid so buttons are NOT squished) ─────────────
        pwr_box = QGroupBox("Power Control")
        pwr_grid = QGridLayout(pwr_box)
        pwr_grid.setSpacing(6)
        pwr_entries = [
            ("Power Off (BROM)",   OpType.POWER_OFF, "Send power-off via BROM protocol",          ""),
            ("WDT Reset (BROM)",   OpType.WD_RESET,  "Watchdog reboot via BROM protocol",          ""),
            ("Reboot (ADB)",       None,              "Normal reboot via ADB",                      ""),
            ("Reboot → Recovery",  None,              "Reboot into recovery mode via ADB",          "recovery"),
            ("Reboot → Bootloader",None,              "Reboot into fastboot/bootloader via ADB",    "bootloader"),
            ("Reboot → EDL/BROM",  None,              "Force into deep-flash EDL mode via ADB",     "edl"),
        ]
        for i, (label, op, tip, mode) in enumerate(pwr_entries):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setMinimumWidth(180)
            if op:
                btn.clicked.connect(lambda _, o=op: self._run_op(o, {}))
            elif mode == "edl":
                btn.clicked.connect(lambda: self._adb.reboot_edl())
            else:
                m = mode  # capture
                btn.clicked.connect(lambda _, m2=m: self._adb_reboot(m2))
            pwr_grid.addWidget(btn, i // 3, i % 3)
        layout.addWidget(pwr_box)

        # ── Format / Erase ───────────────────────────────────────────────────
        fmt_box = QGroupBox("Format / Erase Partition")
        fmt_layout = QGridLayout(fmt_box)
        fmt_layout.setSpacing(8)

        fmt_layout.addWidget(QLabel("Target Partition:"), 0, 0)
        self.fmt_part_combo = QComboBox()
        self.fmt_part_combo.setEditable(True)
        self.fmt_part_combo.addItems([
            "userdata", "cache", "metadata", "frp", "nvram",
            "lk", "lk2", "system", "vendor", "product", "odm",
            "persist", "misc", "para",
        ])
        fmt_layout.addWidget(self.fmt_part_combo, 0, 1)

        btn_fmt_part = QPushButton("Erase Selected Partition")
        btn_fmt_part.setObjectName("btn_danger")
        btn_fmt_part.setMinimumWidth(200)
        btn_fmt_part.clicked.connect(self._do_format_part)
        fmt_layout.addWidget(btn_fmt_part, 0, 2)

        btn_fmt_all = QPushButton("⚠   Factory Reset  —  Wipes userdata + cache + metadata")
        btn_fmt_all.setObjectName("btn_danger")
        btn_fmt_all.clicked.connect(self._do_format_all)
        fmt_layout.addWidget(btn_fmt_all, 1, 0, 1, 3)
        layout.addWidget(fmt_box)

        # ── FRP ──────────────────────────────────────────────────────────────
        frp_box = QGroupBox("FRP — Factory Reset Protection Bypass")
        frp_layout = QHBoxLayout(frp_box)
        frp_info = QLabel(
            "Erases the 'frp' partition to remove Google account lock.\n"
            "Device must be in BROM or Preloader mode."
        )
        btn_frp = QPushButton("🔓   Bypass FRP (Erase frp partition)")
        btn_frp.setObjectName("btn_flash")
        btn_frp.setMinimumWidth(260)
        btn_frp.setMinimumHeight(36)
        btn_frp.clicked.connect(self._do_frp)
        frp_layout.addWidget(frp_info, 1)
        frp_layout.addWidget(btn_frp)
        layout.addWidget(frp_box)

        # ── Bootloader ───────────────────────────────────────────────────────
        bl_box = QGroupBox("Bootloader Unlock")
        bl_box.setMinimumHeight(130)
        bl_layout = QGridLayout(bl_box)
        bl_layout.setSpacing(8)

        bl_info = QLabel(
            "MTK method: wipes lk / lk2 / para partitions to remove boot verification.\n"
            "After this, use 'fastboot oem unlock' or OEM unlock in Developer Options.\n"
            "Warning: unlocking erases all user data on most devices."
        )
        bl_info.setWordWrap(True)
        bl_layout.addWidget(bl_info, 0, 0, 1, 2)

        btn_bl = QPushButton("🔑   Unlock Bootloader  (MTK — wipe lk/lk2/para)")
        btn_bl.setObjectName("btn_warn")
        btn_bl.setMinimumHeight(36)
        btn_bl.clicked.connect(self._do_unlock_bl)
        bl_layout.addWidget(btn_bl, 1, 0)

        btn_fb = QPushButton("Reboot → Bootloader  (then run: fastboot oem unlock)")
        btn_fb.setMinimumHeight(36)
        btn_fb.clicked.connect(lambda: self._adb_reboot("bootloader"))
        bl_layout.addWidget(btn_fb, 1, 1)
        layout.addWidget(bl_box)

        # ── NVRAM ────────────────────────────────────────────────────────────
        nvram_box = QGroupBox("NVRAM / Persist  (IMEI · WiFi MAC · BT MAC · Calibration)")
        nvram_layout = QHBoxLayout(nvram_box)
        nvram_info = QLabel(
            "Always backup NVRAM before flashing!\n"
            "Restoring a backup repairs lost IMEI / baseband after bad flash."
        )
        btn_nvram_bak = QPushButton("⬇   Backup NVRAM")
        btn_nvram_bak.setMinimumWidth(160)
        btn_nvram_bak.clicked.connect(self._do_nvram_backup)
        btn_nvram_rst = QPushButton("⬆   Restore NVRAM")
        btn_nvram_rst.setObjectName("btn_warn")
        btn_nvram_rst.setMinimumWidth(160)
        btn_nvram_rst.clicked.connect(self._do_nvram_restore)
        nvram_layout.addWidget(nvram_info, 1)
        nvram_layout.addWidget(btn_nvram_bak)
        nvram_layout.addWidget(btn_nvram_rst)
        layout.addWidget(nvram_box)

        # ── Memory Test ──────────────────────────────────────────────────────
        mem_box = QGroupBox("Memory Diagnostics")
        mem_layout = QHBoxLayout(mem_box)
        mem_info = QLabel("Tests device RAM and NAND/eMMC/UFS flash for read/write errors.")
        btn_mem = QPushButton("▶   Run RAM + Flash Memory Test")
        btn_mem.setMinimumWidth(240)
        btn_mem.clicked.connect(lambda: self._run_op(OpType.MEM_TEST, {}))
        mem_layout.addWidget(mem_info, 1)
        mem_layout.addWidget(btn_mem)
        layout.addWidget(mem_box)

        layout.addStretch()
        return outer

    # ── Payload / Auth ────────────────────────────────────────────────────────
    def _build_payload_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info_box = QGroupBox("BROM Exploit / Auth Bypass")
        info_layout = QVBoxLayout(info_box)
        info_lbl = QLabel(
            "Send a custom payload to bypass BROM authentication or SLA/DAA.\n"
            "Required for devices with Secure Boot enabled.\n\n"
            "Common payloads:\n"
            "  • kamakiri   — MT6580/MT6735/MT6737/MT6739\n"
            "  • amonet     — MT6771 (Helio P60)\n"
            "  • carbonara  — MT6765/MT6762\n"
            "  • brutforce  — V6 protocol devices (requires loader)\n\n"
            "Load the correct payload .bin for your chipset from the Loaders directory."
        )
        info_lbl.setStyleSheet("color:#607080; font-size:11px; line-height:160%;")
        info_lbl.setWordWrap(True)
        info_layout.addWidget(info_lbl)
        layout.addWidget(info_box)

        load_box = QGroupBox("Load Payload")
        load_layout = QHBoxLayout(load_box)
        self.payload_path = QLineEdit()
        self.payload_path.setPlaceholderText("Select .bin payload file…")
        self.payload_path.setReadOnly(True)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_payload)
        btn_send   = QPushButton("⚡  Send Payload")
        btn_send.setObjectName("btn_flash")
        btn_send.clicked.connect(self._do_send_payload)
        load_layout.addWidget(self.payload_path, 1)
        load_layout.addWidget(btn_browse)
        load_layout.addWidget(btn_send)
        layout.addWidget(load_box)

        # Loader selector
        loader_box = QGroupBox("V6 Loader (Dimensity / new Helio G)")
        loader_layout = QHBoxLayout(loader_box)
        self.loader_path = QLineEdit()
        self.loader_path.setPlaceholderText("Select V6 loader (.bin) — required for MT6853+…")
        self.loader_path.setReadOnly(True)
        btn_loader = QPushButton("Browse Loader…")
        btn_loader.clicked.connect(self._browse_loader)
        loader_layout.addWidget(self.loader_path, 1)
        loader_layout.addWidget(btn_loader)
        layout.addWidget(loader_box)

        layout.addStretch()
        return w

    # ── ADB Shell ─────────────────────────────────────────────────────────────
    def _build_adb_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Device picker
        top = QHBoxLayout()
        self.adb_device_combo = QComboBox()
        btn_refresh_adb = QPushButton("⟳ Refresh")
        btn_refresh_adb.clicked.connect(self._refresh_adb_devices)
        top.addWidget(QLabel("Device:"))
        top.addWidget(self.adb_device_combo, 1)
        top.addWidget(btn_refresh_adb)
        layout.addLayout(top)

        # Shell output
        self.adb_output = QTextEdit()
        self.adb_output.setReadOnly(True)
        self.adb_output.setObjectName("log_view")
        layout.addWidget(self.adb_output, 1)

        # Command input
        cmd_layout = QHBoxLayout()
        self.adb_cmd = QLineEdit()
        self.adb_cmd.setPlaceholderText("Enter shell command…  e.g. getprop ro.product.model")
        self.adb_cmd.returnPressed.connect(self._run_adb_cmd)
        btn_run = QPushButton("Run")
        btn_run.clicked.connect(self._run_adb_cmd)
        btn_logcat = QPushButton("Logcat")
        btn_logcat.clicked.connect(self._get_logcat)
        cmd_layout.addWidget(self.adb_cmd, 1)
        cmd_layout.addWidget(btn_run)
        cmd_layout.addWidget(btn_logcat)
        layout.addLayout(cmd_layout)

        # Quick action buttons
        quick_box = QGroupBox("Quick Actions")
        quick_layout = QHBoxLayout(quick_box)
        for label, cmd in [
            ("Device Info", "getprop ro.product.model"),
            ("Storage",     "df -h"),
            ("CPU Info",    "cat /proc/cpuinfo | head -20"),
            ("Battery",     "dumpsys battery | head -20"),
            ("Network",     "ip addr"),
            ("Apps",        "pm list packages -3"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, c=cmd: self._run_adb_shell(c))
            quick_layout.addWidget(btn)
        layout.addWidget(quick_box)

        return w

    # ── Repair ────────────────────────────────────────────────────────────────
    def _build_repair_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        repair_info = QGroupBox("Repair Guide")
        info_layout = QVBoxLayout(repair_info)
        info_text = QLabel(
            "<b>IMEI Repair</b><br>"
            "IMEI is stored in NVRAM. To repair:<br>"
            "1. Backup NVRAM first (Device Ops tab)<br>"
            "2. Use a hex editor to patch the IMEI bytes at offset 0x2A<br>"
            "3. Restore NVRAM (Device Ops tab)<br><br>"
            "<b>Boot Loop Fix</b><br>"
            "Flash the stock preloader + boot partition via Flash tab.<br><br>"
            "<b>Baseband Loss</b><br>"
            "Restore NVRAM backup, then flash md1img/md3img partitions.<br><br>"
            "<b>Dead Boot (no BROM detected)</b><br>"
            "Try: hold Vol- while inserting USB to force BROM mode.<br>"
            "Some devices: Vol+ + Vol- simultaneously.<br>"
            "Use a USB-A to USB-A cable for hardware glitch on old SOCs."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color:#607080; line-height:160%;")
        info_text.setTextFormat(Qt.RichText)
        info_layout.addWidget(info_text)
        layout.addWidget(repair_info)

        # Boot.img patcher hint
        patch_box = QGroupBox("Boot.img Patching (Magisk Root)")
        patch_layout = QVBoxLayout(patch_box)
        steps = QLabel(
            "1. Backup the 'boot' partition (Flash tab → Backup Selected)\n"
            "2. Transfer boot.bin to phone via ADB push\n"
            "3. Patch with Magisk app on device\n"
            "4. Pull patched boot back via ADB pull\n"
            "5. Flash patched boot.bin back (Flash tab → Flash Single)"
        )
        steps.setStyleSheet("color:#607080; font-size:11px;")

        btn_push_boot = QPushButton("ADB Push boot.img to /sdcard/")
        btn_push_boot.clicked.connect(self._push_boot_to_device)
        btn_pull_boot = QPushButton("ADB Pull patched_boot.img from /sdcard/")
        btn_pull_boot.clicked.connect(self._pull_patched_boot)

        patch_layout.addWidget(steps)
        patch_layout.addWidget(btn_push_boot)
        patch_layout.addWidget(btn_pull_boot)
        layout.addWidget(patch_box)

        layout.addStretch()
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _connect_engine(self):
        self._engine.progress_updated.connect(self._on_progress)
        self._engine.status_updated.connect(self.status_lbl.setText)
        self._engine.operation_finished.connect(self._on_op_finished)

    def _on_progress(self, cur: int, total: int, label: str):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(cur)
        self.status_lbl.setText(label)

    def _on_op_finished(self, ok: bool, msg: str):
        icon_fn = QMessageBox.information if ok else QMessageBox.critical
        icon_fn(self, "Done" if ok else "Error", msg)

    def _run_op(self, op: OpType, params: dict):
        self._engine.run(op, params)

    def _adb_reboot(self, mode: str):
        serial = self.adb_device_combo.currentText().split()[0] if self.adb_device_combo.currentText() else ""
        ok = self._adb.reboot(mode, serial)
        self.status_lbl.setText(f"Reboot {'sent' if ok else 'failed'} (mode={mode or 'normal'})")

    # ── Device ops ────────────────────────────────────────────────────────────
    def _do_format_part(self):
        name = self.fmt_part_combo.currentText()
        if QMessageBox.question(self, "Confirm", f"Format partition '{name}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._run_op(OpType.FORMAT_PART, {"name": name})

    def _do_format_all(self):
        if QMessageBox.question(self, "⚠ Confirm Factory Reset",
                                "This will wipe userdata, cache, metadata.\nContinue?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._run_op(OpType.FORMAT_ALL, {})

    def _do_frp(self):
        if QMessageBox.question(self, "Confirm FRP Bypass",
                                "This will erase the FRP partition.\nProceed?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._run_op(OpType.FRP_BYPASS, {})

    def _do_unlock_bl(self):
        if QMessageBox.question(self, "⚠ Unlock Bootloader",
                                "This will modify lk/lk2/para partitions.\nProceed?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._run_op(OpType.UNLOCK_BL, {})

    def _do_nvram_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save NVRAM", "nvram_backup.bin", "Binary (*.bin)")
        if path:
            self._run_op(OpType.NVRAM_READ, {"out_path": path})

    def _do_nvram_restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open NVRAM", "", "Binary (*.bin);;All (*)")
        if path:
            self.status_lbl.setText(f"NVRAM restore: {path}")

    # ── Payload ───────────────────────────────────────────────────────────────
    def _browse_payload(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select Payload", "", "Binary (*.bin);;All (*)")
        if p:
            self.payload_path.setText(p)

    def _browse_loader(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select V6 Loader", "", "Binary (*.bin);;All (*)")
        if p:
            self.loader_path.setText(p)

    def _do_send_payload(self):
        path = self.payload_path.text()
        if not path:
            QMessageBox.warning(self, "No Payload", "Browse for a payload .bin file first.")
            return
        self._run_op(OpType.SEND_PAYLOAD, {"payload_path": path})

    # ── ADB ───────────────────────────────────────────────────────────────────
    def _refresh_adb_devices(self):
        self.adb_device_combo.clear()
        if not self._adb.available:
            self.adb_device_combo.addItem("ADB not found")
            return
        devs = self._adb.get_devices()
        for d in devs:
            self.adb_device_combo.addItem(f"{d['serial']} [{d['state']}]")
        if not devs:
            self.adb_device_combo.addItem("No devices")

    def _run_adb_cmd(self):
        cmd = self.adb_cmd.text().strip()
        if not cmd:
            return
        self._run_adb_shell(cmd)

    def _run_adb_shell(self, cmd: str):
        serial = self.adb_device_combo.currentText().split()[0] if self.adb_device_combo.currentText() else ""
        code, out = self._adb.shell(cmd, serial)
        self.adb_output.append(f"\n$ {cmd}\n{out}")

    def _get_logcat(self):
        serial = self.adb_device_combo.currentText().split()[0] if self.adb_device_combo.currentText() else ""
        out = self._adb.get_logcat(serial=serial)
        self.adb_output.setText(out)

    def _push_boot_to_device(self):
        local, _ = QFileDialog.getOpenFileName(self, "Select boot.img / boot.bin", "", "Binary (*.bin *.img);;All (*)")
        if local:
            serial = self.adb_device_combo.currentText().split()[0] if self.adb_device_combo.currentText() else ""
            ok = self._adb.push_file(local, "/sdcard/boot.img", serial)
            self.status_lbl.setText(f"Push {'OK' if ok else 'FAILED'}: boot.img → /sdcard/")

    def _pull_patched_boot(self):
        local, _ = QFileDialog.getSaveFileName(self, "Save patched boot", "patched_boot.img", "Binary (*.img *.bin)")
        if local:
            serial = self.adb_device_combo.currentText().split()[0] if self.adb_device_combo.currentText() else ""
            ok = self._adb.pull_file("/sdcard/Download/patched_boot.img", local, serial)
            if not ok:
                ok = self._adb.pull_file("/sdcard/patched_boot.img", local, serial)
            self.status_lbl.setText(f"Pull {'OK' if ok else 'FAILED'}: patched boot.img")
