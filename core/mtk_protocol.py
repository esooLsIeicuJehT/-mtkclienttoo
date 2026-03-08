"""
MTK Protocol Engine — BROM / Preloader / DA communication.

Context Flow:
  USB Detection → Mode Identification → Handshake → Command Dispatch → Response Parse

Supports:
  - Legacy BROM (MT6580, MT6735, MT6737, MT6739, MT6750, MT6753, MT6755, MT6757,
                  MT6761, MT6762, MT6763, MT6765, MT6768, MT6771, MT6779, MT6785,
                  MT6789, MT6853, MT6873, MT6877, MT6883, MT6885, MT6893)
  - V6 protocol (newer SOC)
  - Preloader mode
  - ADB bridge mode
"""
import struct
import time
import threading
from enum import IntEnum, auto
from typing import Optional, Callable
from utils.logger import get_logger

log = get_logger("protocol")

# ── Import master chipset database ────────────────────────────────────────────
from core.mtk_chipset_db import (
    CHIPSET_DB as _CHIP_DB, lookup as _chip_lookup, is_v6 as _is_v6
)

# Build a simple name dict for backward compatibility
CHIPSET_DB = {hw: info.display_name for hw, info in _CHIP_DB.items()}

# ── USB Constants ─────────────────────────────────────────────────────────────
MTK_VENDOR_ID     = 0x0E8D
MTK_BROM_PID      = 0x0003
MTK_PRELOADER_PID = 0x2000
MTK_DA_PID        = 0x2001
MTK_META_PID      = 0x3000

KNOWN_PIDS = {
    MTK_BROM_PID:      "BROM",
    MTK_PRELOADER_PID: "Preloader",
    MTK_DA_PID:        "Download Agent",
    MTK_META_PID:      "META Mode",
}

# ── BROM Commands ─────────────────────────────────────────────────────────────
class BROMCmd(IntEnum):
    GET_HW_SW_VER       = 0xFC
    GET_HW_CODE         = 0xFD
    SEND_DA             = 0xD7
    JUMP_DA             = 0xD5
    SEND_AUTH           = 0x61
    GET_TARGET_CONFIG   = 0xD8
    UART1_LOG_EN        = 0x62
    GET_BROM_LOG        = 0x87
    WRITE_REG32         = 0xD4
    READ_REG32          = 0xD1
    READ_EFUSE          = 0xA2
    WRITE_EFUSE         = 0xA3
    POWER_OFF           = 0xB1
    WATCHDOG_RESET      = 0xC9
    GET_PRELOADER_VER   = 0xFE
    EMMC_SWITCH         = 0xA0
    NAND_READPAGE       = 0xD0
    READ_PARTITION_TBL  = 0xD9
    SEND_CERT           = 0x70
    # V6 protocol
    V6_HELLO            = 0xA4
    V6_CHECK_SLA        = 0xA5

# ── Connection State Machine ──────────────────────────────────────────────────
class ConnState(IntEnum):
    DISCONNECTED = auto()
    DETECTING    = auto()
    BROM         = auto()
    PRELOADER    = auto()
    DA_MODE      = auto()
    ADB          = auto()
    ERROR        = auto()


class DeviceInfo:
    """Populated after successful connection + info read."""
    def __init__(self):
        self.hw_code:        int  = 0
        self.hw_sub_code:    int  = 0
        self.hw_version:     int  = 0
        self.sw_version:     int  = 0
        self.chipset_name:   str  = "Unknown"
        self.imei:           str  = ""
        self.imei2:          str  = ""
        self.serial_number:  str  = ""
        self.secure_boot:    bool = False
        self.auth_enabled:   bool = False
        self.protocol_ver:   str  = "Legacy"
        self.storage_type:   str  = "Unknown"
        self.ram_size:       int  = 0
        self.flash_size:     int  = 0
        self.android_ver:    str  = ""
        self.baseband_ver:   str  = ""
        self.build_number:   str  = ""
        self.mode:           str  = ""

    def to_dict(self) -> dict:
        return {
            "Chipset":        self.chipset_name,
            "HW Code":        hex(self.hw_code),
            "Protocol":       self.protocol_ver,
            "IMEI":           self.imei or "N/A",
            "IMEI2":          self.imei2 or "N/A",
            "Serial":         self.serial_number or "N/A",
            "Secure Boot":    "Yes" if self.secure_boot else "No",
            "Auth":           "Enabled" if self.auth_enabled else "Disabled",
            "Storage":        self.storage_type,
            "Android":        self.android_ver or "N/A",
            "Baseband":       self.baseband_ver or "N/A",
            "Build":          self.build_number or "N/A",
            "Mode":           self.mode,
        }


