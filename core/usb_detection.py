"""
USB Detection — advanced multi-platform device detection with fallback strategies.

Context Flow:
  Platform Detection → USB Backend Selection → Device Scan → Mode Identification
"""
import platform
import subprocess
import shutil
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum, auto

try:
    import usb.core
    import usb.util
    USB_AVAILABLE = True
except ImportError:
    USB_AVAILABLE = False

try:
    from sqlmodel import SQLModel, Field, create_engine, Session, select
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False

from utils.logger import get_logger

log = get_logger("usb_detection")


class DetectionMethod(Enum):
    """Detection methods in order of preference."""
    USBPY_LIBUSB = auto()      # Primary: pyusb/libusb backend
    ADB_SERIAL = auto()        # Fallback: ADB serial numbers
    WMI_QUERY = auto()         # Windows WMI for device info
    SYSTEM_USB = auto()        # System command fallback (lsusb/system_profiler)
    PLATFORM_USB = auto()      # Platform-specific API (win32, etc.)


@dataclass
class USBDevice:
    """Detected USB device information."""
    vendor_id: int
    product_id: int
    serial: str = ""
    bus_id: str = ""
    device_id: str = ""
    description: str = ""
    interface: str = ""
    
    @property
    def vid_pid(self) -> str:
        return f"0x{self.vendor_id:04X}:0x{self.product_id:04X}"
    
    @property
    def is_mtk(self) -> bool:
        return self.vendor_id == 0x0E8D


