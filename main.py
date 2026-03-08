#!/usr/bin/env python3
"""
MTK Client 2.0 — MediaTek Flash & Repair Utility
Cross-platform: Fedora/Linux/Windows
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QFontDatabase, QFont, QIcon
from ui.main_window import MainWindow
from utils.platform_setup import PlatformSetup

def main():
    QCoreApplication.setApplicationName("MTK Client 2.0")
    QCoreApplication.setOrganizationName("MTKClient")
    QCoreApplication.setApplicationVersion("2.0.0")

    # Hi-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Platform setup (udev rules on Linux, drivers on Windows)
    setup = PlatformSetup()
    setup.ensure_prerequisites()

    # Load stylesheet
    style_path = os.path.join(os.path.dirname(__file__), "ui", "styles", "dark_theme.qss")
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
