from .mtk_protocol import MTKProtocol, DeviceInfo, ConnState
from .mtk_chipset_db import CHIPSET_DB, lookup, lookup_by_name, is_v6, is_kaeru_compatible
from .partition_manager import ScatterParser, Partition
from .flash_engine import FlashEngine, OpType
from .adb_bridge import ADBBridge
from .scatter_generator import ScatterGenerator
from .payload_manager import PayloadManager
from .usb_detection import USBDetector, USBDevice, DetectionMethod

# Database module (optional)
try:
    from .database import DatabaseService
except ImportError:
    DatabaseService = None

__all__ = [
    "MTKProtocol", "DeviceInfo", "ConnState",
    "CHIPSET_DB", "lookup", "lookup_by_name", "is_v6", "is_kaeru_compatible",
    "ScatterParser", "Partition",
    "FlashEngine", "OpType",
    "ADBBridge",
    "ScatterGenerator",
    "PayloadManager",
    "USBDetector", "USBDevice", "DetectionMethod",
    "DatabaseService",
]
