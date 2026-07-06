#!/usr/bin/env python3
"""
MTK Client 2.0 — MediaTek Flash & Repair Utility
Cross-platform: Windows/Linux/macOS

Features:
- Advanced USB detection with multiple fallback strategies
- BROM/Preloader/DA protocol support
- ADB integration
- Kaeru payload development workshop
- Device history tracking
"""
import sys
import os
import platform
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up application metadata before Qt imports
from PyQt5.QtCore import QCoreApplication
QCoreApplication.setApplicationName("MTK Client 2.0")
QCoreApplication.setOrganizationName("MTKClient")
QCoreApplication.setApplicationVersion("2.1.0")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontDatabase, QFont, QIcon

# Import from core
from ui.main_window import MainWindow
from utils.platform_setup import PlatformSetup
from utils.logger import get_logger

log = get_logger("main")


def main():
    """Application entry point."""
    # Hi-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Platform detection and setup
    setup = PlatformSetup()
    status = setup.ensure_prerequisites()
    
    # Log platform status
    for info in status.get("info", []):
        log.info(info)
    for warn in status.get("warnings", []):
        log.warning(warn)
    for issue in status.get("issues", []):
        log.error(issue)
    
    # Load stylesheet
    style_path = os.path.join(os.path.dirname(__file__), "ui", "styles", "dark_theme.qss")
    style = ""
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            style = f.read()
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if style:
        app.setStyleSheet(style)
    
    window = MainWindow()
    window.show()
    
    log.info(f"MTK Client 2.1 - Starting interface...")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()