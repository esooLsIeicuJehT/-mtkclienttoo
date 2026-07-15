"""
Bypass Tab — FRP bypass methods for various devices
Dynamically loads all bypass profiles from core/bypass/
"""
import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QMessageBox,
    QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from core import FlashEngine, ADBBridge
from utils.logger import get_logger


BYPASS_UTILITY_FILES = {
    "__init__.py", "types.py", "bypass_manager.py",
    "adb_exploits.py", "hardware_exploits.py", "interface_exploits.py",
    "system_exploits.py", "device_manager.py", "adb_utils.py",
    "frp_bypass_wizard.py"
}

BYPASS_METHOD_PATTERNS = (
    "bypass", "bypass_", "exploit", "auto_bypass", "universal_bypass",
    "frp_reset", "pattern_bypass", "adb_bypass", "gatekeeper",
    "security_unlock", "oem_unlock", "talkback", "remove_",
    "disable_", "unlock_", "wipe", "reset", "connect", "disconnect",
    "run", "find_device", "cleanup", "connect_device", "patch", "upload",
    "build_", "extract_", "trigger_", "handshake", "dump", "read_", "write_"
)

CATEGORY_KEYWORDS = {
    "samsung": "Samsung",
    "google_pixel": "Google Pixel",
    "pixel": "Google Pixel",
    "huawei": "Huawei",
    "honor": "Huawei",
    "motorola": "Motorola",
    "qualcomm": "Qualcomm",
    "mediatek": "MediaTek",
    "mtk": "MediaTek",
    "generic": "Generic",
    "android": "Android",
    "mdm": "MDM",
    "miui": "Xiaomi MIUI",
    "xiaomi": "Xiaomi",
    "lockscreen": "Lockscreen",
    "imei": "IMEI/QCN",
    "qcn": "IMEI/QCN",
    "carbonara": "MediaTek",
    "heapbait": "MediaTek",
    "heapb8": "Qualcomm",
    "heap": "Heap Exploits",
    "auth_bypass": "Qualcomm",
    "edl": "Qualcomm",
    "brom": "MediaTek",
}


def _categorize(filename: str) -> str:
    base = filename.replace(".py", "").lower()
    for keyword, category in CATEGORY_KEYWORDS.items():
        if keyword in base:
            return category
    return "Other"


def _is_bypass_method(name: str) -> bool:
    if name.startswith("_") or name == "__init__":
        return False
    name_lower = name.lower()
    return any(
        name_lower.startswith(pattern) or name_lower == pattern
        for pattern in BYPASS_METHOD_PATTERNS
    )


def _find_main_class(module, module_name: str):
    skip_suffixes = ("Manager", "Method", "Result", "Commands")
    candidates = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if any(name.endswith(suffix) for suffix in skip_suffixes):
            continue
        if obj.__module__ != module_name:
            continue
        try:
            import enum
            if issubclass(obj, enum.Enum):
                continue
        except TypeError:
            pass
        method_count = sum(
            1 for _, member in inspect.getmembers(obj, inspect.isfunction)
            if _is_bypass_method(member.__name__)
        )
        total_methods = sum(
            1 for _, member in inspect.getmembers(obj, inspect.isfunction)
            if not member.__name__.startswith("_") and member.__name__ != "__init__"
        )
        candidates.append((method_count, total_methods, name, obj))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][3]


def _discover_profiles():
    bypass_dir = Path(__file__).resolve().parent.parent.parent / "core" / "bypass"
    profiles = []
    for py_file in sorted(bypass_dir.glob("*.py")):
        if py_file.name in BYPASS_UTILITY_FILES or py_file.name.startswith("_"):
            continue
        module_name = f"core.bypass.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, str(py_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            get_logger("bypass_tab").warning(
                f"Failed to import bypass module {module_name}: {e}"
            )
            continue

        main_class = _find_main_class(module, module_name)
        if not main_class:
            continue

        methods = []
        for method_name, member in inspect.getmembers(main_class, inspect.isfunction):
            if _is_bypass_method(method_name):
                methods.append(method_name)

        if not methods:
            continue

        profiles.append({
            "module_name": module_name,
            "class_name": main_class.__name__,
            "category": _categorize(py_file.name),
            "filename": py_file.name,
            "methods": sorted(set(methods)),
        })

    return profiles


