"""
Device Info Tab — displays MTK + ADB hardware/software info.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QHeaderView, QSplitter, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont


class DeviceInfoTab(QWidget):
    def __init__(self, protocol, adb, parent=None):
        super().__init__(parent)
        self._proto = protocol
        self._adb   = adb
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Top bar ──────────────────────────────────────────────────────────
        top = QHBoxLayout()
        btn_refresh = QPushButton("⟳  Refresh Info")
        btn_refresh.setToolTip("Re-read device info from connected device")
        btn_refresh.clicked.connect(self.refresh)

        btn_refresh_adb = QPushButton("ADB Info")
        btn_refresh_adb.setToolTip("Read device info via ADB")
        btn_refresh_adb.clicked.connect(self.refresh_adb)

        btn_export = QPushButton("Export Report")
        btn_export.clicked.connect(self._export_report)

        self.lbl_device = QLabel("No device connected")
        self.lbl_device.setObjectName("lbl_disconnected")

        top.addWidget(self.lbl_device)
        top.addStretch()
        top.addWidget(btn_refresh_adb)
        top.addWidget(btn_refresh)
        top.addWidget(btn_export)
        layout.addLayout(top)

        # ── Split: MTK info + ADB info ────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # MTK BROM info table
        mtk_box = QGroupBox("MediaTek Hardware Info")
        mtk_layout = QVBoxLayout(mtk_box)
        self.mtk_table = self._make_table(["Property", "Value"])
        mtk_layout.addWidget(self.mtk_table)
        splitter.addWidget(mtk_box)

        # ADB info table
        adb_box = QGroupBox("Android / ADB Info")
        adb_layout = QVBoxLayout(adb_box)
        self.adb_table = self._make_table(["Property", "Value"])
        adb_layout.addWidget(self.adb_table)
        splitter.addWidget(adb_box)

        splitter.setSizes([400, 400])
        layout.addWidget(splitter, 1)

        # ── Chipset info panel ────────────────────────────────────────────────
        chip_box = QGroupBox("Chipset Features")
        chip_layout = QHBoxLayout(chip_box)
        self.chip_info = QTextEdit()
        self.chip_info.setReadOnly(True)
        self.chip_info.setMaximumHeight(100)
        chip_layout.addWidget(self.chip_info)
        layout.addWidget(chip_box)

        self._populate_defaults()

    def _make_table(self, headers):
        t = QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setAlternatingRowColors(True)
        return t

    def _populate_defaults(self):
        placeholder = [
            ("Status", "Waiting for device…"),
            ("Mode", "—"),
            ("Chipset", "—"),
            ("HW Code", "—"),
            ("Protocol", "—"),
            ("Secure Boot", "—"),
            ("Auth", "—"),
            ("Storage", "—"),
        ]
        self._fill_table(self.mtk_table, placeholder)

    def _fill_table(self, table, data: list):
        table.setRowCount(len(data))
        for row, (k, v) in enumerate(data):
            ki = QTableWidgetItem(k)
            vi = QTableWidgetItem(str(v))
            ki.setForeground(QColor("#607090"))
            vi.setForeground(QColor("#a0c8e0"))
            table.setItem(row, 0, ki)
            table.setItem(row, 1, vi)

    def refresh(self):
        """Populate MTK info from connected protocol."""
        info = self._proto.read_device_info()
        data = list(info.to_dict().items())
        self._fill_table(self.mtk_table, data)

        name = info.chipset_name
        if name != "Unknown":
            self.lbl_device.setText(f"⬤  {name}")
            self.lbl_device.setObjectName("lbl_connected")
        else:
            self.lbl_device.setText("⬤  Device Connected")
            self.lbl_device.setObjectName("lbl_connected")

        # Chip feature hints
        features = self._get_chip_features(info.hw_code)
        self.chip_info.setText(features)

    def refresh_adb(self):
        """Populate ADB info."""
        if not self._adb.available:
            self._fill_table(self.adb_table, [("Error", "ADB not available")])
            return
        devs = self._adb.get_devices()
        if not devs:
            self._fill_table(self.adb_table, [("Status", "No ADB device found")])
            return
        serial = devs[0].get("serial", "")
        info   = self._adb.get_full_info(serial)
        data   = list(info.items())
        self._fill_table(self.adb_table, data)

    def _get_chip_features(self, hw_code: int) -> str:
        lines = []
        if hw_code >= 0x6853:
            lines.append("• Dimensity series — V6 protocol required")
            lines.append("• Secure boot likely enabled — loader required for BROM")
            lines.append("• UFS 2.x storage likely")
        elif hw_code >= 0x6761:
            lines.append("• Helio G/P series — Legacy BROM protocol")
            lines.append("• eMMC 5.1 storage typical")
        else:
            lines.append("• Legacy SOC — kamakiri/amonet exploit may apply")
            lines.append("• eMMC storage")
        return "\n".join(lines) if lines else "No feature data available."

    def _export_report(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", "device_report.txt", "Text Files (*.txt)"
        )
        if not path:
            return

        def safe_row(table, r):
            k = table.item(r, 0)
            v = table.item(r, 1)
            return (k.text() if k else ""), (v.text() if v else "")

        with open(path, "w") as f:
            f.write("=== MTK Client 2.0 — Device Report ===\n\n")
            f.write("[ MediaTek Hardware Info ]\n")
            for r in range(self.mtk_table.rowCount()):
                k, v = safe_row(self.mtk_table, r)
                f.write(f"  {k:<22}: {v}\n")
            f.write("\n[ Android / ADB Info ]\n")
            for r in range(self.adb_table.rowCount()):
                k, v = safe_row(self.adb_table, r)
                f.write(f"  {k:<22}: {v}\n")
