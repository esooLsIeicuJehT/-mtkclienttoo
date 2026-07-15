"""
Main Window — top-level application frame.

Context Flow:
  Window Init → Connection Header → [Tab Container | GuidePanel]
  Device Events (thread-safe signal) → Connection State → UI + Guide update
"""
import platform
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QMessageBox,
    QTabWidget, QProgressBar, QSplitter, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from core import MTKProtocol, ConnState, FlashEngine, ADBBridge
from core.device_manager import DeviceManager
from ui.tabs import DeviceInfoTab, FlashTab, ToolsTab, LogTab, SetupTab
from ui.tabs.root_tab import RootTab
from ui.tabs.kaeru_tab import KaeruTab
from ui.tabs.bypass_tab import BypassTab
from ui.guide_panel import GuidePanel
from utils import get_logger

log = get_logger("main_window")

STATE_LABELS = {
    ConnState.DISCONNECTED: ("⬤  DISCONNECTED",  "#ff4444"),
    ConnState.DETECTING:    ("⬤  DETECTING…",    "#ffaa00"),
    ConnState.BROM:         ("⬤  BROM MODE",      "#00d4ff"),
    ConnState.PRELOADER:    ("⬤  PRELOADER",      "#00c890"),
    ConnState.DA_MODE:      ("⬤  DA MODE",        "#a0e060"),
    ConnState.ADB:          ("⬤  ADB",            "#80c0ff"),
    ConnState.ERROR:        ("⬤  ERROR",          "#ff4444"),
}

STATE_GUIDE_KEYS = {
    ConnState.DISCONNECTED: "DISCONNECTED",
    ConnState.DETECTING:    "DETECTING",
    ConnState.BROM:         "BROM",
    ConnState.PRELOADER:    "PRELOADER",
    ConnState.DA_MODE:      "BROM",
    ConnState.ERROR:        "DISCONNECTED",
}

OP_GUIDE_KEYS = {
    "FLASH_SCATTER":  "FLASH_SCATTER",
    "FLASH_SINGLE":   "FLASH_SCATTER",
    "BACKUP_ALL":     "BACKUP_ALL",
    "BACKUP_SINGLE":  "BACKUP_SINGLE",
    "FRP_BYPASS":     "FRP_BYPASS",
    "FORMAT_PART":    "FORMAT_PART",
    "FORMAT_ALL":     "FORMAT_ALL",
    "UNLOCK_BL":      "UNLOCK_BL",
    "SEND_PAYLOAD":   "SEND_PAYLOAD",
    "NVRAM_READ":     "NVRAM_READ",
    "MEM_TEST":       "MEM_TEST",
    "POWER_OFF":      "POWER_OFF",
    "WD_RESET":       "WD_RESET",
}


class _Bridge(QObject):
    """Thread-safe bridge from USB thread callbacks to Qt main thread signals."""
    state_changed = pyqtSignal(object)
    log_received  = pyqtSignal(str, str)

    def on_state_change(self, state):
        self.state_changed.emit(state)

    def on_log(self, level, msg):
        self.log_received.emit(level, msg)


