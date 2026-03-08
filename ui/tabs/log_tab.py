"""
Log Tab — real-time color-coded log viewer with export and search.
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLineEdit, QLabel, QFileDialog,
    QCheckBox, QComboBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QTextCharFormat, QFont, QTextCursor

from utils import get_qt_handler

# Color map for log levels
LEVEL_COLORS = {
    "DEBUG":    "#354555",
    "INFO":     "#2a8060",
    "WARNING":  "#886600",
    "ERROR":    "#882020",
    "CRITICAL": "#cc0000",
}

LEVEL_TEXT_COLORS = {
    "DEBUG":    "#405565",
    "INFO":     "#00c890",
    "WARNING":  "#d4a020",
    "ERROR":    "#ff4444",
    "CRITICAL": "#ff0000",
}


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._build_ui()
        self._connect_logger()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.filter_combo.setMaximumWidth(100)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search logs…")
        self.search_box.setMaximumWidth(200)
        self.search_box.textChanged.connect(self._search)

        self.auto_scroll_chk = QCheckBox("Auto-scroll")
        self.auto_scroll_chk.setChecked(True)
        self.auto_scroll_chk.stateChanged.connect(
            lambda s: setattr(self, "_auto_scroll", s == Qt.Checked)
        )

        btn_clear  = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        btn_export = QPushButton("Export")
        btn_export.clicked.connect(self._export)
        btn_copy   = QPushButton("Copy All")
        btn_copy.clicked.connect(self._copy_all)

        toolbar.addWidget(QLabel("Level:"))
        toolbar.addWidget(self.filter_combo)
        toolbar.addWidget(self.search_box)
        toolbar.addStretch()
        toolbar.addWidget(self.auto_scroll_chk)
        toolbar.addWidget(btn_copy)
        toolbar.addWidget(btn_export)
        toolbar.addWidget(btn_clear)
        layout.addLayout(toolbar)

        # ── Log view ──────────────────────────────────────────────────────────
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("log_view")
        self.log_view.setMaximumBlockCount(5000)
        layout.addWidget(self.log_view)

        # ── Status ────────────────────────────────────────────────────────────
        self.count_lbl = QLabel("0 messages")
        self.count_lbl.setStyleSheet("color:#304050; font-size:11px;")
        layout.addWidget(self.count_lbl)

        self._message_count = 0

    def _connect_logger(self):
        handler = get_qt_handler()
        if handler:
            handler.log_emitted.connect(self.append_log)

    def append_log(self, level: str, message: str):
        # Filter by selected level
        filter_level = self.filter_combo.currentText()
        if filter_level != "All" and level != filter_level:
            return

        color = LEVEL_TEXT_COLORS.get(level, "#a0b8c8")

        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)

        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor(color))
        cursor.setCharFormat(char_fmt)
        cursor.insertText(message + "\n")

        self._message_count += 1
        self.count_lbl.setText(f"{self._message_count} messages")

        if self._auto_scroll:
            self.log_view.setTextCursor(cursor)
            self.log_view.ensureCursorVisible()

    def _search(self, text: str):
        if not text:
            return
        self.log_view.find(text)

    def _clear(self):
        self.log_view.clear()
        self._message_count = 0
        self.count_lbl.setText("0 messages")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", "mtkclient_log.txt", "Text (*.txt);;All (*)"
        )
        if path:
            with open(path, "w") as f:
                f.write(self.log_view.toPlainText())

    def _copy_all(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log_view.toPlainText())
