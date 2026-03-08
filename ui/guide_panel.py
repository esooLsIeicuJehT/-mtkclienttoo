"""
GuidePanel — Context-aware instruction panel.

Shows step-by-step user guidance whenever any operation is triggered.
Updates its content based on: operation type, device state, chipset family.

Context Flow:
  Operation fired → GuidePanel.show_guide(op_key) → lookup guide DB
  → render steps with status indicators → user follows along
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette

# ── Guide Database ─────────────────────────────────────────────────────────────
# Each entry: list of (icon, title, detail)
GUIDES = {

    "DISCONNECTED": {
        "title": "Getting Started",
        "color": "#607080",
        "steps": [
            ("🔌", "Power off your device completely",
             "Hold the power button until the screen goes black. Wait 5 seconds."),
            ("📱", "Enter BROM mode",
             "Hold Vol– (some devices: Vol+) then plug in your USB cable. "
             "Keep holding until the LED lights up or this tool detects the device."),
            ("💡", "LED hint",
             "Most MTK devices show a solid RED or WHITE LED in BROM mode. "
             "If nothing happens try the other volume button."),
            ("🔄", "Alternative: via ADB",
             "If your device is running Android, open the ADB Shell tab and run: "
             "adb reboot edl  — this forces BROM mode without physical buttons."),
            ("✅", "Click CONNECT",
             "Once the device is in BROM mode, click the CONNECT button at the top "
             "or enable Auto-Detect to connect automatically when plugged in."),
        ]
    },

    "DETECTING": {
        "title": "Detecting Device…",
        "color": "#ffaa00",
        "steps": [
            ("🔍", "Scanning USB bus",
             "Searching for MediaTek vendor ID 0x0E8D on all USB ports."),
            ("⏳", "Please wait",
             "This takes 1–3 seconds. Make sure the device is in BROM or Preloader mode."),
            ("⚠️", "If detection fails",
             "On Linux: check udev rules are installed (Setup tab).\n"
             "On Windows: install UsbDk and MediaTek VCOM drivers.\n"
             "Try a different USB port or cable — USB 2.0 ports are more reliable for BROM."),
        ]
    },

    "BROM": {
        "title": "BROM Mode Connected ✓",
        "color": "#00d4ff",
        "steps": [
            ("✅", "Device is in BROM mode",
             "You have full low-level access to the device flash memory."),
            ("📋", "Check Device Info tab",
             "Click the Device Info tab to see the chipset, HW code, secure boot status and more."),
            ("⚡", "Ready to flash",
             "Load a scatter file in the Flash tab to flash or backup firmware."),
            ("🔧", "Advanced tools",
             "Use the Tools tab for FRP bypass, bootloader unlock, NVRAM backup, "
             "root assist, and more."),
            ("⚠️", "Do NOT disconnect",
             "Keep the USB connected throughout any flash operation. "
             "Disconnecting mid-flash can brick the device."),
        ]
    },

    "PRELOADER": {
        "title": "Preloader Mode Connected ✓",
        "color": "#00c890",
        "steps": [
            ("✅", "Preloader mode active",
             "The device bootloader is running. Most flash operations are available."),
            ("📋", "Read device info",
             "Click Refresh Info on the Device Info tab to populate chipset details."),
            ("⚡", "Flash operations",
             "The Flash tab is ready. Load your scatter file and select partitions."),
            ("🔄", "To get full BROM access",
             "Power off and re-enter BROM mode (hold Vol– before plugging USB) "
             "for lower-level operations like payload/exploit injection."),
        ]
    },

    "FLASH_SCATTER": {
        "title": "Flashing Firmware",
        "color": "#ff8030",
        "steps": [
            ("🚫", "DO NOT disconnect USB",
             "Disconnecting during flash WILL brick your device. Keep the cable plugged in."),
            ("⏳", "Wait for completion",
             "The progress bar shows current/total bytes. Each partition is flashed in sequence."),
            ("📊", "Watch the partition list",
             "Each partition status will update as it completes. Green = success."),
            ("🔄", "After completion",
             "The device will reboot automatically when flashing is done. "
             "First boot may take 3–5 minutes — this is normal."),
            ("⚠️", "If flash fails",
             "Check that all partition file paths are valid (green) in the partition list. "
             "Make sure the scatter file matches your exact device firmware version."),
        ]
    },

    "BACKUP_ALL": {
        "title": "Backing Up All Partitions",
        "color": "#4080ff",
        "steps": [
            ("📁", "Backup folder selected",
             "All partition .bin files will be saved to your selected folder."),
            ("⏳", "This takes a while",
             "A full backup reads every partition sequentially. "
             "Expect 5–20 minutes depending on flash size and USB speed."),
            ("🔒", "Store backups safely",
             "These .bin files are your recovery files. Store them on a separate drive "
             "or cloud backup — losing them means no recovery from bad flash."),
            ("✅", "After backup",
             "You can use these files in the Flash tab to restore individual partitions "
             "or re-flash the full firmware from the scatter file."),
        ]
    },

    "BACKUP_SINGLE": {
        "title": "Backing Up Partition",
        "color": "#4080ff",
        "steps": [
            ("📁", "Reading partition",
             "The selected partition is being read from device flash."),
            ("💾", "Save the file",
             "The .bin file will be saved to your chosen location. "
             "Keep this as a restore point before making changes."),
            ("✅", "Done",
             "The partition backup is complete. You can flash it back any time "
             "via Flash tab → select the partition → Browse File."),
        ]
    },

    "FRP_BYPASS": {
        "title": "FRP Bypass",
        "color": "#ff8030",
        "steps": [
            ("🔓", "Erasing FRP partition",
             "The 'frp' partition stores Google account verification data. "
             "Erasing it removes the account lock."),
            ("⏳", "Wait for completion",
             "This operation is fast — usually under 10 seconds."),
            ("🔄", "After FRP erase",
             "Power off the device, remove and re-insert the battery if possible, "
             "then power back on normally."),
            ("📱", "First boot",
             "The Google account setup screen will no longer appear. "
             "You can set up the device fresh without the previous account."),
            ("⚠️", "Note",
             "If the device was factory-reset and still shows FRP, "
             "ensure you erased the correct partition. Some devices use 'persist/frp'."),
        ]
    },

    "FORMAT_PART": {
        "title": "Erasing Partition",
        "color": "#ff4444",
        "steps": [
            ("⚠️", "Partition erase in progress",
             "The selected partition is being wiped. This cannot be undone."),
            ("⏳", "Wait for completion",
             "Do not disconnect USB during erase."),
            ("✅", "After erase",
             "The partition is now blank. If this was userdata/cache, "
             "the device will perform a clean first boot setup on next power-on."),
        ]
    },

    "FORMAT_ALL": {
        "title": "Factory Reset — Wiping Device",
        "color": "#ff2222",
        "steps": [
            ("🚫", "DO NOT disconnect USB",
             "Wiping all data partitions. Stay connected."),
            ("⏳", "Wiping userdata, cache, metadata",
             "All user data is being permanently erased."),
            ("🔄", "After wipe",
             "Power off the device then power back on normally. "
             "First boot setup will run as if the phone is brand new."),
            ("📱", "No Google FRP",
             "If you also ran FRP bypass, there will be no account lock on first boot."),
        ]
    },

    "UNLOCK_BL": {
        "title": "Bootloader Unlock",
        "color": "#f0c040",
        "steps": [
            ("⚠️", "What this does",
             "Wipes lk, lk2, and para partitions to remove boot signature verification. "
             "This is the MTK-specific unlock method."),
            ("🔄", "Step 1 — After MTK unlock",
             "Power off device. Power it back on normally into Android."),
            ("⚙️", "Step 2 — Enable OEM Unlock",
             "Go to Settings → About Phone → tap Build Number 7 times.\n"
             "Then Settings → Developer Options → Enable OEM Unlocking."),
            ("💻", "Step 3 — Fastboot unlock",
             "Reboot to bootloader (Tools → Reboot → Bootloader), then run:\n"
             "fastboot oem unlock\nor: fastboot flashing unlock"),
            ("✅", "Step 4 — Confirm on device",
             "The device screen will ask you to confirm. "
             "Use volume buttons to select YES and press power."),
            ("📱", "After unlock",
             "The bootloader is now unlocked. Device will factory reset. "
             "You can now flash custom ROMs, recoveries, and root your device."),
        ]
    },

    "SEND_PAYLOAD": {
        "title": "Sending BROM Payload",
        "color": "#a060ff",
        "steps": [
            ("⚡", "Payload injection in progress",
             "Sending exploit payload to bypass BROM authentication."),
            ("🔒", "What this bypasses",
             "Secure Boot / SLA / DAA on MTK devices. "
             "Required for flashing on locked devices with auth enabled."),
            ("✅", "If successful",
             "Auth bypass is active. You can now proceed with flash/backup operations "
             "that would otherwise require a signed DA (Download Agent)."),
            ("❌", "If it fails",
             "Make sure you selected the correct payload for your chipset. "
             "V6 devices (Dimensity) need a compatible loader, not a legacy payload."),
        ]
    },

    "NVRAM_READ": {
        "title": "NVRAM Backup",
        "color": "#4080ff",
        "steps": [
            ("📦", "Reading NVRAM partition",
             "NVRAM contains your IMEI, IMEI2, WiFi MAC, Bluetooth MAC, "
             "and RF calibration data."),
            ("💾", "Store this file safely",
             "CRITICAL: Keep this backup in a safe place. "
             "If you lose your IMEI after a bad flash, this is the only way to restore it."),
            ("✅", "After backup",
             "Use 'Restore NVRAM' if you ever need to recover your IMEI or baseband "
             "after flashing a new firmware."),
        ]
    },

    "MEM_TEST": {
        "title": "Memory Diagnostics",
        "color": "#40c080",
        "steps": [
            ("🧪", "Testing RAM",
             "Writing and reading test patterns to device RAM to check for errors."),
            ("💾", "Testing flash",
             "Reading flash sectors to check for bad blocks or read errors."),
            ("✅", "Interpreting results",
             "No errors = healthy device. Errors in RAM suggest hardware damage. "
             "Bad flash blocks are normal up to 2% — more indicates aging flash."),
        ]
    },

    "ROOT_WORKFLOW": {
        "title": "Root Assistant",
        "color": "#00ff88",
        "steps": [
            ("🔓", "Step 1 — Unlock Bootloader",
             "Bootloader MUST be unlocked before rooting. "
             "Go to Device Ops → Bootloader Unlock and follow those steps first."),
            ("💾", "Step 2 — Backup boot partition",
             "Click 'Backup boot.img' in the Root Assistant tab. "
             "This gives you a stock boot to restore from if anything goes wrong."),
            ("📲", "Step 3 — Install your root manager",
             "Transfer the Magisk / KernelSU / APatch APK to your phone "
             "and install it (Settings → Allow unknown sources)."),
            ("🩹", "Step 4 — Patch boot.img",
             "Open the root manager app → Install → Select and Patch a File → "
             "choose the boot.img you transferred. Wait for patching to finish."),
            ("⬆️", "Step 5 — Pull patched boot",
             "Click 'Pull Patched boot.img' — this pulls the patched file from /sdcard/."),
            ("⚡", "Step 6 — Flash patched boot",
             "Click 'Flash Patched boot.img' to write it to the boot partition."),
            ("✅", "Step 7 — Verify",
             "Device will reboot. Open the root manager app and click Refresh — "
             "it should show 'Installed' with your device's Zygisk/module info."),
        ]
    },

    "POWER_OFF": {
        "title": "Powering Off Device",
        "color": "#607080",
        "steps": [
            ("🔌", "Power off command sent",
             "The device will power down via BROM protocol."),
            ("✅", "To reconnect",
             "Hold Vol– and plug in USB again to re-enter BROM mode."),
        ]
    },

    "WD_RESET": {
        "title": "Watchdog Reset",
        "color": "#607080",
        "steps": [
            ("🔄", "Rebooting device",
             "Watchdog timer triggered — device is rebooting now."),
            ("⏳", "Wait for boot",
             "Normal boot takes 30–90 seconds on most MTK devices."),
        ]
    },
}


class StepWidget(QFrame):
    """Single step card with icon, title, and detail text."""
    def __init__(self, number: int, icon: str, title: str, detail: str,
                 active: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        bg = "#111a28" if active else "#0a0e18"
        border = "#00d4ff" if active else "#1a2535"
        self.setStyleSheet(
            f"QFrame {{ background:{bg}; border-left:3px solid {border}; "
            f"border-radius:3px; margin:2px 0; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        num_lbl = QLabel(f"{number}")
        num_lbl.setFixedSize(22, 22)
        num_lbl.setAlignment(Qt.AlignCenter)
        num_color = "#00d4ff" if active else "#304050"
        num_lbl.setStyleSheet(
            f"color:{num_color}; font-weight:bold; font-size:11px; "
            f"background:#111520; border:1px solid {border}; border-radius:11px;"
        )

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(f"<b>{title}</b>")
        title_lbl.setStyleSheet(f"color:{'#d0e8ff' if active else '#8090a8'}; font-size:12px;")
        title_lbl.setTextFormat(Qt.RichText)
        detail_lbl = QLabel(detail)
        detail_lbl.setWordWrap(True)
        detail_lbl.setStyleSheet("color:#506878; font-size:11px; line-height:150%;")
        text_col.addWidget(title_lbl)
        text_col.addWidget(detail_lbl)

        layout.addWidget(num_lbl)
        layout.addWidget(icon_lbl)
        layout.addLayout(text_col, 1)


class GuidePanel(QWidget):
    """
    Persistent right-side panel showing context-aware instructions.
    Updated by GuidePanel.show_guide(key) from any part of the UI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)
        self._current_key = "DISCONNECTED"
        self._build_ui()
        self.show_guide("DISCONNECTED")

    def _build_ui(self):
        self.setStyleSheet("background:#080c14; border-left:1px solid #1a2535;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(42)
        self._header.setStyleSheet("background:#060810; border-bottom:1px solid #1a2535;")
        hdr_layout = QHBoxLayout(self._header)
        hdr_layout.setContentsMargins(12, 0, 8, 0)

        self._header_title = QLabel("GUIDE")
        self._header_title.setStyleSheet(
            "color:#00d4ff; font-size:11px; font-weight:bold; letter-spacing:2px;"
        )
        self._dot = QLabel("⬤")
        self._dot.setStyleSheet("color:#607080; font-size:8px;")

        hdr_layout.addWidget(self._dot)
        hdr_layout.addWidget(self._header_title)
        hdr_layout.addStretch()
        layout.addWidget(self._header)

        # ── Op title ──────────────────────────────────────────────────────────
        self._op_title = QLabel("")
        self._op_title.setWordWrap(True)
        self._op_title.setStyleSheet(
            "color:#a0c0d8; font-size:13px; font-weight:bold; "
            "padding:10px 12px 6px 12px;"
        )
        layout.addWidget(self._op_title)

        # ── Steps scroll area ─────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background:#080c14;")

        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background:#080c14;")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(8, 4, 8, 12)
        self._steps_layout.setSpacing(4)
        self._steps_layout.addStretch()

        self._scroll.setWidget(self._steps_container)
        layout.addWidget(self._scroll, 1)

        # ── Footer hint ───────────────────────────────────────────────────────
        footer = QLabel("Instructions update automatically\nwhen you perform any operation.")
        footer.setStyleSheet(
            "color:#283848; font-size:10px; padding:8px 12px; "
            "border-top:1px solid #121820;"
        )
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def show_guide(self, key: str, active_step: int = 0):
        """Lookup guide by key and render steps."""
        self._current_key = key
        guide = GUIDES.get(key, GUIDES.get("DISCONNECTED"))

        # Update header color dot
        color = guide.get("color", "#607080")
        self._dot.setStyleSheet(f"color:{color}; font-size:9px;")
        self._op_title.setText(guide.get("title", ""))
        self._op_title.setStyleSheet(
            f"color:{color}; font-size:13px; font-weight:bold; "
            f"padding:10px 12px 6px 12px;"
        )

        # Clear existing steps (all except the stretch at end)
        while self._steps_layout.count() > 1:
            item = self._steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        steps = guide.get("steps", [])
        for i, (icon, title, detail) in enumerate(steps):
            is_active = (i == active_step)
            step_w = StepWidget(i + 1, icon, title, detail, active=is_active)
            self._steps_layout.insertWidget(i, step_w)

        # Scroll to top
        self._scroll.verticalScrollBar().setValue(0)

    def advance_step(self, step: int):
        """Highlight a specific step as current."""
        self.show_guide(self._current_key, active_step=step)