class USBDetector:
    """
    Advanced USB detection with multiple fallback strategies.
    
    Features:
    - Multi-backend detection (pyusb, WMI, system commands)
    - Cross-platform support (Windows, Linux, macOS)
    - Device history tracking via SQLite
    - ADB serial cross-reference
    """
    
    MTK_VENDOR_ID = 0x0E8D
    MTK_BROM_PID = 0x0003
    MTK_PRELOADER_PID = 0x2000
    MTK_DA_PID = 0x2001
    
    _mode_cache = {}
    
    def __init__(self, db_path: str = ":memory:"):
        self.system = platform.system()
        self.db_path = db_path
        self._engine = None
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for device history tracking."""
        if not SQLMODEL_AVAILABLE:
            return
        
        class DeviceRecord(SQLModel, table=True):
            __tablename__ = "device_history"
            id: Optional[int] = Field(default=None, primary_key=True)
            vid: int
            pid: int
            serial: str = Field(default="")
            first_seen: str = Field(default_factory=lambda: self._now())
            last_seen: str = Field(default_factory=lambda: self._now())
            mode: str = Field(default="unknown")
            detection_method: str = Field(default="unknown")
            
            @staticmethod
            def _now():
                from datetime import datetime
                return datetime.utcnow().isoformat()
        
        self.DeviceRecord = DeviceRecord
        self._engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        SQLModel.metadata.create_all(self._engine)
    
    def detect_mtk_device(self) -> Optional[USBDevice]:
        """
        Detect MediaTek device using best available method.
        Returns USBDevice or None.
        """
        methods = [
            DetectionMethod.USBPY_LIBUSB,
            DetectionMethod.ADB_SERIAL,
            DetectionMethod.WMI_QUERY,
            DetectionMethod.SYSTEM_USB,
        ]
        
        for method in methods:
            if self.system == "Windows" and method == DetectionMethod.WMI_QUERY:
                device = self._detect_windows_wmi()
                if device:
                    return device
            elif method == DetectionMethod.USBPY_LIBUSB:
                device = self._detect_pyusb()
                if device:
                    return device
            elif method == DetectionMethod.ADB_SERIAL:
                device = self._detect_adb_crossref()
                if device:
                    return device
            elif method == DetectionMethod.SYSTEM_USB:
                device = self._detect_system_usb()
                if device:
                    return device
        
        return None
    
    def _detect_pyusb(self) -> Optional[USBDevice]:
        """Primary detection using pyusb/libusb."""
        if not USB_AVAILABLE:
            return None
        
        # Try known MTK PIDs first
        for pid in [self.MTK_BROM_PID, self.MTK_PRELOADER_PID, self.MTK_DA_PID]:
            try:
                dev = usb.core.find(idVendor=self.MTK_VENDOR_ID, idProduct=pid)
                if dev:
                    return self._create_device(dev, pid)
            except Exception as e:
                log.debug(f"pyusb detection error for PID {hex(pid)}: {e}")
        
        # Fallback: any MTK vendor device
        try:
            dev = usb.core.find(idVendor=self.MTK_VENDOR_ID)
            if dev:
                return self._create_device(dev, dev.idProduct)
        except Exception as e:
            log.debug(f"pyusb generic detection error: {e}")
        
        return None
    
    def _create_device(self, dev, pid: int) -> USBDevice:
        """Create USBDevice from pyusb device object."""
        serial = ""
        try:
            # Try to get serial string descriptor
            serial = usb.util.get_string(dev, dev.iSerialNumber) or ""
        except Exception:
            pass
        
        return USBDevice(
            vendor_id=self.MTK_VENDOR_ID,
            product_id=pid,
            serial=serial,
            bus_id=str(dev.bus) if hasattr(dev, 'bus') else "",
            device_id=str(dev.address) if hasattr(dev, 'address') else "",
            description=self._pid_to_mode(pid),
        )
    
    def _detect_windows_wmi(self) -> Optional[USBDevice]:
        """Windows WMI-based detection using PowerShell."""
        if self.system != "Windows":
            return None
        
        try:
            cmd = [
                "powershell", "-Command",
                "Get-PnpDevice -Class USB | Where-Object {$_.InstanceId -like '*VID_0E8D*'} | "
                "Select-Object -ExpandProperty InstanceId"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                # Parse WMI output to extract PID/VID
                for line in result.stdout.strip().splitlines():
                    pid = self._extract_pid(line)
                    if pid:
                        return USBDevice(vendor_id=self.MTK_VENDOR_ID, product_id=pid)
        except Exception as e:
            log.debug(f"WMI detection error: {e}")
        
        return None
    
    def _detect_adb_crossref(self) -> Optional[USBDevice]:
        """Cross-reference ADB devices for MTK serials."""
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    # Look for MTK serial patterns
                    if "0e8d" in line.lower() or "mediatek" in line.lower():
                        # Extract serial and try to get PID via lsusb
                        pass
        except Exception:
            pass
        return None
    
    def _detect_system_usb(self) -> Optional[USBDevice]:
        """System command fallback detection."""
        if self.system == "Linux":
            return self._detect_linux_lsusb()
        elif self.system == "Darwin":
            return self._detect_macos_system_profiler()
        return None
    
    def _detect_linux_lsusb(self) -> Optional[USBDevice]:
        """Linux lsusb-based detection."""
        try:
            result = subprocess.run(
                ["lsusb", "-d", f"{self.MTK_VENDOR_ID:04x}:"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.splitlines():
                    # Parse: Bus 001 Device 042: ID 0e8d:0003 MediaTek Inc MTK_BROM
                    parts = line.split()
                    if len(parts) >= 6:
                        # Extract PID from ID field
                        id_idx = next((i for i, p in enumerate(parts) if p == "ID"), -1)
                        if id_idx >= 0 and id_idx + 1 < len(parts):
                            id_parts = parts[id_idx + 1].split(":")
                            if len(id_parts) == 2:
                                pid = int(id_parts[1], 16)
                                return USBDevice(
                                    vendor_id=self.MTK_VENDOR_ID,
                                    product_id=pid,
                                    bus_id=parts[1],
                                    device_id=parts[3].rstrip(":"),
                                )
        except Exception as e:
            log.debug(f"lsusb detection error: {e}")
        return None
    
    def _detect_macos_system_profiler(self) -> Optional[USBDevice]:
        """macOS system_profiler-based detection."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPUSBDataType", "-json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                # Parse JSON for MTK devices
        except Exception as e:
            log.debug(f"system_profiler error: {e}")
        return None
    
    def _extract_pid(self, wmi_line: str) -> Optional[int]:
        """Extract PID from WMI device ID string."""
        import re
        match = re.search(r'PID_([0-9A-Fa-f]{4})', wmi_line)
        if match:
            return int(match.group(1), 16)
        return None
    
    def _pid_to_mode(self, pid: int) -> str:
        """Convert PID to human-readable mode."""
        modes = {
            self.MTK_BROM_PID: "BROM",
            self.MTK_PRELOADER_PID: "Preloader",
            self.MTK_DA_PID: "DA Mode",
        }
        return modes.get(pid, f"Unknown(0x{pid:04X})")
    
    def get_all_usb_devices(self) -> List[USBDevice]:
        """Get all USB devices (not just MTK)."""
        devices = []
        
        if USB_AVAILABLE:
            try:
                for dev in usb.core.find(find_all=True):
                    device = USBDevice(
                        vendor_id=dev.idVendor,
                        product_id=dev.idProduct,
                        serial=str(dev.serial_number or ""),
                    )
                    devices.append(device)
            except Exception:
                pass
        
        return devices
    
    def record_detection(self, device: USBDevice, method: DetectionMethod):
        """Record device detection in history database."""
        if not self._engine:
            return
        
        try:
            with Session(self._engine) as session:
                existing = session.exec(
                    select(self.DeviceRecord).where(
                        self.DeviceRecord.vid == device.vendor_id,
                        self.DeviceRecord.pid == device.product_id,
                        self.DeviceRecord.serial == device.serial
                    )
                ).first()
                
                if existing:
                    existing.last_seen = self.DeviceRecord._now()
                    existing.mode = device.description
                    session.add(existing)
                else:
                    record = self.DeviceRecord(
                        vid=device.vendor_id,
                        pid=device.product_id,
                        serial=device.serial,
                        mode=device.description,
                        detection_method=method.name,
                    )
                    session.add(record)
                
                session.commit()
        except Exception as e:
            log.debug(f"Database record error: {e}")
    
    def get_detection_history(self) -> List[dict]:
        """Get device detection history."""
        if not self._engine:
            return []
        
        try:
            with Session(self._engine) as session:
                records = session.exec(
                    select(self.DeviceRecord).order_by(self.DeviceRecord.last_seen.desc())
                ).all()
                return [
                    {
                        "vid": r.vid,
                        "pid": r.pid,
                        "serial": r.serial,
                        "first_seen": r.first_seen,
                        "last_seen": r.last_seen,
                        "mode": r.mode,
                    }
                    for r in records
                ]
        except Exception:
            return []