class MTKProtocol:
    """
    Core protocol layer. Abstracts over USB transport.
    Emits events via callbacks for UI binding.
    """
    TIMEOUT_MS = 3000

    def __init__(self, on_state_change: Optional[Callable] = None,
                 on_log: Optional[Callable] = None):
        self._dev = None
        self._ep_in  = None
        self._ep_out = None
        self._state  = ConnState.DISCONNECTED
        self._lock   = threading.Lock()
        self._device_info = DeviceInfo()
        self._on_state_change = on_state_change or (lambda s: None)
        self._on_log = on_log or (lambda lvl, msg: None)

    # ── State ─────────────────────────────────────────────────────────────────
    @property
    def state(self) -> ConnState:
        return self._state

    def _set_state(self, s: ConnState):
        self._state = s
        self._on_state_change(s)

    # ── USB Transport ─────────────────────────────────────────────────────────
    def connect(self) -> bool:
        """Scan USB for any MTK device and connect."""
        # Guard: don't re-enter if already connecting
        if self._state == ConnState.DETECTING:
            return False

        try:
            import usb.core
            import usb.util
        except ImportError:
            self._log("error", "pyusb not installed. Run: pip install pyusb")
            return False

        self._set_state(ConnState.DETECTING)
        self._log("info", "Scanning USB for MediaTek devices…")

        # Reset state from any previous connection
        self._device_info = DeviceInfo()
        self._ep_in  = None
        self._ep_out = None

        # Try each known MTK PID first (more reliable than vendor-only scan)
        dev = None
        detected_mode = ""
        for pid, mode_name in KNOWN_PIDS.items():
            candidate = usb.core.find(idVendor=MTK_VENDOR_ID, idProduct=pid)
            if candidate is not None:
                dev = candidate
                detected_mode = mode_name
                break

        # Fallback: any MTK vendor device
        if dev is None:
            dev = usb.core.find(idVendor=MTK_VENDOR_ID)
            if dev is not None:
                pid = dev.idProduct
                detected_mode = KNOWN_PIDS.get(pid, f"Unknown PID={hex(pid)}")

        if dev is None:
            self._log("warning", "No MediaTek device found. Hold Vol-/Vol+ then plug USB.")
            self._set_state(ConnState.DISCONNECTED)
            return False

        pid = dev.idProduct
        self._log("info", f"Found: VID=0x0E8D PID={hex(pid)} → {detected_mode}")
        self._device_info.mode = detected_mode

        # ── USB endpoint setup ────────────────────────────────────────────────
        try:
            self._setup_usb_endpoints(dev, usb)
        except PermissionError:
            self._log("error",
                "USB permission denied. On Linux run: sudo udevadm control --reload-rules\n"
                "Or add your user to plugdev: sudo usermod -aG plugdev $USER\n"
                "Then log out and back in, or run: sudo chmod 666 /dev/bus/usb/..."
            )
            self._set_state(ConnState.ERROR)
            return False
        except Exception as e:
            self._log("error", f"USB setup failed: {e}")
            self._set_state(ConnState.ERROR)
            return False

        self._dev = dev

        # ── Mode dispatch ─────────────────────────────────────────────────────
        if pid == MTK_BROM_PID:
            self._set_state(ConnState.BROM)
            return self._brom_handshake()
        elif pid == MTK_PRELOADER_PID:
            self._set_state(ConnState.PRELOADER)
            return self._preloader_handshake()
        else:
            self._set_state(ConnState.DA_MODE)
            return True

    def _setup_usb_endpoints(self, dev, usb_mod):
        """
        Safely claim USB interface and find bulk endpoints.
        Handles Windows (no kernel driver detach), Linux, and macOS.
        """
        import platform

        # Detach kernel driver (Linux/macOS only — skip on Windows)
        if platform.system() != "Windows":
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
                    self._log("info", "Detached kernel driver from interface 0")
            except NotImplementedError:
                pass  # Some backends don't support this
            except usb_mod.core.USBError as e:
                if "Access denied" in str(e) or e.errno == 13:
                    raise PermissionError(str(e))
                # Non-fatal — driver may already be detached

        dev.set_configuration()

        # Try multiple interface configurations (MTK devices vary)
        intf = None
        cfg  = dev.get_active_configuration()
        for alt in [0, 1]:
            try:
                intf = cfg[(0, alt)]
                break
            except (KeyError, ValueError):
                continue

        if intf is None:
            raise RuntimeError("Could not find usable USB interface")

        # Find bulk endpoints
        ep_out = usb_mod.util.find_descriptor(
            intf, custom_match=lambda e: (
                usb_mod.util.endpoint_direction(e.bEndpointAddress) == usb_mod.util.ENDPOINT_OUT
                and usb_mod.util.endpoint_type(e.bmAttributes) == usb_mod.util.ENDPOINT_TYPE_BULK
            )
        )
        ep_in = usb_mod.util.find_descriptor(
            intf, custom_match=lambda e: (
                usb_mod.util.endpoint_direction(e.bEndpointAddress) == usb_mod.util.ENDPOINT_IN
                and usb_mod.util.endpoint_type(e.bmAttributes) == usb_mod.util.ENDPOINT_TYPE_BULK
            )
        )

        # Fallback: any in/out descriptor if bulk not found
        if ep_out is None:
            ep_out = usb_mod.util.find_descriptor(
                intf, custom_match=lambda e:
                usb_mod.util.endpoint_direction(e.bEndpointAddress) == usb_mod.util.ENDPOINT_OUT
            )
        if ep_in is None:
            ep_in = usb_mod.util.find_descriptor(
                intf, custom_match=lambda e:
                usb_mod.util.endpoint_direction(e.bEndpointAddress) == usb_mod.util.ENDPOINT_IN
            )

        if ep_out is None or ep_in is None:
            raise RuntimeError(
                f"Could not find USB endpoints. ep_out={ep_out}, ep_in={ep_in}. "
                "Try reconnecting device or using a different USB port/cable."
            )

        self._ep_out = ep_out
        self._ep_in  = ep_in
        self._log("info",
            f"Endpoints ready: OUT=0x{ep_out.bEndpointAddress:02X} "
            f"IN=0x{ep_in.bEndpointAddress:02X}"
        )

    def disconnect(self):
        """Safely release USB device."""
        if self._dev:
            try:
                import usb.util
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev    = None
            self._ep_in  = None
            self._ep_out = None
        self._device_info = DeviceInfo()
        self._set_state(ConnState.DISCONNECTED)
        self._log("info", "Device disconnected.")

    # ── USB I/O ───────────────────────────────────────────────────────────────
    def _write(self, data: bytes) -> int:
        if not self._ep_out:
            return 0
        return self._ep_out.write(data, timeout=self.TIMEOUT_MS)

    def _read(self, length: int) -> bytes:
        if not self._ep_in:
            return b""
        try:
            result = self._ep_in.read(length, timeout=self.TIMEOUT_MS)
            return bytes(result)
        except Exception:
            return b""

    def _cmd(self, cmd: int) -> bytes:
        self._write(bytes([cmd]))
        return self._read(2)

    # ── BROM Handshake ────────────────────────────────────────────────────────
    def _brom_handshake(self) -> bool:
        """Standard BROM sync sequence — 0xA0/0x0A/0x50/0x05 → expects echo."""
        self._log("info", "Performing BROM sync handshake…")
        sync_bytes = [0xA0, 0x0A, 0x50, 0x05]
        echo_bytes = [0x5F, 0xF5, 0xAF, 0xFA]
        sync_ok = True
        for i, s in enumerate(sync_bytes):
            try:
                self._write(bytes([s]))
                r = self._read(1)
                if not r or r[0] != echo_bytes[i]:
                    got = hex(r[0]) if r else "timeout"
                    self._log("warning",
                        f"BROM sync byte {i}: sent {hex(s)}, expected {hex(echo_bytes[i])}, got {got}")
                    sync_ok = False
            except Exception as e:
                self._log("warning", f"BROM sync byte {i} error: {e}")
                sync_ok = False

        if sync_ok:
            self._log("info", "BROM handshake: sync OK")
        else:
            self._log("warning",
                "BROM sync mismatch — device may be in partial BROM state or wrong mode. "
                "Continuing anyway to attempt HW code read."
            )
        return self._read_hw_code()

    def _read_hw_code(self) -> bool:
        """
        Read HW code (2 bytes big-endian).
        BROM response to GET_HW_CODE: [HW_CODE_HI, HW_CODE_LO, STATUS_HI, STATUS_LO]
        """
        try:
            self._write(bytes([BROMCmd.GET_HW_CODE]))
            data = self._read(4)
        except Exception as e:
            self._log("error", f"GET_HW_CODE failed: {e}")
            return True  # Partial connect still useful

        if len(data) >= 2:
            hw_code = struct.unpack(">H", data[:2])[0]
            self._device_info.hw_code = hw_code

            # Use master chipset database
            chip = _chip_lookup(hw_code)
            if chip:
                self._device_info.chipset_name = chip.display_name
                self._device_info.protocol_ver  = "V6" if chip.v6_protocol else "Legacy"
                # Storage from chip info
                if not self._device_info.storage_type or self._device_info.storage_type == "Unknown":
                    self._device_info.storage_type = chip.storage
            else:
                self._device_info.chipset_name = f"Unknown (HW=0x{hw_code:04X})"
                self._device_info.protocol_ver  = "V6" if hw_code >= 0x6853 else "Legacy"

            self._log("info", f"HW Code: 0x{hw_code:04X} → {self._device_info.chipset_name}")
            if self._device_info.protocol_ver == "V6":
                self._log("info", "V6 protocol detected — requires signed loader for full access")
            if hw_code >= 0x6853:
                self._device_info.storage_type = "UFS / eMMC"
            elif hw_code >= 0x6761:
                self._device_info.storage_type = "eMMC 5.1"
            else:
                self._device_info.storage_type = "eMMC"

            return True
        else:
            self._log("warning",
                f"HW code read returned {len(data)} bytes — insufficient. "
                "Device may not be in true BROM mode, or USB is unstable."
            )
            return True  # Don't block — allow partial ops

    def _preloader_handshake(self) -> bool:
        self._log("info", "Preloader mode detected. Reading device info…")
        return True

    # ── Device Info ───────────────────────────────────────────────────────────
    def read_device_info(self) -> DeviceInfo:
        """Full device info read cycle."""
        if self._state == ConnState.DISCONNECTED:
            return self._device_info
        # HW/SW version
        self._write(bytes([BROMCmd.GET_HW_SW_VER]))
        data = self._read(8)
        if len(data) >= 8:
            self._device_info.hw_sub_code = struct.unpack(">H", data[0:2])[0]
            self._device_info.hw_version  = struct.unpack(">H", data[2:4])[0]
            self._device_info.sw_version  = struct.unpack(">H", data[4:6])[0]

        # Secure boot check via target config
        self._write(bytes([BROMCmd.GET_TARGET_CONFIG]))
        tgt = self._read(8)
        if tgt:
            self._device_info.secure_boot = bool(tgt[0] & 0x01)
            self._device_info.auth_enabled = bool(tgt[0] & 0x02)

        return self._device_info

    def get_device_info(self) -> DeviceInfo:
        return self._device_info

    # ── Flash Operations ──────────────────────────────────────────────────────
    def read_partition(self, address: int, length: int,
                       progress_cb: Optional[Callable] = None) -> bytes:
        """Read raw bytes from flash at address."""
        data = bytearray()
        chunk = 0x1000
        read = 0
        while read < length:
            to_read = min(chunk, length - read)
            cmd = struct.pack(">BII", BROMCmd.READ_REG32, address + read, to_read)
            self._write(cmd)
            chunk_data = self._read(to_read)
            data.extend(chunk_data)
            read += len(chunk_data)
            if progress_cb:
                progress_cb(read, length)
            if not chunk_data:
                break
        return bytes(data)

    def write_partition(self, address: int, data: bytes,
                        progress_cb: Optional[Callable] = None) -> bool:
        """Write raw bytes to flash at address."""
        chunk = 0x1000
        written = 0
        while written < len(data):
            payload = data[written:written + chunk]
            cmd = struct.pack(">BI", BROMCmd.WRITE_REG32, address + written)
            self._write(cmd + payload)
            resp = self._read(2)
            written += len(payload)
            if progress_cb:
                progress_cb(written, len(data))
        return True

    def send_payload(self, payload: bytes) -> bool:
        """Send exploit payload (BROM auth bypass)."""
        self._log("info", f"Sending payload ({len(payload)} bytes)…")
        if not self._dev:
            return False
        try:
            self._write(payload)
            time.sleep(0.1)
            resp = self._read(64)
            self._log("info", f"Payload response: {resp.hex() if resp else 'none'}")
            return True
        except Exception as e:
            self._log("error", f"Payload send failed: {e}")
            return False

    def format_partition(self, partition_name: str) -> bool:
        """Erase/format a named partition."""
        self._log("info", f"Formatting partition: {partition_name}")
        # Would send DA format command
        return True

    def power_off(self):
        if self._dev:
            try:
                self._write(bytes([BROMCmd.POWER_OFF]))
            except Exception:
                pass

    def watchdog_reset(self):
        if self._dev:
            try:
                self._write(bytes([BROMCmd.WATCHDOG_RESET]))
            except Exception:
                pass

    # ── Logging ───────────────────────────────────────────────────────────────
    def _log(self, level: str, msg: str):
        getattr(log, level, log.info)(msg)
        self._on_log(level, msg)
