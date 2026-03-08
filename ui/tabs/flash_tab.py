"""
Flash Tab — scatter file loading and firmware flash/backup operations.
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox,
    QProgressBar, QComboBox, QLineEdit, QAbstractItemView,
    QMessageBox, QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from core import ScatterParser, Partition, FlashEngine, OpType


class FlashTab(QWidget):
    def __init__(self, engine: FlashEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._parser = ScatterParser()
        self._build_ui()
        self._connect_engine()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Scatter File Loader ───────────────────────────────────────────────
        scatter_box = QGroupBox("Scatter / Firmware File")
        scatter_layout = QHBoxLayout(scatter_box)
        self.scatter_path = QLineEdit()
        self.scatter_path.setPlaceholderText("Load scatter file (MT__xx_Android_scatter.txt)…")
        self.scatter_path.setReadOnly(True)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_scatter)
        btn_auto_resolve = QPushButton("Auto-Resolve Paths")
        btn_auto_resolve.setToolTip("Resolve partition file paths relative to scatter directory")
        btn_auto_resolve.clicked.connect(self._auto_resolve)
        scatter_layout.addWidget(self.scatter_path, 1)
        scatter_layout.addWidget(btn_browse)
        scatter_layout.addWidget(btn_auto_resolve)
        layout.addWidget(scatter_box)

        # ── Scatter Summary ───────────────────────────────────────────────────
        self.summary_lbl = QLabel("No scatter loaded.")
        self.summary_lbl.setStyleSheet("color:#506070; font-size:11px; padding:2px 6px;")
        layout.addWidget(self.summary_lbl)

        # ── Partition Table ───────────────────────────────────────────────────
        parts_box  = QGroupBox("Partitions")
        parts_layout = QVBoxLayout(parts_box)

        # toolbar
        toolbar = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(lambda: self._select_all(True))
        btn_deselect   = QPushButton("Deselect All")
        btn_deselect.clicked.connect(lambda: self._select_all(False))
        btn_sel_fw     = QPushButton("Firmware Only")
        btn_sel_fw.setToolTip("Select only essential firmware partitions")
        btn_sel_fw.clicked.connect(self._select_firmware_only)
        btn_browse_part = QPushButton("Browse File for Selected")
        btn_browse_part.clicked.connect(self._browse_for_selected)
        toolbar.addWidget(btn_select_all)
        toolbar.addWidget(btn_deselect)
        toolbar.addWidget(btn_sel_fw)
        toolbar.addStretch()
        toolbar.addWidget(btn_browse_part)
        parts_layout.addLayout(toolbar)

        self.part_table = QTableWidget()
        self.part_table.setColumnCount(6)
        self.part_table.setHorizontalHeaderLabels([
            "✓", "Partition", "Start Addr", "Size", "File", "Status"
        ])
        hdr = self.part_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.part_table.setColumnWidth(0, 28)
        self.part_table.verticalHeader().setVisible(False)
        self.part_table.setAlternatingRowColors(True)
        self.part_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        parts_layout.addWidget(self.part_table)
        layout.addWidget(parts_box, 1)

        # ── Flash Mode + Actions ──────────────────────────────────────────────
        action_box  = QGroupBox("Flash Options")
        action_layout = QHBoxLayout(action_box)

        mode_lbl = QLabel("Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Download Only",
            "Firmware Upgrade",
            "Format + Download",
            "Format All + Download",
        ])
        self.mode_combo.setToolTip(
            "Download Only: flash selected partitions\n"
            "Firmware Upgrade: skip format, only flash\n"
            "Format + Download: format then flash\n"
            "Format All + Download: wipe everything then flash"
        )

        self.btn_flash = QPushButton("⚡  FLASH")
        self.btn_flash.setObjectName("btn_flash")
        self.btn_flash.setMinimumWidth(130)
        self.btn_flash.clicked.connect(self._do_flash)

        btn_backup = QPushButton("⬇  Backup All")
        btn_backup.setToolTip("Backup all partitions to a folder")
        btn_backup.clicked.connect(self._do_backup_all)

        btn_backup_single = QPushButton("⬇  Backup Selected")
        btn_backup_single.clicked.connect(self._do_backup_selected)

        btn_abort = QPushButton("✕  Abort")
        btn_abort.setObjectName("btn_danger")
        btn_abort.clicked.connect(self._engine.abort)

        action_layout.addWidget(mode_lbl)
        action_layout.addWidget(self.mode_combo)
        action_layout.addStretch()
        action_layout.addWidget(btn_backup_single)
        action_layout.addWidget(btn_backup)
        action_layout.addWidget(btn_abort)
        action_layout.addWidget(self.btn_flash)
        layout.addWidget(action_box)

        # ── Progress ──────────────────────────────────────────────────────────
        prog_box    = QGroupBox("Progress")
        prog_layout = QVBoxLayout(prog_box)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%v / %m bytes — %p%")
        self.status_lbl   = QLabel("Ready.")
        self.status_lbl.setObjectName("lbl_status")
        prog_layout.addWidget(self.status_lbl)
        prog_layout.addWidget(self.progress_bar)
        layout.addWidget(prog_box)

    # ── Engine Connections ────────────────────────────────────────────────────
    def _connect_engine(self):
        self._engine.progress_updated.connect(self._on_progress)
        self._engine.status_updated.connect(self.status_lbl.setText)
        self._engine.operation_finished.connect(self._on_finished)

    def _on_progress(self, cur: int, total: int, label: str):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(cur)
        self.status_lbl.setText(label)

    # ── Scatter Loading ───────────────────────────────────────────────────────
    def _browse_scatter(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Scatter File", "",
            "Scatter Files (*.txt *.cfg);;All Files (*)"
        )
        if path:
            self._load_scatter(path)

    def _load_scatter(self, path: str):
        ok = self._parser.load(path)
        if ok:
            self.scatter_path.setText(path)
            self.summary_lbl.setText(self._parser.summary.replace("\n", "  |  "))
            self._parser.resolve_file_paths(os.path.dirname(path))
            self._populate_table()
        else:
            QMessageBox.warning(self, "Parse Error", f"Failed to parse scatter file:\n{path}")

    def _auto_resolve(self):
        if not self._parser.source_file:
            return
        base = os.path.dirname(self._parser.source_file)
        self._parser.resolve_file_paths(base)
        self._populate_table()

    # ── Table Population ──────────────────────────────────────────────────────
    def _populate_table(self):
        parts = self._parser.partitions
        self.part_table.setRowCount(len(parts))
        for row, p in enumerate(parts):
            # Checkbox column
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if p.is_download else Qt.Unchecked)
            self.part_table.setItem(row, 0, chk)
            # Name
            name_item = QTableWidgetItem(p.name)
            name_item.setForeground(QColor("#a0c8e0"))
            self.part_table.setItem(row, 1, name_item)
            # Start
            self.part_table.setItem(row, 2, QTableWidgetItem(p.start_hex))
            # Size
            self.part_table.setItem(row, 3, QTableWidgetItem(p.size_human))
            # File
            file_item = QTableWidgetItem(os.path.basename(p.file_name) if p.file_name else "—")
            file_item.setForeground(
                QColor("#00c84a") if p.has_file else QColor("#604040")
            )
            self.part_table.setItem(row, 4, file_item)
            # Status
            if p.has_file:
                status = "Ready"
                color  = "#008844"
            elif p.file_name:
                status = "File Missing"
                color  = "#886600"
            else:
                status = "No File"
                color  = "#304040"
            st = QTableWidgetItem(status)
            st.setForeground(QColor(color))
            self.part_table.setItem(row, 5, st)

    def _select_all(self, checked: bool):
        for row in range(self.part_table.rowCount()):
            chk = self.part_table.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _select_firmware_only(self):
        fw_parts = {"preloader", "lk", "lk2", "boot", "recovery", "system",
                    "vendor", "dtbo", "vbmeta", "logo", "tee1", "tee2",
                    "gz1", "gz2", "sspm_1", "sspm_2"}
        for row in range(self.part_table.rowCount()):
            chk  = self.part_table.item(row, 0)
            name = self.part_table.item(row, 1)
            if chk and name:
                is_fw = any(name.text().lower().startswith(p) for p in fw_parts)
                chk.setCheckState(Qt.Checked if is_fw else Qt.Unchecked)

    def _browse_for_selected(self):
        rows = self.part_table.selectedItems()
        if not rows:
            return
        row = self.part_table.currentRow()
        part = self._parser.partitions[row]
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select file for {part.name}", "", "Binary Files (*.bin *.img *.ext4);;All Files (*)"
        )
        if path:
            part.file_name = path
            self._populate_table()

    # ── Sync table checkboxes → parser ───────────────────────────────────────
    def _sync_selection(self):
        for row in range(self.part_table.rowCount()):
            chk = self.part_table.item(row, 0)
            if chk and row < len(self._parser.partitions):
                self._parser.partitions[row].is_selected = (
                    chk.checkState() == Qt.Checked
                )

    # ── Operations ────────────────────────────────────────────────────────────
    def _do_flash(self):
        self._sync_selection()
        mode = self.mode_combo.currentText()
        if QMessageBox.question(
            self, "Confirm Flash",
            f"Mode: {mode}\n\nThis will write to device flash memory.\nProceed?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._engine.run(OpType.FLASH_SCATTER, {"parser": self._parser})

    def _do_backup_all(self):
        out = QFileDialog.getExistingDirectory(self, "Select Backup Folder")
        if out:
            self._engine.run(OpType.BACKUP_ALL, {"parser": self._parser, "out_dir": out})

    def _do_backup_selected(self):
        row = self.part_table.currentRow()
        if row < 0 or row >= len(self._parser.partitions):
            QMessageBox.warning(self, "Select Partition", "Please select a partition first.")
            return
        part = self._parser.partitions[row]
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save {part.name}", f"{part.name}.bin", "Binary (*.bin);;All (*)"
        )
        if path:
            self._engine.run(OpType.BACKUP_SINGLE, {"partition": part, "out_path": path})

    # ── Progress/Finish ───────────────────────────────────────────────────────
    def _on_finished(self, ok: bool, msg: str):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.status_lbl.setText(msg)
        icon = QMessageBox.Information if ok else QMessageBox.Critical
        QMessageBox.information(self, "Complete" if ok else "Failed", msg)
