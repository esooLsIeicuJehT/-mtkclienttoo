"""
Kaeru Workshop Tab — full integration for kaeru ARMv7 payload development.

Context Flow:
  Device Detected → Auto-populate device info → Eligibility check →
  LK Extraction → Board file generation → Defconfig generation →
  API template browser → Build → Flash

Kaeru: https://github.com/R0rt1z2/kaeru
  ARMv7 payload for arbitrary code execution on MTK LK bootloaders.
  Supports: custom fastboot commands, boot mode override, NOP/FORCE_RETURN patches.
"""
import os
import re
import webbrowser
import subprocess
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QLineEdit, QTextEdit,
    QComboBox, QSplitter, QTabWidget, QFrame, QScrollArea,
    QFileDialog, QMessageBox, QProgressBar, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont, QTextCharFormat, QColor, QSyntaxHighlighter

from core import FlashEngine, ADBBridge
from core.mtk_chipset_db import (
    lookup, lookup_by_name, all_chips, kaeru_compatible_chips,
    KAERU_DEFCONFIG_TEMPLATES, KAERU_DEFAULT_DEFCONFIG,
    get_payload_url, is_kaeru_compatible, is_v6
)
from core.scatter_generator import ScatterGenerator
from core.payload_manager import PayloadManager
from utils.logger import get_logger

log_fn = get_logger("kaeru")  # Initialized logger