class ConnectionHeader(QFrame):
    def __init__(self, protocol, adb, parent=None):
        super().__init__(parent)
        self._proto      = protocol
        self._adb        = adb
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_usb)
        self._build_ui()

    def _build_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { background:#080c14; border-bottom:1px solid #1a2535; }")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        title = QLabel("MTK CLIENT <span style='color:#00d4ff'>2.0</span>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet(
            "font-size:17px; font-weight:bold; color:#607080; "
            "letter-spacing:2px; background:transparent;"
        )

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#1a2535;")

        self.state_lbl = QLabel("⬤  DISCONNECTED")
        self.state_lbl.setStyleSheet(
            "color:#ff4444; font-size:12px; min-width:190px; background:transparent;"
        )

        self.device_lbl = QLabel("")
        self.device_lbl.setStyleSheet(
            "color:#304050; font-size:11px; background:transparent;"
        )

        self.btn_auto = QPushButton("Auto-Detect")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setToolTip(
            "Automatically scan USB every 800ms.\nEnable before plugging in device."
        )
        self.btn_auto.toggled.connect(self._toggle_auto)

        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setMinimumWidth(110)
        self.btn_connect.clicked.connect(self._toggle_connect)

        layout.addWidget(title)
        layout.addWidget(sep)
        layout.addWidget(self.state_lbl)
        layout.addWidget(self.device_lbl, 1)
        layout.addWidget(self.btn_auto)
        layout.addWidget(self.btn_connect)

    def _toggle_connect(self):
        if self._proto.state in (ConnState.DISCONNECTED, ConnState.ERROR):
            self._proto.connect()
        else:
            self._proto.disconnect()

    def _toggle_auto(self, on):
        if on:
            self._poll_timer.start(800)
            self.btn_auto.setText("Auto: ON ●")
            self.btn_auto.setStyleSheet("color:#00c890;")
        else:
            self._poll_timer.stop()
            self.btn_auto.setText("Auto-Detect")
            self.btn_auto.setStyleSheet("")

    def _poll_usb(self):
        if self._proto.state == ConnState.DISCONNECTED:
            self._proto.connect()
            self._update_connected_device_label()
        elif self._proto.state == ConnState.ERROR:
            self._update_connected_device_label()

    def _update_connected_device_label(self):
        if self._proto.state in (ConnState.BROM, ConnState.PRELOADER, ConnState.DA_MODE):
            return
        try:
            devices = self._device_manager.scan_devices()
            if devices:
                dev = devices[0]
                label = f"{dev.manufacturer or dev.brand} {dev.model or dev.serial}".strip()
                if label:
                    self.device_lbl.setText(label)
                    self.device_lbl.setStyleSheet(
                        "color:#00a868; font-size:11px; background:transparent;"
                    )
        except Exception:
            pass

    def update_state(self, state, device_name=""):
        label, color = STATE_LABELS.get(state, ("⬤  UNKNOWN", "#607080"))
        self.state_lbl.setText(label)
        self.state_lbl.setStyleSheet(
            f"color:{color}; font-size:12px; min-width:190px; background:transparent;"
        )
        is_conn = state not in (ConnState.DISCONNECTED, ConnState.ERROR, ConnState.DETECTING)
        self.btn_connect.setText("DISCONNECT" if is_conn else "CONNECT")
        if device_name and device_name not in ("", "Unknown"):
            self.device_lbl.setText(device_name)
            self.device_lbl.setStyleSheet(
                "color:#00a868; font-size:11px; background:transparent;"
            )
        else:
            self.device_lbl.setText("")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTK Client 2.0 — MediaTek Flash & Repair Utility")
        self.setMinimumSize(1150, 700)
        self.resize(1380, 820)

        # Thread-safe bridge (must exist before MTKProtocol)
        self._bridge = _Bridge()
        self._bridge.state_changed.connect(self._on_state_change)
        self._bridge.log_received.connect(self._on_log)

        self._proto  = MTKProtocol(
            on_state_change=self._bridge.on_state_change,
            on_log=self._bridge.on_log,
        )
        self._engine = FlashEngine(self._proto)
        self._adb    = ADBBridge()
        self._device_manager = DeviceManager()

        self._build_ui()
        self._build_menu()
        self._connect_engine()

        self.statusBar().showMessage(
            f"MTK Client 2.0  |  {platform.system()} {platform.release()}  |  "
            "Power off device → hold Vol– → plug USB to enter BROM mode"
        )

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.header = ConnectionHeader(self._proto, self._adb)
        root_layout.addWidget(self.header)

        # Tabs | Guide split
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background:#1a2535; }")

        # Tabs
        self.tabs      = QTabWidget()
        self.tab_info  = DeviceInfoTab(self._proto, self._adb)
        self.tab_flash = FlashTab(self._engine)
        self.tab_tools = ToolsTab(self._engine, self._adb)
        self.tab_root  = RootTab(self._engine, self._adb)
        self.tab_kaeru = KaeruTab(self._engine, self._adb)
        self.tab_bypass = BypassTab(self._engine, self._adb, self._proto)
        self.tab_log   = LogTab()
        self.tab_setup = SetupTab()

        self.tabs.addTab(self.tab_info,  "📱  Device Info")
        self.tabs.addTab(self.tab_flash, "⚡  Flash")
        self.tabs.addTab(self.tab_tools, "🔧  Tools")
        self.tabs.addTab(self.tab_root,  "🌿  Root")
        self.tabs.addTab(self.tab_kaeru, "🐸  Kaeru")
        self.tabs.addTab(self.tab_bypass, "🔓  Bypass")
        self.tabs.addTab(self.tab_log,   "📋  Logs")
        self.tabs.addTab(self.tab_setup, "⚙   Setup")

        splitter.addWidget(self.tabs)

        # Guide panel
        self.guide = GuidePanel()
        splitter.addWidget(self.guide)
        splitter.setSizes([1020, 320])
        splitter.setCollapsible(1, True)

        root_layout.addWidget(splitter, 1)

        # Wire tab guide signals
        self.tab_root.guide_requested.connect(self.guide.show_guide)
        self.tab_kaeru.guide_requested.connect(self.guide.show_guide)

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        fm.addAction("Open Scatter File…", self._open_scatter)
        fm.addSeparator()
        fm.addAction("Exit", self.close)

        dm = mb.addMenu("Device")
        dm.addAction("Connect",    lambda: self._proto.connect())
        dm.addAction("Disconnect", lambda: self._proto.disconnect())
        dm.addSeparator()
        dm.addAction("Power Off",  lambda: self._proto.power_off())
        dm.addAction("WDT Reset",  lambda: self._proto.watchdog_reset())
        dm.addSeparator()
        dm.addAction("Reboot → Recovery",    lambda: self._adb.reboot("recovery"))
        dm.addAction("Reboot → Bootloader",  lambda: self._adb.reboot("bootloader"))
        dm.addAction("Reboot → EDL/BROM",    lambda: self._adb.reboot_edl())

        gm = mb.addMenu("Guide")
        guides = [
            ("Getting Started",         "DISCONNECTED"),
            ("How to Flash Firmware",   "FLASH_SCATTER"),
            ("Bootloader Unlock",       "UNLOCK_BL"),
            ("Root Guide",              "ROOT_WORKFLOW"),
            ("FRP Bypass",              "FRP_BYPASS"),
            ("NVRAM Backup",            "NVRAM_READ"),
            ("Memory Test",             "MEM_TEST"),
        ]
        for label, key in guides:
            k = key  # capture
            gm.addAction(label, lambda _, k=k: self.guide.show_guide(k))

        hm = mb.addMenu("Help")
        hm.addAction("BROM Mode Guide", self._show_brom_guide)
        hm.addAction("About",           self._show_about)

    def _connect_engine(self):
        self._engine.operation_started.connect(
            lambda name: self.guide.show_guide(OP_GUIDE_KEYS.get(name, "DISCONNECTED"))
        )
        self._engine.log_message.connect(
            lambda lvl, msg: self.tab_log.append_log(lvl, msg)
        )
        self._engine.status_updated.connect(self.statusBar().showMessage)
        self._engine.operation_finished.connect(
            lambda ok, msg: self.statusBar().showMessage(("✓  " if ok else "✗  ") + msg)
        )

    # ── State (main thread) ───────────────────────────────────────────────────
    def _on_state_change(self, state):
        device_name = ""
        if state in (ConnState.BROM, ConnState.PRELOADER, ConnState.DA_MODE):
            self.tab_info.refresh()
            info = self._proto.get_device_info()
            device_name = info.chipset_name
            self.statusBar().showMessage(
                f"Connected  [{STATE_LABELS[state][0].strip()}]  —  {device_name}"
            )
        elif state == ConnState.DISCONNECTED:
            self.statusBar().showMessage("Device disconnected.")
        elif state == ConnState.ERROR:
            self.statusBar().showMessage("Connection error — check Logs tab.")

        self.header.update_state(state, device_name)
        self.guide.show_guide(STATE_GUIDE_KEYS.get(state, "DISCONNECTED"))
        # Notify Kaeru tab of device hw_code
        if state in (ConnState.BROM, ConnState.PRELOADER, ConnState.DA_MODE):
            info = self._proto.get_device_info()
            self.tab_kaeru.update_device(info.hw_code)

    def _on_log(self, level, msg):
        self.tab_log.append_log(level, msg)

    # ── Menu handlers ─────────────────────────────────────────────────────────
    def _open_scatter(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Scatter File", "",
            "Scatter Files (*.txt *.cfg);;All Files (*)"
        )
        if path:
            self.tabs.setCurrentWidget(self.tab_flash)
            self.tab_flash._load_scatter(path)
            self.guide.show_guide("FLASH_SCATTER")

    def _show_brom_guide(self):
        self.guide.show_guide("DISCONNECTED")
        QMessageBox.information(self, "BROM Mode Guide",
            "How to enter BROM / EDL mode:\n\n"
            "Method 1 — Vol button:\n"
            "  Power off → hold Vol– → plug USB\n"
            "  (try Vol+ if Vol– doesn't work)\n\n"
            "Method 2 — Battery out:\n"
            "  Remove battery → hold Vol– → plug USB\n\n"
            "Method 3 — ADB:\n"
            "  adb reboot edl\n\n"
            "V6 devices (Dimensity MT6853+):\n"
            "  BROM is locked. Load a V6 loader in\n"
            "  Tools → Payload / Auth tab first.\n\n"
            "LED: Solid red/white = BROM mode.\n"
            "Check the Guide panel on the right for step-by-step instructions."
        )

    def _show_about(self):
        QMessageBox.about(self, "About MTK Client 2.0",
            "<h3>MTK Client 2.0</h3>"
            "<p>MediaTek Flash, Repair &amp; Root Utility</p>"
            "<p>Cross-platform: Fedora / Linux / Windows</p>"
            "<p><b>Chipsets:</b> MT6580 → MT6985 (Dimensity 9200)</p>"
            "<p><b>Features:</b><br>"
            "Scatter flashing · Partition backup/restore · FRP bypass<br>"
            "BROM payload · NVRAM backup · Bootloader unlock<br>"
            "Root assistant (Magisk/KernelSU/APatch) · ADB shell<br>"
            "Memory test · Context-aware Guide panel · Fedora auto-setup</p>"
        )