class BypassTab(QWidget):
    def __init__(self, engine: FlashEngine, adb: ADBBridge, proto, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._adb = adb
        self._proto = proto
        self.logger = get_logger("bypass_tab")
        self._profiles = _discover_profiles()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        device_info_box = QGroupBox("Device Information")
        device_info_layout = QGridLayout(device_info_box)

        device_info_layout.addWidget(QLabel("Device Model:"), 0, 0)
        self.device_model_label = QLabel("Unknown")
        device_info_layout.addWidget(self.device_model_label, 0, 1)

        device_info_layout.addWidget(QLabel("Android Version:"), 1, 0)
        self.android_version_label = QLabel("Unknown")
        device_info_layout.addWidget(self.android_version_label, 1, 1)

        device_info_layout.addWidget(QLabel("Chipset:"), 2, 0)
        self.chipset_label = QLabel("Unknown")
        device_info_layout.addWidget(self.chipset_label, 2, 1)

        device_info_layout.addWidget(QLabel("Connection State:"), 3, 0)
        self.connection_state_label = QLabel("Disconnected")
        device_info_layout.addWidget(self.connection_state_label, 3, 1)

        layout.addWidget(device_info_box)

        self.bypass_tabs = QTabWidget()

        self.bypass_tabs.addTab(self._create_device_scanner_tab(), "🔍 Device Scanner")

        existing_titles = set()
        for profile in self._profiles:
            tab_title = profile["category"]
            if tab_title in existing_titles:
                tab_title = f"{profile['category']} ({profile['filename'].replace('.py', '')})"
            existing_titles.add(tab_title)

            tab = self._create_profile_tab(profile)
            self.bypass_tabs.addTab(tab, tab_title)

        if not self._profiles:
            empty_tab = QWidget()
            empty_layout = QVBoxLayout(empty_tab)
            empty_label = QLabel("No bypass profiles found in core/bypass/")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(empty_label)
            self.bypass_tabs.addTab(empty_tab, "No Profiles")

        self.bypass_tabs.addTab(self._create_hardware_tab(), "Hardware Utilities")

        layout.addWidget(self.bypass_tabs)

        progress_box = QGroupBox("Operation Progress")
        progress_layout = QVBoxLayout(progress_box)

        self.bypass_progress = QProgressBar()
        self.bypass_progress.setMaximumHeight(12)
        progress_layout.addWidget(self.bypass_progress)

        self.bypass_status_label = QLabel("Ready.")
        progress_layout.addWidget(self.bypass_status_label)

        layout.addWidget(progress_box)
        layout.addStretch()

    def _create_profile_tab(self, profile: dict) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info_label = QLabel(
            f"{profile['category']} bypass methods.\n"
            f"Source: {profile['filename']}"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color:#607080; font-size:11px; margin-bottom:10px;")
        layout.addWidget(info_label)

        group = QGroupBox(f"{profile['category']} Methods")
        group_layout = QVBoxLayout(group)

        for method_name in profile["methods"]:
            btn = QPushButton(method_name.replace("_", " ").title())
            btn.setToolTip(f"Execute {method_name} from {profile['filename']}")
            btn.clicked.connect(
                lambda _, m=method_name, p=profile: self._execute_profile_method(p, m)
            )
            group_layout.addWidget(btn)

        layout.addWidget(group)
        layout.addStretch()
        return w

    def _create_hardware_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info_label = QLabel(
            "Hardware-based bypass utilities.\n"
            "These operations reboot the device into specialized modes."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color:#607080; font-size:11px; margin-bottom:10px;")
        layout.addWidget(info_label)

        hardware_group = QGroupBox("Hardware Utilities")
        hardware_layout = QVBoxLayout(hardware_group)

        btn_edl = QPushButton("Qualcomm EDL Mode")
        btn_edl.setToolTip("Enter Qualcomm EDL mode for FRP bypass")
        btn_edl.clicked.connect(self._execute_edl_mode)
        hardware_layout.addWidget(btn_edl)

        btn_mtk = QPushButton("MediaTek Download Mode")
        btn_mtk.setToolTip("Enter MediaTek download mode")
        btn_mtk.clicked.connect(self._execute_mtk_download_mode)
        hardware_layout.addWidget(btn_mtk)

        btn_samsung = QPushButton("Samsung Download Mode")
        btn_samsung.setToolTip("Enter Samsung download mode (ODIN)")
        btn_samsung.clicked.connect(self._execute_samsung_download_mode)
        hardware_layout.addWidget(btn_samsung)

        layout.addWidget(hardware_group)
        layout.addStretch()
        return w

    def _get_device_info(self) -> dict:
        try:
            if hasattr(self, "_proto") and self._proto:
                info = self._proto.get_device_info()
                if info:
                    return {
                        "serial": getattr(info, "serial", ""),
                        "model": getattr(info, "model", ""),
                        "brand": getattr(info, "brand", ""),
                        "platform": "android",
                        "android_version": getattr(info, "android_version", ""),
                    }
        except Exception as e:
            self.logger.error(f"Error getting device info: {e}")
        return {}

    def _create_bypass_instance(self, profile: dict):
        module_name = profile["module_name"]
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                str(
                    Path(__file__).resolve().parent.parent.parent
                    / "core"
                    / "bypass"
                    / f"{profile['filename']}"
                ),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            self.logger.error(f"Failed to load {module_name}: {e}")
            return None
        cls = getattr(module, profile["class_name"])
        device_info = self._get_device_info()
        logger = self.logger

        try:
            sig = inspect.signature(cls.__init__)
            params = [p for p in sig.parameters if p != "self"]

            if "device_info" in params and "logger" in params:
                instance = cls(device_info, logger)
                if hasattr(instance, "device_serial") and device_info:
                    instance.device_serial = device_info.get("serial", "")
                return instance
            elif "device" in params and "logger" in params:
                try:
                    from core.usb_detection import USBDetector, USBDevice
                    usb_devices = USBDetector().scan()
                    usb_device = usb_devices[0] if usb_devices else USBDevice(vendor_id=0, product_id=0)
                    return cls(usb_device, logger)
                except Exception:
                    return cls(None, logger)
            elif "adb_path" in params:
                adb_path = getattr(self._adb, "_adb", None) or "adb"
                if "fastboot_path" in params:
                    instance = cls(adb_path, "fastboot")
                else:
                    instance = cls(adb_path)
                if hasattr(instance, "device_serial") and device_info:
                    instance.device_serial = device_info.get("serial", "")
                return instance
            else:
                return cls()
        except Exception:
            try:
                return cls()
            except Exception:
                return None

    def _handle_bypass_result(self, result, method_name: str):
        if isinstance(result, bool):
            if result:
                QMessageBox.information(self, "Success", f"{method_name} completed successfully!")
            else:
                QMessageBox.warning(self, "Failed", f"{method_name} failed.")
        elif hasattr(result, "success"):
            if result.success:
                QMessageBox.information(self, "Success", getattr(result, "message", "Success"))
            else:
                QMessageBox.warning(self, "Failed", getattr(result, "message", "Failed"))
        elif result is not None:
            QMessageBox.information(self, "Success", f"{method_name} executed successfully!")
        else:
            QMessageBox.warning(self, "Failed", f"{method_name} failed.")

    def _execute_profile_method(self, profile: dict, method_name: str):
        try:
            instance = self._create_bypass_instance(profile)
            if instance is None:
                QMessageBox.critical(
                    self, "Error",
                    f"Failed to instantiate {profile['class_name']} from {profile['filename']}"
                )
                return

            method = getattr(instance, method_name)
            self.bypass_status_label.setText(f"Executing {method_name}...")
            self.bypass_progress.setValue(0)

            result = method()
            self._handle_bypass_result(result, method_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Bypass error: {str(e)}")
        finally:
            self.bypass_status_label.setText("Ready.")
            self.bypass_progress.setValue(0)

    def _execute_edl_mode(self):
        device_info = self._get_device_info()
        if not device_info:
            QMessageBox.warning(self, "No Device", "No device connected. Please connect a device first.")
            return

        reply = QMessageBox.question(
            self,
            "Enter EDL Mode",
            "This will attempt to put the device into Qualcomm EDL mode.\n\n"
            "Make sure the device is connected and ADB is authorized.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.bypass_status_label.setText("Entering EDL mode...")
            self.bypass_progress.setValue(50)
            try:
                success = self._adb.reboot_edl(device_info.get("serial", ""))
                if success:
                    QMessageBox.information(self, "Success", "EDL mode command sent. Check device for EDL mode.")
                else:
                    QMessageBox.warning(self, "Failed", "Failed to send EDL mode command.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"EDL mode error: {str(e)}")
            finally:
                self.bypass_status_label.setText("Ready.")
                self.bypass_progress.setValue(0)

    def _execute_mtk_download_mode(self):
        device_info = self._get_device_info()
        if not device_info:
            QMessageBox.warning(self, "No Device", "No device connected. Please connect a device first.")
            return

        reply = QMessageBox.question(
            self,
            "Enter MTK Download Mode",
            "This will attempt to put the device into MediaTek download mode.\n\n"
            "Make sure the device is connected and ADB is authorized.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.bypass_status_label.setText("Entering MTK download mode...")
            self.bypass_progress.setValue(50)
            try:
                success = self._adb.reboot("download", device_info.get("serial", ""))
                if success:
                    QMessageBox.information(self, "Success", "Download mode command sent. Check device for download mode.")
                else:
                    QMessageBox.warning(self, "Failed", "Failed to send download mode command.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Download mode error: {str(e)}")
            finally:
                self.bypass_status_label.setText("Ready.")
                self.bypass_progress.setValue(0)

    def _execute_samsung_download_mode(self):
        device_info = self._get_device_info()
        if not device_info:
            QMessageBox.warning(self, "No Device", "No device connected. Please connect a device first.")
            return

        reply = QMessageBox.question(
            self,
            "Enter Samsung Download Mode",
            "This will attempt to put the device into Samsung download mode (ODIN mode).\n\n"
            "Make sure the device is connected and ADB is authorized.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.bypass_status_label.setText("Entering Samsung download mode...")
            self.bypass_progress.setValue(50)
            try:
                success = self._adb.reboot("download", device_info.get("serial", ""))
                if success:
                    QMessageBox.information(self, "Success", "Download mode command sent. Check device for download mode.")
                else:
                    QMessageBox.warning(self, "Failed", "Failed to send download mode command.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Download mode error: {str(e)}")
            finally:
                self.bypass_status_label.setText("Ready.")
                self.bypass_progress.setValue(0)

    def _update_device_info(self):
        try:
            device_info = self._get_device_info()
            if device_info:
                self.device_model_label.setText(f"{device_info.get('brand', 'Unknown')} {device_info.get('model', 'Unknown')}")
                self.android_version_label.setText(device_info.get("android_version", "Unknown"))
                self.chipset_label.setText(device_info.get("chipset", "Unknown"))
                self.connection_state_label.setText("Connected")
            else:
                self.device_model_label.setText("No device")
                self.android_version_label.setText("Unknown")
                self.chipset_label.setText("Unknown")
                self.connection_state_label.setText("Disconnected")
        except Exception as e:
            self.device_model_label.setText("Error")
            self.android_version_label.setText("Unknown")
            self.chipset_label.setText("Unknown")
            self.connection_state_label.setText("Error")

    def _create_device_scanner_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info_label = QLabel(
            "Comprehensive device scanner using USB detection, ADB, and fastboot.\n"
            "Detects MediaTek BROM/Preloader, Qualcomm EDL, ADB, fastboot, and more."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color:#607080; font-size:11px; margin-bottom:10px;")
        layout.addWidget(info_label)

        controls = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Now")
        self.btn_scan.clicked.connect(self._scan_all_devices)
        controls.addWidget(self.btn_scan)

        self.chk_auto_scan = QCheckBox("Auto-Scan")
        self.chk_auto_scan.setToolTip("Automatically rescan every 2 seconds")
        controls.addWidget(self.chk_auto_scan)

        controls.addStretch()
        layout.addLayout(controls)

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(6)
        self.device_table.setHorizontalHeaderLabels([
            "Type", "Serial/ID", "Mode", "Manufacturer", "Model", "Details"
        ])
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.device_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.device_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.device_table.setAlternatingRowColors(True)
        layout.addWidget(self.device_table)

        self.scan_status_label = QLabel("Ready to scan.")
        self.scan_status_label.setStyleSheet("color:#607080; font-size:11px;")
        layout.addWidget(self.scan_status_label)

        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._scan_all_devices)
        self.chk_auto_scan.toggled.connect(self._on_auto_scan_toggled)

        return w

    def _on_auto_scan_toggled(self, checked: bool):
        if checked:
            self._scan_timer.start(2000)
            self._scan_all_devices()
        else:
            self._scan_timer.stop()

    def _scan_all_devices(self):
        self.btn_scan.setEnabled(False)
        self.scan_status_label.setText("Scanning...")
        try:
            devices = self._collect_all_devices()
            self._populate_device_table(devices)
            self.scan_status_label.setText(f"Found {len(devices)} device(s)")
        except Exception as e:
            self.logger.error(f"Device scan failed: {e}")
            self.scan_status_label.setText(f"Scan failed: {e}")
        finally:
            self.btn_scan.setEnabled(True)

    def _collect_all_devices(self) -> List[dict]:
        devices: List[dict] = []

        try:
            from core.discovery import UsbDetector
            for desc in UsbDetector().scan():
                devices.append({
                    "type": "USB",
                    "serial": desc.serial_number or desc.stable_id,
                    "mode": desc.mode.value if hasattr(desc.mode, "value") else str(desc.mode),
                    "manufacturer": desc.manufacturer or "",
                    "model": desc.product or "",
                    "details": f"VID:PID {desc.identifier.key if hasattr(desc, 'identifier') else '?'}",
                })
        except Exception as e:
            self.logger.debug(f"Discovery scan failed: {e}")

        try:
            from core.device_manager import DeviceManager
            dm = DeviceManager()
            for dev in dm.scan_devices():
                devices.append({
                    "type": dev.connection_type.upper(),
                    "serial": dev.serial,
                    "mode": dev.state.value if hasattr(dev.state, "value") else str(dev.state),
                    "manufacturer": dev.manufacturer or dev.brand,
                    "model": dev.model,
                    "details": f"Android {dev.android_version} | {dev.chipset}",
                })
        except Exception as e:
            self.logger.debug(f"DeviceManager scan failed: {e}")

        try:
            from core.usb_detection import USBDetector
            for usb_dev in USBDetector().scan():
                mode_name = usb_dev.mode.name if hasattr(usb_dev.mode, "name") else str(usb_dev.mode)
                devices.append({
                    "type": "USB-DETECT",
                    "serial": usb_dev.serial or usb_dev.stable_id,
                    "mode": mode_name,
                    "manufacturer": usb_dev.manufacturer or "",
                    "model": usb_dev.product or "",
                    "details": f"VID:PID {usb_dev.vid_pid}",
                })
        except Exception as e:
            self.logger.debug(f"USB detection scan failed: {e}")

        seen = set()
        unique = []
        for dev in devices:
            key = (dev.get("type"), dev.get("serial"), dev.get("mode"))
            if key not in seen:
                seen.add(key)
                unique.append(dev)
        return unique

    def _populate_device_table(self, devices: List[dict]):
        self.device_table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.device_table.setItem(row, 0, QTableWidgetItem(dev.get("type", "")))
            self.device_table.setItem(row, 1, QTableWidgetItem(dev.get("serial", "")))
            self.device_table.setItem(row, 2, QTableWidgetItem(dev.get("mode", "")))
            self.device_table.setItem(row, 3, QTableWidgetItem(dev.get("manufacturer", "")))
            self.device_table.setItem(row, 4, QTableWidgetItem(dev.get("model", "")))
            self.device_table.setItem(row, 5, QTableWidgetItem(dev.get("details", "")))
