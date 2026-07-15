"""
USB Manager — compatibility shim for legacy USBManager references.

Legacy bypass modules expect a USBManager class with connect_device()
and disconnect_device(). This module adapts core.usb_detection.USBDetector
to that interface.
"""
from typing import Any, Optional

from core.usb_detection import USBDetector, USBDevice


class USBManager:
    """Compatibility wrapper around USBDetector for legacy bypass modules."""

    def __init__(self, logger=None):
        self._logger = logger
        self._detector = USBDetector()
        self._connected: dict = {}

    def connect_device(self, vendor_id: int, product_id: int) -> Optional[USBDevice]:
        try:
            devices = self._detector.scan()
            for device in devices:
                if device.vendor_id == vendor_id and device.product_id == product_id:
                    key = (vendor_id, product_id)
                    self._connected[key] = device
                    return device
            return None
        except Exception as exc:
            if self._logger:
                self._logger.error(f"USBManager connect failed: {exc}")
            return None

    def disconnect_device(self, device: Any) -> None:
        try:
            if device is None:
                return
            key = (getattr(device, "vendor_id", 0), getattr(device, "product_id", 0))
            self._connected.pop(key, None)
        except Exception:
            pass