# ── C Syntax Highlighter ──────────────────────────────────────────────────────
class CSyntaxHighlighter(QSyntaxHighlighter):
    """Minimal C syntax highlighter for the board file editor."""

    def __init__(self, doc):
        super().__init__(doc)
        self._rules = []

        def rule(pattern, color, bold=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if bold:
                fmt.setFontWeight(700)
            self._rules.append((re.compile(pattern), fmt))

        # Keywords
        rule(
            r'\b(void|int|uint8_t|uint16_t|uint32_t|uint64_t|char|const|static|'
            r'if|else|for|while|return|include|define|ifdef|endif|NULL|true|false|'
            r'bootmode_t|BOOTMODE_\w+)\b',
            "#569cd6", bold=True
        )
        # Preprocessor
        rule(r'#\w+', "#c586c0")
        # Strings
        rule(r'"[^"\\]*(?:\\.[^"\\]*)*"', "#ce9178")
        # Comments
        rule(r'//[^\n]*', "#6a9955")
        rule(r'/\*[\s\S]*?\*/', "#6a9955")
        # Macros (ALL_CAPS)
        rule(r'\b[A-Z_][A-Z0-9_]{3,}\b', "#4ec9b0")
        # Functions
        rule(r'\b([a-z_]\w*)\s*(?=\()', "#dcdcaa")
        # Numbers (hex + decimal)
        rule(r'\b0x[0-9A-Fa-f]+\b', "#b5cea8")
        rule(r'\b\d+\b', "#b5cea8")

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── Kaeru API Templates Database ─────────────────────────────────────────────
KAERU_TEMPLATES = {
    "Minimal board_late_init": """\
/* Called by kaeru after payload injection, before fastboot starts */
void board_late_init(void) {
    /* Your custom code runs here */
    video_printf("Kaeru is active!\\n");
}
""",

    "Custom Fastboot Command": """\
/* Example: fastboot oem hello */
void cmd_hello(const char *arg, void *data, unsigned size) {
    fastboot_info("Hello from kaeru!");
    fastboot_info("Arg: %s", arg);
    fastboot_okay("");   /* Always call okay() OR fail() to finish */
}

void board_late_init(void) {
    /* Register: prefix, handler, allow_locked (always 1) */
    fastboot_register("oem hello",         cmd_hello,         1);
}
""",

    "Remove Bootloader Warning": """\
/* Disable the "bootloader is unlocked" warning screen */
void board_late_init(void) {
    /*
     * Use SEARCH_PATTERN to find the BL warning function by its
     * first bytes (extracted from your LK with Ghidra).
     * Replace the pattern bytes below with those from YOUR LK.
     *
     * Example: THUMB mode function starting with 2D E9 F0 43
     * → little-endian pairs: 0xE92D, 0x43F0
     */
    uint32_t addr = SEARCH_PATTERN(LK_START, LK_END,
                                   0xE92D, 0x43F0,  /* <-- YOUR bytes */
                                   0x4602, 0x4B1E);
    if (addr) {
        video_printf("Found warning fn @ 0x%08X\\n", addr);
        /* THUMB BL = 4 bytes = 2 NOPs */
        NOP(addr, 2);
    } else {
        video_printf("Warning fn not found - check pattern!\\n");
    }
}
""",

    "Override Boot Mode": """\
/* Force device into recovery mode on every boot */
void board_late_init(void) {
    bootmode_t current = get_bootmode();
    show_bootmode(current);   /* Print current mode to screen */

    /* Override: always boot to recovery */
    set_bootmode(BOOTMODE_RECOVERY);
    video_printf("Boot mode forced to: RECOVERY\\n");
}
""",

    "Custom Boot Key Combo": """\
/*
 * Remap button combos.
 * mtk_detect_key() checks if a key is pressed.
 * Keys: VOL_UP=0, VOL_DOWN=1, POWER=2
 */
void board_late_init(void) {
    /* If Vol+ pressed at boot → force fastboot */
    if (mtk_detect_key(0)) {
        video_printf("[KAERU] Vol+ detected → FASTBOOT\\n");
        set_bootmode(BOOTMODE_FASTBOOT);
        return;
    }
    /* If Vol- pressed at boot → force recovery */
    if (mtk_detect_key(1)) {
        video_printf("[KAERU] Vol- detected → RECOVERY\\n");
        set_bootmode(BOOTMODE_RECOVERY);
        return;
    }
}
""",

    "Force Function Return Value": """\
/*
 * Make a function always return a specific value.
 * Example: spoof bootloader lock status (always return "unlocked").
 *
 * Find the lock-check function in Ghidra by searching for code that
 * reads seccfg/oem_lock_info, then get its first bytes.
 */
void board_late_init(void) {
    uint32_t addr = SEARCH_PATTERN(LK_START, LK_END,
                                   0xB573, 0x4C0F,  /* <-- YOUR bytes */
                                   0x2300, 0x6823);
    if (addr) {
        video_printf("Lock-check fn @ 0x%08X → forcing return 0\\n", addr);
        /* 0 = unlocked on most MTK implementations */
        FORCE_RETURN(addr, 0);
    }
}
""",

    "Memory Hexdump (Debug)": """\
/*
 * Dump first 0x200 bytes of LK to screen + UART.
 * Useful for verifying you have the right memory layout.
 */
void board_late_init(void) {
    video_printf("=== LK Hexdump (first 0x200 bytes) ===\\n");
    video_hexdump((void *)CONFIG_BOOTLOADER_BASE, 0x200);
    uart_hexdump((void *)CONFIG_BOOTLOADER_BASE, 0x200);
}
""",

    "Add Fastboot Oem Unlock Bypass": """\
/*
 * Register 'fastboot oem unlock-go' that bypasses the unlock confirmation
 * and directly writes the seccfg unlock state.
 */
void cmd_unlock_go(const char *arg, void *data, unsigned size) {
    /* Write unlock=1 to boot mode address as a flag */
    WRITE32(CONFIG_BOOTMODE_ADDRESS + 0x10, 0x77654321);
    fastboot_info("OEM unlock bypass applied.");
    fastboot_info("Reboot device to complete.");
    fastboot_okay("");
}

void board_late_init(void) {
    fastboot_register("oem unlock-go", cmd_unlock_go, 1);
    video_printf("[KAERU] oem unlock-go registered\\n");
}
""",
}

# ── Board file template ───────────────────────────────────────────────────────
BOARD_TEMPLATE = """\
// SPDX-License-Identifier: AGPL-3.0-only
/*
 * {model} ({codename}) — kaeru board support
 * SoC: {soc}
 *
 * Auto-generated by MTK Client 2.0 — Kaeru Workshop
 * Review and adjust offsets before building!
 *
 * Useful resources:
 *   kaeru wiki: https://github.com/R0rt1z2/kaeru/wiki
 *   Ghidra (disassembler): https://ghidra-sre.org/
 */

#include <lib/fastboot.h>
#include <lib/bootmode.h>
#include <lib/common.h>

/* ── Custom Fastboot Commands ─────────────────────────────────────── */

/**
 * oem hello — sanity check command.
 * Usage: fastboot oem hello
 */
static void cmd_hello(const char *arg, void *data, unsigned sz) {{
    fastboot_info("Kaeru is alive on {model}!");
    fastboot_info("SoC: {soc}  |  LK base: 0x{lk_base:08X}");
    fastboot_okay("");
}}

/**
 * oem dump-bootmode — shows current boot mode.
 * Usage: fastboot oem dump-bootmode
 */
static void cmd_dump_bootmode(const char *arg, void *data, unsigned sz) {{
    bootmode_t mode = get_bootmode();
    fastboot_info("Current boot mode: %s (%d)",
                  bootmode2str(mode), (int)mode);
    fastboot_okay("");
}}

/* ── Board Initialization ─────────────────────────────────────────── */

void board_late_init(void) {{
    /* ── 1. Visual confirmation ──────────────────────────────── */
    video_printf("\\n[KAERU] Running on {model} ({soc})\\n");
    video_printf("[KAERU] LK base: 0x{lk_base:08X}\\n");

    /* ── 2. Register fastboot commands ──────────────────────── */
    fastboot_register("oem hello",         cmd_hello,        1);
    fastboot_register("oem dump-bootmode", cmd_dump_bootmode,1);

    /* ── 3. Show current boot mode ──────────────────────────── */
    bootmode_t mode = get_bootmode();
    show_bootmode(mode);

    /*
     * ── 4. TODO: Add your patches here ──────────────────────
     *
     * To remove unlock warning (find pattern with Ghidra):
     *   uint32_t fn = SEARCH_PATTERN(LK_START, LK_END, 0x????, 0x????);
     *   if (fn) NOP(fn, 2);
     *
     * To force a function to return a value:
     *   FORCE_RETURN(fn_address, 0);
     *
     * To patch memory directly:
     *   WRITE32(CONFIG_BOOTMODE_ADDRESS, BOOTMODE_FASTBOOT);
     */
}}
"""

DEFCONFIG_TEMPLATE = """\
# {model} ({codename}) — kaeru defconfig
# SoC: {soc}
# Auto-generated by MTK Client 2.0
#
# IMPORTANT: These addresses are ESTIMATES based on chipset family.
# You MUST verify CONFIG_APP_ADDRESS, CONFIG_FASTBOOT_CONTINUE,
# and CONFIG_BOOTMODE_ADDRESS using Ghidra on your actual lk.bin!
# See: https://github.com/R0rt1z2/kaeru/wiki/Porting-kaeru-to-a-new-device

CONFIG_BOARD="{codename}"
CONFIG_VENDOR="{vendor}"

# Bootloader memory layout
CONFIG_BOOTLOADER_BASE=0x{lk_base:08X}
CONFIG_BOOTLOADER_SIZE=0x{lk_size:08X}

# These MUST be found with Ghidra — the values below are estimates!
CONFIG_APP_ADDRESS=0x{app_addr:08X}
CONFIG_FASTBOOT_CONTINUE=0x{fastboot_cont:08X}
CONFIG_BOOTMODE_ADDRESS=0x{bootmode_addr:08X}

# Enable features
CONFIG_LK_LOG_STORE=y
CONFIG_KAERU_FASTBOOT=y
CONFIG_KAERU_BOOTMODE=y

# Debug (disable for production)
# CONFIG_DEBUG=y
"""


# ── Worker for background operations ─────────────────────────────────────────
class KaeruWorker(QThread):
    log_line  = pyqtSignal(str, str)   # (level, message)
    progress  = pyqtSignal(int, int)   # (current, total)
    finished  = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            ok     = isinstance(result, bool) and result
            msg    = "" if ok is True else str(result) if result else "Done"
            self.finished.emit(bool(result), str(msg))
        except Exception as e:
            self.finished.emit(False, str(e))


# ── Main Tab ──────────────────────────────────────────────────────────────────
class KaeruTab(QWidget):
    """
    Kaeru Workshop — fancy IDE-like tab for kaeru payload development.

    Panels:
      Left:   Device info + eligibility + LK tools
      Center: Code editor (board.c / defconfig / template browser)
      Right:  API reference + build output
    """

    guide_requested = pyqtSignal(str)

    def __init__(self, engine: FlashEngine, adb: ADBBridge, parent=None):
        super().__init__(parent)
        self._engine        = engine
        self._adb           = adb
        self._scatter_gen   = ScatterGenerator(adb=adb)
        self._payload_mgr   = PayloadManager.instance()
        self._worker: Optional[KaeruWorker] = None
        self._lk_path: str  = ""
        self._current_hw    = 0
        self._codename      = "device"
        self._vendor        = "Unknown"
        self._model         = "Unknown Device"
        self._soc_name      = "Unknown"
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background:#1a2535; }")

        # Left panel
        left = self._build_left_panel()
        left.setMinimumWidth(270)
        left.setMaximumWidth(360)
        splitter.addWidget(left)

        # Center: editor tabs
        center = self._build_center_panel()
        splitter.addWidget(center)

        # Right: API reference + build log
        right = self._build_right_panel()
        right.setMinimumWidth(260)
        right.setMaximumWidth(380)
        splitter.addWidget(right)

        splitter.setSizes([290, 700, 300])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(2, True)
        root.addWidget(splitter)

    # ── Left Panel: Device / Status / LK Tools ────────────────────────────────
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#080c14; border-right:1px solid #1a2535;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QLabel("🐸  KAERU WORKSHOP")
        hdr.setStyleSheet(
            "color:#00d4ff; font-size:13px; font-weight:bold; "
            "letter-spacing:2px; padding:6px 0;"
        )
        layout.addWidget(hdr)

        lnk = QPushButton("Open kaeru GitHub →")
        lnk.setStyleSheet(
            "color:#4a9eff; background:transparent; border:none; "
            "text-align:left; font-size:11px; padding:0;"
        )
        lnk.setCursor(Qt.PointingHandCursor)
        lnk.clicked.connect(lambda: webbrowser.open("https://github.com/R0rt1z2/kaeru"))
        layout.addWidget(lnk)

        self._add_separator(layout)

        # ── Device Info ───────────────────────────────────────────────────────
        dev_box = QGroupBox("Detected Device")
        dev_layout = QGridLayout(dev_box)
        dev_layout.setSpacing(4)

        fields = ["SoC", "Codename", "Vendor", "Model", "HW Code", "Arch", "V6 Auth"]
        self._dev_labels: dict[str, QLabel] = {}
        for i, f in enumerate(fields):
            lbl = QLabel(f + ":")
            lbl.setStyleSheet("color:#405060; font-size:11px;")
            val = QLabel("—")
            val.setStyleSheet("color:#8090a8; font-size:11px;")
            self._dev_labels[f] = val
            dev_layout.addWidget(lbl, i, 0)
            dev_layout.addWidget(val, i, 1)

        btn_refresh = QPushButton("↻  Refresh from ADB")
        btn_refresh.setMinimumHeight(28)
        btn_refresh.clicked.connect(self._refresh_device_info)
        dev_layout.addWidget(btn_refresh, len(fields), 0, 1, 2)
        layout.addWidget(dev_box)

        # ── Eligibility ───────────────────────────────────────────────────────
        elig_box = QGroupBox("Kaeru Eligibility")
        elig_layout = QVBoxLayout(elig_box)
        self.elig_lbl = QLabel("Connect device to check eligibility.")
        self.elig_lbl.setWordWrap(True)
        self.elig_lbl.setStyleSheet("color:#607080; font-size:11px;")
        elig_layout.addWidget(self.elig_lbl)

        self.elig_detail = QLabel("")
        self.elig_detail.setWordWrap(True)
        self.elig_detail.setStyleSheet("color:#505060; font-size:10px;")
        elig_layout.addWidget(self.elig_detail)

        btn_elig = QPushButton("▶  Check Eligibility")
        btn_elig.setMinimumHeight(28)
        btn_elig.clicked.connect(self._check_eligibility)
        elig_layout.addWidget(btn_elig)
        layout.addWidget(elig_box)

        # ── Device Configuration ──────────────────────────────────────────────
        cfg_box = QGroupBox("Device Configuration")
        cfg_layout = QGridLayout(cfg_box)
        cfg_layout.setSpacing(6)

        def lbl_field(label, row, default=""):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color:#405060; font-size:11px;")
            edit = QLineEdit(default)
            edit.setStyleSheet("font-size:11px;")
            cfg_layout.addWidget(lbl, row, 0)
            cfg_layout.addWidget(edit, row, 1)
            return edit

        self.edit_codename = lbl_field("Codename", 0, "device")
        self.edit_vendor   = lbl_field("Vendor",   1, "Unknown")
        self.edit_model    = lbl_field("Model",    2, "Unknown Device")
        self.edit_soc      = lbl_field("SoC",      3, "MT6761")
        layout.addWidget(cfg_box)

        # ── LK Extraction ─────────────────────────────────────────────────────
        lk_box = QGroupBox("LK Extraction")
        lk_layout = QVBoxLayout(lk_box)

        lk_info = QLabel(
            "Kaeru patches your LK image. Extract it from the device\n"
            "or load a local copy."
        )
        lk_info.setStyleSheet("color:#506070; font-size:10px;")
        lk_info.setWordWrap(True)
        lk_layout.addWidget(lk_info)

        self.lk_path_lbl = QLabel("No LK loaded")
        self.lk_path_lbl.setStyleSheet(
            "color:#405060; font-size:10px; font-style:italic;"
        )
        lk_layout.addWidget(self.lk_path_lbl)

        btn_row = QHBoxLayout()
        btn_pull = QPushButton("Pull LK (ADB)")
        btn_pull.setMinimumHeight(28)
        btn_pull.clicked.connect(self._pull_lk_adb)
        btn_open = QPushButton("Open File…")
        btn_open.setMinimumHeight(28)
        btn_open.clicked.connect(self._open_lk_file)
        btn_row.addWidget(btn_pull)
        btn_row.addWidget(btn_open)
        lk_layout.addLayout(btn_row)
        layout.addWidget(lk_box)

        # ── Scatter Generator ─────────────────────────────────────────────────
        scat_box = QGroupBox("Scatter File Auto-Generator")
        scat_layout = QVBoxLayout(scat_box)
        scat_info = QLabel(
            "Auto-reads partition table from connected device\n"
            "and generates a ready-to-use scatter file."
        )
        scat_info.setStyleSheet("color:#506070; font-size:10px;")
        scat_info.setWordWrap(True)
        scat_layout.addWidget(scat_info)

        btn_gen_scat = QPushButton("⚡  Generate Scatter File")
        btn_gen_scat.setObjectName("btn_flash")
        btn_gen_scat.setMinimumHeight(30)
        btn_gen_scat.clicked.connect(self._generate_scatter)
        scat_layout.addWidget(btn_gen_scat)
        layout.addWidget(scat_box)

        # ── Payload Manager ───────────────────────────────────────────────────
        pay_box = QGroupBox("Payload Manager")
        pay_layout = QVBoxLayout(pay_box)

        self.payload_status = QLabel("Status: unknown")
        self.payload_status.setStyleSheet("color:#607080; font-size:10px;")
        self.payload_status.setWordWrap(True)
        pay_layout.addWidget(self.payload_status)

        self.payload_progress = QProgressBar()
        self.payload_progress.setMaximumHeight(8)
        self.payload_progress.hide()
        pay_layout.addWidget(self.payload_progress)

        btn_pay_row = QHBoxLayout()
        btn_download = QPushButton("↓ Download")
        btn_download.setMinimumHeight(26)
        btn_download.clicked.connect(self._download_payload)
        btn_import = QPushButton("+ Import")
        btn_import.setMinimumHeight(26)
        btn_import.clicked.connect(self._import_payload)
        btn_pay_row.addWidget(btn_download)
        btn_pay_row.addWidget(btn_import)
        pay_layout.addLayout(btn_pay_row)
        layout.addWidget(pay_box)

        layout.addStretch()

        # Status
        self.left_status = QLabel("Ready.")
        self.left_status.setStyleSheet(
            "color:#405060; font-size:10px; padding-top:4px;"
        )
        layout.addWidget(self.left_status)
        return panel

    # ── Center Panel: Code Editor ─────────────────────────────────────────────
    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#0d1117;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("background:#080c14; border-bottom:1px solid #1a2535;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 0, 8, 0)
        tb_layout.setSpacing(8)

        file_lbl = QLabel("Editor")
        file_lbl.setStyleSheet("color:#607080; font-size:11px; font-weight:bold;")
        tb_layout.addWidget(file_lbl)

        # File selector buttons (act as tabs)
        self._editor_btns: dict[str, QPushButton] = {}
        for fname in ["board.c", "defconfig", "templates"]:
            btn = QPushButton(fname)
            btn.setCheckable(True)
            btn.setMinimumHeight(24)
            btn.setMinimumWidth(90)
            btn.setStyleSheet(
                "QPushButton { background:#111a28; color:#607080; border:1px solid #1a2535; "
                "border-radius:3px; font-size:11px; padding:0 8px; }"
                "QPushButton:checked { background:#1a2e48; color:#00d4ff; "
                "border-color:#00d4ff; }"
            )
            btn.clicked.connect(lambda _, n=fname: self._switch_editor(n))
            tb_layout.addWidget(btn)
            self._editor_btns[fname] = btn

        tb_layout.addStretch()

        btn_copy = QPushButton("⎘ Copy")
        btn_copy.setMinimumHeight(24)
        btn_copy.setMinimumWidth(60)
        btn_copy.clicked.connect(self._copy_editor_content)
        btn_save = QPushButton("💾 Save")
        btn_save.setMinimumHeight(24)
        btn_save.setMinimumWidth(60)
        btn_save.clicked.connect(self._save_editor_content)
        tb_layout.addWidget(btn_copy)
        tb_layout.addWidget(btn_save)

        layout.addWidget(toolbar)

        # The editor stacks
        self._editor_pages: dict[str, QWidget] = {}

        # board.c editor
        board_editor = self._make_code_editor()
        self._board_editor: QTextEdit = board_editor.findChild(QTextEdit)
        self._editor_pages["board.c"] = board_editor

        # defconfig editor
        defconfig_editor = self._make_code_editor(monospace=True)
        self._defconfig_editor: QTextEdit = defconfig_editor.findChild(QTextEdit)
        self._editor_pages["defconfig"] = defconfig_editor

        # Template browser
        templates_page = self._build_template_browser()
        self._editor_pages["templates"] = templates_page

        for page in self._editor_pages.values():
            layout.addWidget(page)

        # Generate initial content
        self._switch_editor("board.c")
        self._regenerate_board_file()
        self._regenerate_defconfig()

        # Bottom: generate buttons
        gen_bar = QWidget()
        gen_bar.setFixedHeight(40)
        gen_bar.setStyleSheet("background:#080c14; border-top:1px solid #1a2535;")
        gen_layout = QHBoxLayout(gen_bar)
        gen_layout.setContentsMargins(8, 0, 8, 0)

        btn_gen_board = QPushButton("⚡  Generate board.c")
        btn_gen_board.setMinimumHeight(28)
        btn_gen_board.clicked.connect(self._regenerate_board_file)
        btn_gen_def   = QPushButton("⚡  Generate defconfig")
        btn_gen_def.setMinimumHeight(28)
        btn_gen_def.clicked.connect(self._regenerate_defconfig)
        btn_export    = QPushButton("📁  Export to kaeru dir…")
        btn_export.setObjectName("btn_flash")
        btn_export.setMinimumHeight(28)
        btn_export.clicked.connect(self._export_to_kaeru)

        gen_layout.addWidget(btn_gen_board)
        gen_layout.addWidget(btn_gen_def)
        gen_layout.addStretch()
        gen_layout.addWidget(btn_export)
        layout.addWidget(gen_bar)

        return panel

    def _make_code_editor(self, monospace: bool = True) -> QWidget:
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        editor    = QTextEdit()
        editor.setObjectName("log_view")
        editor.setReadOnly(False)
        font = QFont("Cascadia Code, Consolas, Courier New, monospace", 11)
        font.setStyleHint(QFont.Monospace)
        editor.setFont(font)
        editor.setStyleSheet(
            "background:#0d1117; color:#c9d1d9; border:none; "
            "selection-background-color:#264f78;"
        )
        editor.setTabStopDistance(28)
        CSyntaxHighlighter(editor.document())
        layout.addWidget(editor)
        return container

    def _build_template_browser(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:#0d1117;")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left: template list
        list_panel = QWidget()
        list_panel.setMaximumWidth(250)
        list_panel.setStyleSheet("background:#080c14; border-right:1px solid #1a2535;")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(6, 6, 6, 6)

        lbl = QLabel("API Templates")
        lbl.setStyleSheet("color:#607080; font-size:11px; font-weight:bold;")
        list_layout.addWidget(lbl)

        self._tmpl_tree = QTreeWidget()
        self._tmpl_tree.setHeaderHidden(True)
        self._tmpl_tree.setStyleSheet(
            "QTreeWidget { background:#080c14; color:#8090a8; border:none; "
            "font-size:11px; } "
            "QTreeWidget::item:selected { background:#1a2e48; color:#00d4ff; }"
        )
        for name in KAERU_TEMPLATES:
            item = QTreeWidgetItem([name])
            self._tmpl_tree.addTopLevelItem(item)
        self._tmpl_tree.currentItemChanged.connect(self._on_template_selected)
        list_layout.addWidget(self._tmpl_tree)

        btn_append = QPushButton("Append to board.c →")
        btn_append.setMinimumHeight(28)
        btn_append.clicked.connect(self._append_template_to_board)
        list_layout.addWidget(btn_append)
        layout.addWidget(list_panel)

        # Right: preview
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self._tmpl_preview = QTextEdit()
        self._tmpl_preview.setReadOnly(True)
        font = QFont("Cascadia Code, Consolas, monospace", 11)
        font.setStyleHint(QFont.Monospace)
        self._tmpl_preview.setFont(font)
        self._tmpl_preview.setStyleSheet(
            "background:#0d1117; color:#c9d1d9; border:none;"
        )
        CSyntaxHighlighter(self._tmpl_preview.document())
        preview_layout.addWidget(self._tmpl_preview)
        layout.addWidget(preview_panel)

        # Select first template
        if self._tmpl_tree.topLevelItemCount() > 0:
            self._tmpl_tree.setCurrentItem(self._tmpl_tree.topLevelItem(0))

        return page

    # ── Right Panel: API Reference + Build Log ────────────────────────────────
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#080c14; border-left:1px solid #1a2535;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        right_tabs = QTabWidget()
        right_tabs.setDocumentMode(True)
        right_tabs.setStyleSheet(
            "QTabWidget::pane { border:none; } "
            "QTabBar::tab { background:#080c14; color:#607080; padding:6px 12px; "
            "font-size:11px; border-bottom:2px solid transparent; } "
            "QTabBar::tab:selected { color:#00d4ff; border-bottom-color:#00d4ff; }"
        )

        # API Reference tab
        right_tabs.addTab(self._build_api_reference(), "API Ref")
        # Build tab
        right_tabs.addTab(self._build_build_panel(), "Build")
        # Chip Browser tab
        right_tabs.addTab(self._build_chip_browser(), "All Chips")

        layout.addWidget(right_tabs)
        return panel

    def _build_api_reference(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:#080c14;")

        inner = QWidget()
        inner.setStyleSheet("background:#080c14;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        def section(title, content):
            box = QGroupBox(title)
            box.setStyleSheet(
                "QGroupBox { color:#4a9eff; font-size:11px; font-weight:bold; "
                "border:1px solid #1a2535; border-radius:4px; margin-top:8px; "
                "padding-top:6px; } "
                "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
            )
            bl = QVBoxLayout(box)
            lbl = QLabel(content)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            lbl.setStyleSheet("color:#8090a8; font-size:10px; line-height:150%;")
            bl.addWidget(lbl)
            layout.addWidget(box)

        section("Debug API",
            "<b>printf(fmt, ...)</b> → UART + expdb log<br>"
            "<b>video_printf(fmt, ...)</b> → Screen output<br>"
            "<b>video_hexdump(ptr, len)</b> → Hex dump to screen<br>"
            "<b>uart_hexdump(ptr, len)</b> → Hex dump to UART<br>"
        )
        section("Fastboot API",
            "<b>fastboot_register(cmd, handler, 1)</b> → Register command<br>"
            "<b>fastboot_info(fmt, ...)</b> → Send INFO response<br>"
            "<b>fastboot_okay(\"\")</b> → Finish with success<br>"
            "<b>fastboot_fail(msg)</b> → Finish with error<br>"
        )
        section("Boot Mode API",
            "<b>get_bootmode()</b> → Current boot mode<br>"
            "<b>set_bootmode(mode)</b> → Set boot mode<br>"
            "<b>show_bootmode(mode)</b> → Print to screen<br>"
            "<b>bootmode2str(mode)</b> → Name string<br>"
            "<br>Modes: NORMAL=0, META=1, RECOVERY=2,<br>"
            "FACTORY=4, FASTBOOT=99, ERECOVERY=101"
        )
        section("Memory / Patch API",
            "<b>READ32/WRITE32(addr, val)</b> → 32-bit R/W<br>"
            "<b>READ8/WRITE8, READ16/WRITE16</b> → 8/16-bit<br>"
            "<b>SET32/CLR32(addr, mask)</b> → Bit set/clear<br>"
            "<br>"
            "<b>SEARCH_PATTERN(start, end, ...)</b> → Find THUMB fn<br>"
            "<b>SEARCH_PATTERN_ARM(...)</b> → Find ARM fn<br>"
            "<b>FORCE_RETURN(addr, val)</b> → Override fn return (THUMB)<br>"
            "<b>FORCE_RETURN_ARM(addr, val)</b> → ARM version<br>"
            "<b>NOP(addr, count)</b> → Insert THUMB NOPs<br>"
            "<b>NOP_ARM(addr, count)</b> → Insert ARM NOPs<br>"
        )
        section("Config Macros",
            "<b>CONFIG_BOOTLOADER_BASE</b> → LK load address<br>"
            "<b>CONFIG_BOOTLOADER_SIZE</b> → LK image size<br>"
            "<b>CONFIG_APP_ADDRESS</b> → App entry point<br>"
            "<b>CONFIG_FASTBOOT_CONTINUE</b> → Fastboot resume fn<br>"
            "<b>CONFIG_BOOTMODE_ADDRESS</b> → Bootmode global var<br>"
            "<b>LK_START / LK_END</b> → Search range macros<br>"
        )
        section("board_late_init()",
            "Your entry point. Called by kaeru after payload injection,<br>"
            "before fastboot starts. Register commands, patch functions,<br>"
            "and set boot modes here."
        )

        wiki_btn = QPushButton("📖  Open Full Wiki")
        wiki_btn.setMinimumHeight(30)
        wiki_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/R0rt1z2/kaeru/wiki")
        )
        layout.addWidget(wiki_btn)
        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_build_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Build environment
        env_box = QGroupBox("Build Environment")
        env_layout = QGridLayout(env_box)

        env_layout.addWidget(QLabel("Kaeru dir:"), 0, 0)
        self.kaeru_dir_edit = QLineEdit()
        self.kaeru_dir_edit.setPlaceholderText("/path/to/kaeru")
        env_layout.addWidget(self.kaeru_dir_edit, 0, 1)
        btn_browse_kaeru = QPushButton("…")
        btn_browse_kaeru.setMaximumWidth(30)
        btn_browse_kaeru.clicked.connect(self._browse_kaeru_dir)
        env_layout.addWidget(btn_browse_kaeru, 0, 2)

        env_layout.addWidget(QLabel("Build method:"), 1, 0)
        self.build_method = QComboBox()
        self.build_method.addItems(["Docker (recommended)", "Native (arm-linux-gnueabihf-gcc)"])
        env_layout.addWidget(self.build_method, 1, 1, 1, 2)
        layout.addWidget(env_box)

        # Build actions
        action_box = QGroupBox("Actions")
        action_layout = QVBoxLayout(action_box)
        btn_setup = QPushButton("1. Run setup.sh (generate board files)")
        btn_setup.setMinimumHeight(30)
        btn_setup.clicked.connect(self._run_kaeru_setup)
        btn_build = QPushButton("2. Build kaeru payload")
        btn_build.setObjectName("btn_flash")
        btn_build.setMinimumHeight(30)
        btn_build.clicked.connect(self._run_kaeru_build)
        btn_flash_lk = QPushButton("3. Flash patched LK")
        btn_flash_lk.setObjectName("btn_warn")
        btn_flash_lk.setMinimumHeight(30)
        btn_flash_lk.clicked.connect(self._flash_patched_lk)
        action_layout.addWidget(btn_setup)
        action_layout.addWidget(btn_build)
        action_layout.addWidget(btn_flash_lk)
        layout.addWidget(action_box)

        # Build progress
        self.build_progress = QProgressBar()
        self.build_progress.setMaximumHeight(8)
        self.build_progress.hide()
        layout.addWidget(self.build_progress)

        # Build log
        log_box = QGroupBox("Build Log")
        log_layout = QVBoxLayout(log_box)
        self.build_log = QTextEdit()
        self.build_log.setReadOnly(True)
        font = QFont("Cascadia Code, Consolas, monospace", 10)
        font.setStyleHint(QFont.Monospace)
        self.build_log.setFont(font)
        self.build_log.setStyleSheet(
            "background:#060810; color:#8090a8; border:none;"
        )
        self.build_log.setMaximumHeight(220)
        btn_clear_log = QPushButton("Clear")
        btn_clear_log.setMaximumWidth(70)
        btn_clear_log.clicked.connect(self.build_log.clear)
        log_layout.addWidget(self.build_log)
        log_layout.addWidget(btn_clear_log, 0, Qt.AlignRight)
        layout.addWidget(log_box, 1)
        return page

    def _build_chip_browser(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        search = QLineEdit()
        search.setPlaceholderText("Search chips…")
        search.textChanged.connect(self._filter_chip_browser)
        layout.addWidget(search)

        self._chip_tree = QTreeWidget()
        self._chip_tree.setHeaderLabels(["Chip", "Marketing", "Arch", "Kaeru"])
        self._chip_tree.setStyleSheet(
            "QTreeWidget { background:#080c14; color:#8090a8; border:none; font-size:10px; }"
            "QTreeWidget::item:selected { background:#1a2e48; color:#c9d1d9; }"
        )
        self._chip_tree.header().setStyleSheet("color:#607080; font-size:10px;")
        self._chip_tree.setColumnWidth(0, 80)
        self._chip_tree.setColumnWidth(1, 110)
        self._chip_tree.setColumnWidth(2, 60)
        self._chip_tree.setColumnWidth(3, 45)

        self._chip_items = []
        for chip in all_chips():
            compat = "✓" if chip.kaeru_compat else "✗"
            item = QTreeWidgetItem([
                chip.name, chip.marketing, chip.arch, compat
            ])
            item.setForeground(3, QColor("#00c890" if chip.kaeru_compat else "#ff5555"))
            if chip.v6_protocol:
                item.setForeground(0, QColor("#ffaa00"))
            self._chip_tree.addTopLevelItem(item)
            self._chip_items.append((chip, item))

        layout.addWidget(self._chip_tree, 1)

        legend = QLabel(
            "<span style='color:#00c890'>✓ kaeru compatible</span>  "
            "<span style='color:#ff5555'>✗ not compatible</span>  "
            "<span style='color:#ffaa00'>■ V6 auth required</span>"
        )
        legend.setTextFormat(Qt.RichText)
        legend.setStyleSheet("font-size:10px; padding:2px;")
        layout.addWidget(legend)
        return page

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _add_separator(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#1a2535; margin:2px 0;")
        layout.addWidget(line)

    def _switch_editor(self, name: str):
        for n, w in self._editor_pages.items():
            w.setVisible(n == name)
        for n, btn in self._editor_btns.items():
            btn.setChecked(n == name)

    def _current_code(self) -> str:
        if self._editor_btns.get("board.c", None) and self._editor_btns["board.c"].isChecked():
            return self._board_editor.toPlainText()
        return self._defconfig_editor.toPlainText()

    def _copy_editor_content(self):
        QApplication.clipboard().setText(self._current_code())
        self.left_status.setText("Copied to clipboard.")

    def _save_editor_content(self):
        if self._editor_btns.get("board.c", None) and self._editor_btns["board.c"].isChecked():
            fname = f"board-{self._codename}.c"
            filt  = "C files (*.c);;All (*)"
        else:
            fname = f"{self._codename}_defconfig"
            filt  = "Defconfig (*);;All (*)"
        path, _ = QFileDialog.getSaveFileName(self, "Save File", fname, filt)
        if path:
            with open(path, "w") as f:
                f.write(self._current_code())
            self.left_status.setText(f"Saved: {os.path.basename(path)}")

    # ── Device Info ───────────────────────────────────────────────────────────
    def update_device(self, hw_code: int):
        """Called by MainWindow when device state changes."""
        self._current_hw = hw_code
        chip = lookup(hw_code)
        if chip:
            self._soc_name = chip.name
            self.edit_soc.setText(chip.name)
            self._dev_labels["SoC"].setText(chip.display_name)
            self._dev_labels["HW Code"].setText(f"0x{hw_code:04X}")
            self._dev_labels["Arch"].setText(chip.arch)
            self._dev_labels["V6 Auth"].setText("YES" if chip.v6_protocol else "NO")
            v6_color = "#ffaa00" if chip.v6_protocol else "#00c890"
            self._dev_labels["V6 Auth"].setStyleSheet(
                f"color:{v6_color}; font-size:11px; font-weight:bold;"
            )
        self._update_payload_status()
        self._check_eligibility_silent()

    def _refresh_device_info(self):
        if not self._adb.available:
            self.left_status.setText("ADB not available.")
            return
        devs = self._adb.get_devices()
        if not devs:
            self.left_status.setText("No ADB device connected.")
            return
        serial = devs[0].get("serial", "")
        info   = self._adb.get_full_info(serial)
        codename = info.get("Codename", "") or self._codename
        vendor   = info.get("Brand", "")    or self._vendor
        model    = info.get("Model", "")    or self._model
        soc      = info.get("Chipset", "")  or self._soc_name

        self._codename, self._vendor, self._model = codename, vendor, model
        self.edit_codename.setText(codename)
        self.edit_vendor.setText(vendor)
        self.edit_model.setText(model)
        if soc:
            self.edit_soc.setText(soc)

        self._dev_labels["Codename"].setText(codename)
        self._dev_labels["Vendor"].setText(vendor)
        self._dev_labels["Model"].setText(model)
        self.left_status.setText(f"ADB info updated: {model}")
        self._regenerate_board_file()
        self._regenerate_defconfig()

    def _check_eligibility(self):
        self._check_eligibility_silent()

    def _check_eligibility_silent(self):
        hw = self._current_hw
        if hw == 0:
            self.elig_lbl.setText("Connect device in BROM/Preloader mode first.")
            self.elig_lbl.setStyleSheet("color:#607080; font-size:11px;")
            self.elig_detail.setText("")
            return

        chip = lookup(hw)
        compat = chip.kaeru_compat if chip else (hw < 0x6853)

        if compat:
            self.elig_lbl.setText(
                f"✓  {chip.name if chip else 'This chip'} is potentially compatible."
            )
            self.elig_lbl.setStyleSheet("color:#00c890; font-size:11px; font-weight:bold;")
            self.elig_detail.setText(
                "The chip uses an ARMv7 LK bootloader which kaeru supports.\n"
                "You must still verify the security policy allows unsigned LK.\n"
                "See: kaeru wiki → Can I use kaeru on my device?"
            )
        elif chip and chip.v6_protocol:
            self.elig_lbl.setText(
                f"⚠  {chip.name}: V6 auth required — limited support."
            )
            self.elig_lbl.setStyleSheet("color:#ffaa00; font-size:11px; font-weight:bold;")
            self.elig_detail.setText(
                "This chip uses V6 BROM authentication (SLA/DAA).\n"
                "Kaeru requires a patched BROM or loader bypass for V6 chips.\n"
                "Check the kaeru GitHub for V6 loader compatibility."
            )
        else:
            self.elig_lbl.setText(f"✗  {chip.name if chip else 'This chip'}: not compatible.")
            self.elig_lbl.setStyleSheet("color:#ff5555; font-size:11px; font-weight:bold;")
            self.elig_detail.setText(
                "This SoC uses AArch64 LK which is not yet supported by kaeru.\n"
                "Kaeru is ARMv7-only. Check the GitHub for updates."
            )

    # ── LK Extraction ─────────────────────────────────────────────────────────
    def _pull_lk_adb(self):
        if not self._adb.available:
            self._warn("ADB not available. Connect device via USB.")
            return
        devs = self._adb.get_devices()
        if not devs:
            self._warn("No ADB device connected.")
            return
        serial = devs[0].get("serial", "")

        path, _ = QFileDialog.getSaveFileName(
            self, "Save LK image", "lk.bin", "Binary (*.bin *.img);;All (*)"
        )
        if not path:
            return

        self.left_status.setText("Pulling LK partition via ADB…")
        ok = self._adb.pull_file("/dev/block/by-name/lk", path, serial)
        if not ok:
            ok = self._adb.pull_file("/dev/block/bootdevice/by-name/lk", path, serial)
        if ok:
            self._lk_path = path
            self.lk_path_lbl.setText(f"✓ {os.path.basename(path)}")
            self.lk_path_lbl.setStyleSheet("color:#00c890; font-size:10px;")
            self._log_build(f"✓ LK pulled → {path}")
            self._auto_detect_lk_size(path)
        else:
            self._warn("Could not pull LK. Root access may be required.")
            self.left_status.setText("LK pull failed.")

    def _open_lk_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LK image", "", "Binary (*.bin *.img);;All (*)"
        )
        if path:
            self._lk_path = path
            self.lk_path_lbl.setText(f"✓ {os.path.basename(path)}")
            self.lk_path_lbl.setStyleSheet("color:#00c890; font-size:10px;")
            self.left_status.setText(f"LK loaded: {os.path.basename(path)}")
            self._auto_detect_lk_size(path)

    def _auto_detect_lk_size(self, path: str):
        try:
            size = os.path.getsize(path)
            self._log_build(f"LK size: 0x{size:08X} ({size:,} bytes)")
            # Auto-update defconfig with real size
            self._regenerate_defconfig(lk_size=size)
        except Exception:
            pass

    # ── Scatter Generator ──────────────────────────────────────────────────────
    def _generate_scatter(self):
        codename = self.edit_codename.text().strip() or "device"
        self.left_status.setText("Generating scatter file…")
        self._log_build("Generating scatter file from device partition table…")

        def do_gen():
            devs = self._adb.get_devices() if self._adb.available else []
            serial = devs[0].get("serial", "") if devs else ""
            text, method = self._scatter_gen.generate_from_device(serial, codename)
            return text, method

        def on_done(ok, msg):
            self.build_progress.hide()
            if ok:
                pass  # handled in on_scatter_done

        # Run in thread-safe manner (blocking for now since ADB is fast)
        try:
            devs = self._adb.get_devices() if self._adb.available else []
            serial = devs[0].get("serial", "") if devs else ""
            text, method = self._scatter_gen.generate_from_device(serial, codename)
            if text:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save Scatter File",
                    f"MT65XX_Android_scatter_{codename}.txt",
                    "Text files (*.txt);;All (*)"
                )
                if path:
                    ok = ScatterGenerator.save(text, path)
                    if ok:
                        self.left_status.setText(f"Scatter saved: {os.path.basename(path)}")
                        self._log_build(f"✓ Scatter generated via {method}")
                        self._log_build(f"  Saved: {path}")
                    else:
                        self.left_status.setText("Failed to save scatter.")
            else:
                self._log_build(f"✗ Scatter generation failed: {method}")
                self.left_status.setText("Could not read partition table from device.")
                QMessageBox.information(self, "Scatter Generation",
                    "Could not auto-generate scatter file.\n\n"
                    "Possible reasons:\n"
                    "• No device connected in ADB mode\n"
                    "• Insufficient permissions (root required for some methods)\n"
                    "• Device uses UFS without standard GPT layout\n\n"
                    "Alternative: Load a scatter file manually in the Flash tab,\n"
                    "or obtain the scatter file from your firmware package.")
        except Exception as e:
            self.left_status.setText(f"Scatter error: {e}")
            self._log_build(f"✗ Scatter error: {e}")

    # ── Payload Manager ───────────────────────────────────────────────────────
    def _update_payload_status(self):
        hw = self._current_hw
        if hw == 0:
            self.payload_status.setText("No device detected.")
            return
        status = self._payload_mgr.status_for(hw)
        if status["is_cached"]:
            self.payload_status.setText(
                f"✓ Cached: {os.path.basename(status['cache_path'])}"
            )
            self.payload_status.setStyleSheet("color:#00c890; font-size:10px;")
        elif status["has_url"]:
            self.payload_status.setText(
                f"Available to download for {status['chip_name']}"
            )
            self.payload_status.setStyleSheet("color:#ffaa00; font-size:10px;")
        else:
            self.payload_status.setText(
                f"No payload available for {status['chip_name']}\n"
                f"You may need to provide one manually."
            )
            self.payload_status.setStyleSheet("color:#805040; font-size:10px;")

    def _download_payload(self):
        hw = self._current_hw
        if hw == 0:
            self._warn("No device detected. Connect a device first.")
            return
        chip = lookup(hw)
        if not get_payload_url(hw):
            self._warn(
                f"No payload URL available for {chip.name if chip else 'this chip'}.\n"
                "You can import a payload manually using the '+ Import' button."
            )
            return

        self.payload_progress.show()
        self.payload_progress.setRange(0, 0)
        self.left_status.setText("Downloading payload…")

        def on_progress(cur, total):
            if total > 0:
                self.payload_progress.setRange(0, total)
                self.payload_progress.setValue(cur)

        def on_done(ok, msg):
            self.payload_progress.hide()
            self._update_payload_status()
            if ok:
                self.left_status.setText(f"Payload downloaded: {os.path.basename(msg)}")
                self._log_build(f"✓ Payload: {msg}")
            else:
                self.left_status.setText(f"Payload download failed: {msg}")
                self._log_build(f"✗ Payload error: {msg}")

        self._payload_mgr.download_async(hw, on_progress, on_done)

    def _import_payload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Payload .bin", "", "Binary (*.bin);;All (*)"
        )
        if not path:
            return
        hw = self._current_hw
        if hw == 0:
            self._warn("No device detected. HW code needed to index payload.")
            return
        ok = self._payload_mgr.import_local(hw, path)
        if ok:
            self._update_payload_status()
            self.left_status.setText("Payload imported.")
            self._log_build(f"✓ Payload imported: {path}")
        else:
            self.left_status.setText("Payload import failed.")

    # ── Code Generation ───────────────────────────────────────────────────────
    def _collect_cfg(self) -> dict:
        soc      = self.edit_soc.text().strip() or "Unknown"
        codename = self.edit_codename.text().strip() or "device"
        vendor   = self.edit_vendor.text().strip() or "Unknown"
        model    = self.edit_model.text().strip() or "Unknown Device"
        chip     = lookup_by_name(soc)
        hw       = chip.hw_code if chip else self._current_hw
        lk_base  = chip.lk_base if chip else 0x48000000
        return dict(soc=soc, codename=codename, vendor=vendor,
                    model=model, chip=chip, hw=hw, lk_base=lk_base)

    def _regenerate_board_file(self):
        cfg = self._collect_cfg()
        text = BOARD_TEMPLATE.format(
            model    = cfg["model"],
            codename = cfg["codename"],
            soc      = cfg["soc"],
            lk_base  = cfg["lk_base"],
            vendor   = cfg["vendor"],
        )
        self._board_editor.setPlainText(text)

    def _regenerate_defconfig(self, lk_size: int = 0):
        cfg = self._collect_cfg()
        hw  = cfg["hw"]

        template = KAERU_DEFCONFIG_TEMPLATES.get(hw, KAERU_DEFAULT_DEFCONFIG)
        text = DEFCONFIG_TEMPLATE.format(
            model        = cfg["model"],
            codename     = cfg["codename"],
            vendor       = cfg["vendor"],
            soc          = cfg["soc"],
            lk_base      = template["BOOTLOADER_BASE"],
            lk_size      = lk_size or template["BOOTLOADER_SIZE"],
            app_addr     = template["APP_ADDRESS"],
            fastboot_cont= template["FASTBOOT_CONTINUE"],
            bootmode_addr= template["BOOTMODE_ADDRESS"],
        )
        self._defconfig_editor.setPlainText(text)

    def _export_to_kaeru(self):
        kaeru_dir = self.kaeru_dir_edit.text().strip()
        if not kaeru_dir or not os.path.isdir(kaeru_dir):
            kaeru_dir = QFileDialog.getExistingDirectory(
                self, "Select kaeru repository directory"
            )
        if not kaeru_dir:
            return

        cfg = self._collect_cfg()
        codename = cfg["codename"]
        vendor   = cfg["vendor"].lower().replace(" ", "_")
        soc      = cfg["soc"].lower()

        # board file
        board_dir = os.path.join(kaeru_dir, "board", vendor)
        os.makedirs(board_dir, exist_ok=True)
        board_path = os.path.join(board_dir, f"board-{codename}.c")
        with open(board_path, "w") as f:
            f.write(self._board_editor.toPlainText())

        # defconfig
        cfg_dir = os.path.join(kaeru_dir, "configs")
        os.makedirs(cfg_dir, exist_ok=True)
        def_path = os.path.join(cfg_dir, f"{codename}_defconfig")
        with open(def_path, "w") as f:
            f.write(self._defconfig_editor.toPlainText())

        self._log_build(f"✓ Exported board file: {board_path}")
        self._log_build(f"✓ Exported defconfig:  {def_path}")
        self._log_build("")
        self._log_build("Next steps:")
        self._log_build(f"  cd {kaeru_dir}")
        self._log_build(f"  make {codename}_defconfig")
        self._log_build(f"  make -j$(nproc)")
        self.left_status.setText("Exported to kaeru directory.")

        QMessageBox.information(self, "Export Complete",
            f"Files exported to kaeru directory:\n\n"
            f"board/{vendor}/board-{codename}.c\n"
            f"configs/{codename}_defconfig\n\n"
            f"Next steps:\n"
            f"1. Review and adjust offsets in both files with Ghidra\n"
            f"2. Run: make {codename}_defconfig\n"
            f"3. Run: make -j$(nproc)\n"
            f"4. Flash the output with MTK Client 2.0"
        )

    # ── Template Browser ──────────────────────────────────────────────────────
    def _on_template_selected(self, current, _previous):
        if not current:
            return
        name = current.text(0)
        code = KAERU_TEMPLATES.get(name, "")
        self._tmpl_preview.setPlainText(code)

    def _append_template_to_board(self):
        current = self._tmpl_tree.currentItem()
        if not current:
            return
        name = current.text(0)
        code = KAERU_TEMPLATES.get(name, "")
        if code:
            existing = self._board_editor.toPlainText()
            # Insert template comment + code before closing brace of board_late_init
            insertion = f"\n/* === Template: {name} === */\n{code}"
            self._board_editor.setPlainText(existing + "\n" + insertion)
            self._switch_editor("board.c")
            self.left_status.setText(f"Appended template: {name}")

    # ── Build ──────────────────────────────────────────────────────────────────
    def _browse_kaeru_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select kaeru directory")
        if d:
            self.kaeru_dir_edit.setText(d)

    def _run_kaeru_setup(self):
        kaeru_dir = self.kaeru_dir_edit.text().strip()
        if not kaeru_dir or not os.path.isdir(kaeru_dir):
            self._warn("Select the kaeru repository directory first.")
            return
        setup_sh = os.path.join(kaeru_dir, "setup.sh")
        if not os.path.exists(setup_sh):
            self._warn(f"setup.sh not found in {kaeru_dir}")
            return

        cfg = self._collect_cfg()
        cmd = [
            "bash", setup_sh,
            "-c", cfg["codename"],
            "-m", cfg["model"],
            "-v", cfg["vendor"],
            "-s", cfg["soc"],
        ]
        if self._lk_path and os.path.exists(self._lk_path):
            cmd += ["-l", self._lk_path]

        self._log_build(f"$ {' '.join(cmd)}")
        self._run_cmd(cmd, cwd=kaeru_dir)

    def _run_kaeru_build(self):
        kaeru_dir = self.kaeru_dir_edit.text().strip()
        if not kaeru_dir or not os.path.isdir(kaeru_dir):
            self._warn("Select the kaeru repository directory first.")
            return

        cfg = self._collect_cfg()
        method = self.build_method.currentIndex()

        if method == 0:  # Docker
            cmd = ["docker", "run", "--rm",
                   "-v", f"{kaeru_dir}:/kaeru",
                   "kaeru:latest",
                   "bash", "-c",
                   f"cd /kaeru && make {cfg['codename']}_defconfig && make -j$(nproc)"]
        else:  # Native
            cmd = ["bash", "-c",
                   f"cd {kaeru_dir} && make {cfg['codename']}_defconfig && make -j$(nproc)"]

        self._log_build(f"Building kaeru for {cfg['codename']}…")
        self.build_progress.show()
        self.build_progress.setRange(0, 0)
        self._run_cmd(cmd, cwd=kaeru_dir)

    def _run_cmd(self, cmd: list, cwd: str = None):
        def do_run():
            try:
                proc = subprocess.Popen(
                    cmd, cwd=cwd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True
                )
                for line in proc.stdout:
                    self._log_build(line.rstrip())
                proc.wait()
                return proc.returncode == 0
            except FileNotFoundError as e:
                self._log_build(f"✗ Command not found: {e}")
                return False
            except Exception as e:
                self._log_build(f"✗ Error: {e}")
                return False

        self._worker = KaeruWorker(do_run)
        self._worker.finished.connect(self._on_build_done)
        self._worker.start()

    def _on_build_done(self, ok: bool, msg: str):
        self.build_progress.hide()
        status = "✓ Build succeeded!" if ok else "✗ Build failed — check log."
        self._log_build(status)
        self.left_status.setText(status)

    def _flash_patched_lk(self):
        kaeru_dir = self.kaeru_dir_edit.text().strip()
        if kaeru_dir:
            # Try common output locations
            candidates = [
                os.path.join(kaeru_dir, "out", "lk.bin"),
                os.path.join(kaeru_dir, "lk.bin"),
                os.path.join(kaeru_dir, "out", "lk_patched.bin"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    self._flash_lk_image(c)
                    return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select patched LK image", "", "Binary (*.bin *.img);;All (*)"
        )
        if path:
            self._flash_lk_image(path)

    def _flash_lk_image(self, path: str):
        if QMessageBox.question(
            self, "Flash Patched LK",
            f"Flash kaeru-patched LK to device?\n\nFile: {path}\n\n"
            "⚠ Device must be in BROM/Preloader mode.\n"
            "⚠ A bad flash can brick the device.",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        from core.partition_manager import Partition
        from core import OpType
        part = Partition()
        part.name = "lk"
        part.physical_start = 0x0
        part.size = os.path.getsize(path)
        part.file_name = path
        self._log_build(f"Flashing patched LK: {path}")
        self._engine.run(OpType.FLASH_SINGLE, {"partition": part, "file_path": path})

    # ── Chip Browser ─────────────────────────────────────────────────────────
    def _filter_chip_browser(self, text: str):
        text = text.lower()
        for chip, item in self._chip_items:
            match = (text in chip.name.lower() or
                     text in chip.marketing.lower() or
                     text in chip.series.lower())
            item.setHidden(not match)

    # ── Utilities ─────────────────────────────────────────────────────────────
    def _log_build(self, msg: str):
        self.build_log.append(msg)

    def _warn(self, msg: str):
        QMessageBox.warning(self, "Kaeru Workshop", msg)

    def _set_dev_label(self, key: str, value: str,
                       color: str = "#8090a8"):
        lbl = self._dev_labels.get(key)
        if lbl:
            lbl.setText(value or "—")
            lbl.setStyleSheet(f"color:{color}; font-size:11px;")
