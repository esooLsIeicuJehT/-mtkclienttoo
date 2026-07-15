from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Final, Optional


_USB_ID_RE: Final = re.compile(
    r"^(?:0x)?(?P<vid>[0-9a-fA-F]{4})[:_-](?:0x)?(?P<pid>[0-9a-fA-F]{4})$"
)


class UsbVendor(Enum):
    """Common mobile-device USB vendor identifiers."""
    GOOGLE = 0x18D1
    MOTOROLA = 0x22B8
    SAMSUNG = 0x04E8
    QUALCOMM = 0x05C6
    MEDIATEK = 0x0E8D
    XIAOMI = 0x2717
    HUAWEI = 0x12D1
    ONEPLUS = 0x2A70
    OPPO = 0x22D9
    VIVO = 0x2D95
    SONY = 0x0FCE
    LG = 0x1004
    NOKIA = 0x0421
    APPLE = 0x05AC


class UsbMode(str, Enum):
    """Enumerates possible USB connection modes for mobile devices."""
    UNKNOWN = "unknown"
    ADB = "adb"
    FASTBOOT = "fastboot"
    RECOVERY = "recovery"
    DOWNLOAD = "download"
    EDL = "edl"
    BROM = "brom"
    PRELOADER = "preloader"
    DIAGNOSTIC = "diagnostic"
    MTP = "mtp"
    PTP = "ptp"
    MODEM = "modem"
    MASS_STORAGE = "mass_storage"


@dataclass(frozen=True, slots=True)
class UsbIdentifier:
    """Standardized wrapper for Vendor ID and Product ID."""
    vendor_id: int
    product_id: int

    @property
    def key(self) -> str:
        return f"{self.vendor_id:04x}:{self.product_id:04x}"

    @classmethod
    def from_str(cls, value: str) -> UsbIdentifier:
        match = _USB_ID_RE.match(value)
        if not match:
            raise ValueError(f"Invalid USB identifier structure: '{value}'")
        return cls(
            vendor_id=int(match.group("vid"), 16),
            product_id=int(match.group("pid"), 16),
        )


# Mapping known VID:PIDs to modes for rapid identification
KNOWN_USB_MODES: dict[UsbIdentifier, UsbMode] = {
    UsbIdentifier(0x18D1, 0x4EE7): UsbMode.ADB,        # Pixel ADB
    UsbIdentifier(0x18D1, 0xD00D): UsbMode.FASTBOOT,   # Pixel Bootloader/Fastboot
    UsbIdentifier(0x0E8D, 0x0003): UsbMode.BROM,       # MediaTek BootROM Mode
    UsbIdentifier(0x0E8D, 0x2000): UsbMode.PRELOADER,  # MediaTek Preloader Mode
    UsbIdentifier(0x05C6, 0x9008): UsbMode.EDL,        # Qualcomm Emergency Download Mode
    UsbIdentifier(0x04E8, 0x685D): UsbMode.DOWNLOAD,   # Samsung Odin Download Mode
    UsbIdentifier(0x04E8, 0x6860): UsbMode.ADB,        # Samsung Kies/ADB Mode
}


def infer_mode(
    identifier: UsbIdentifier,
    product: Optional[str] = None,
    interface_text: Optional[str] = None
) -> UsbMode:
    """
    Infers the device mode using direct lookup, falling back to matching
    keywords inside the product descriptor and interface text.
    """
    known = KNOWN_USB_MODES.get(identifier)
    if known is not None:
        return known

    haystack = " ".join(part for part in (product, interface_text) if part).lower()
    if not haystack:
        return UsbMode.UNKNOWN

    keywords: tuple[tuple[tuple[str, ...], UsbMode], ...] = (
        (("android bootloader", "fastboot"), UsbMode.FASTBOOT),
        (("android adb", "adb interface"), UsbMode.ADB),
        (("qualcomm", "qdloader", "9008"), UsbMode.EDL),
        (("mediatek usb port", "brom"), UsbMode.BROM),
        (("mediatek preloader", "preloader"), UsbMode.PRELOADER),
        (("download mode", "odin"), UsbMode.DOWNLOAD),
        (("recovery",), UsbMode.RECOVERY),
        (("diagnostic", "diag port"), UsbMode.DIAGNOSTIC),
        (("mtp",), UsbMode.MTP),
        (("ptp",), UsbMode.PTP),
        (("modem",), UsbMode.MODEM),
        (("mass storage",), UsbMode.MASS_STORAGE),
    )

    for matches, mode in keywords:
        if any(keyword in haystack for keyword in matches):
            return mode

    return UsbMode.UNKNOWN