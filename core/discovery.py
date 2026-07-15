from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
import logging
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Mapping, Optional
from enum import Enum

from .identifiers import UsbIdentifier, UsbMode, infer_mode

logger = logging.getLogger(__name__)

try:
    import pyudev
except ImportError:
    pyudev = None

try:
    import usb.core
    import usb.util
    HAS_PYUSB = True
except ImportError:
    HAS_PYUSB = False


@dataclass(frozen=True, slots=True)
class UsbInterfaceDescriptor:
    number: int | None = None
    class_code: int | None = None
    subclass_code: int | None = None
    protocol_code: int | None = None
    driver: str | None = None
    name: str | None = None

    @property
    def signature(self) -> str:
        values = (self.class_code, self.subclass_code, self.protocol_code)
        return ":".join("--" if v is None else f"{v:02x}" for v in values)


@dataclass(frozen=True, slots=True)
class UsbDeviceDescriptor:
    identifier: UsbIdentifier
    bus: int | None = None
    address: int | None = None
    port_path: str | None = None
    sys_path: Path | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    device_class: int | None = None
    device_subclass: int | None = None
    device_protocol: int | None = None
    interfaces: tuple[UsbInterfaceDescriptor, ...] = field(default_factory=tuple)
    properties: Mapping[str, str] = field(default_factory=dict)
    mode: UsbMode = UsbMode.UNKNOWN

    @property
    def stable_id(self) -> str:
        if self.serial_number:
            return f"usb:{self.identifier.key}:{self.serial_number}"
        if self.port_path:
            return f"usb:{self.identifier.key}:port-{self.port_path}"
        bus_str = "?" if self.bus is None else str(self.bus)
        addr_str = "?" if self.address is None else str(self.address)
        return f"usb:{self.identifier.key}:{bus_str}-{addr_str}"

    @property
    def display_name(self) -> str:
        label = " ".join(filter(None, (self.manufacturer, self.product))).strip()
        return label or f"USB Device [{self.identifier.key}]"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["identifier"] = self.identifier.key
        data["mode"] = self.mode.value
        data["sys_path"] = str(self.sys_path) if self.sys_path else None
        data["interfaces"] = [asdict(item) for item in self.interfaces]
        data["properties"] = dict(self.properties)
        return data


def parse_hex(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip(), 16)
    except (TypeError, ValueError):
        return None


class UsbDetector:
    """Handles USB discovery with PyUdev, falling back to sysfs or PyUSB."""
    def __init__(self, context: Any | None = None, sysfs_root: Path | str = "/sys/bus/usb/devices") -> None:
        self._context = context or (pyudev.Context() if pyudev else None)
        self._sysfs_root = Path(sysfs_root)

    def scan(self) -> list[UsbDeviceDescriptor]:
        if self._context is not None:
            return self._scan_udev()
        if self._sysfs_root.exists():
            return self._scan_sysfs()
        if HAS_PYUSB:
            return self._scan_pyusb()
        return []

    def _scan_udev(self) -> list[UsbDeviceDescriptor]:
        devices = []
        for dev in self._context.list_devices(subsystem="usb", devtype="usb_device"):
            descriptor = self.descriptor_from_udev(dev)
            if descriptor:
                devices.append(descriptor)
        return devices

    def _scan_sysfs(self) -> list[UsbDeviceDescriptor]:
        devices = []
        try:
            for entry in self._sysfs_root.iterdir():
                if entry.is_symlink() or entry.is_dir():
                    if entry.name.startswith("usb") or re.match(r"^\d+-\d+(?:\.\d+)*$", entry.name):
                        descriptor = self._parse_sysfs_device(entry)
                        if descriptor:
                            devices.append(descriptor)
        except Exception as e:
            logger.error(f"Sysfs scan failed: {e}")
        return devices

    def _scan_pyusb(self) -> list[UsbDeviceDescriptor]:
        devices = []
        try:
            for dev in usb.core.find(find_all=True):
                vid = dev.idVendor
                pid = dev.idProduct
                identifier = UsbIdentifier(vid, pid)
                
                try:
                    manufacturer = usb.util.get_string(dev, dev.iManufacturer)
                    product = usb.util.get_string(dev, dev.iProduct)
                    serial = usb.util.get_string(dev, dev.iSerialNumber)
                except Exception:
                    manufacturer, product, serial = None, None, None

                interfaces = []
                cfg = dev.active_configuration()
                if cfg:
                    for intf in cfg:
                        interfaces.append(
                            UsbInterfaceDescriptor(
                                number=intf.bInterfaceNumber,
                                class_code=intf.bInterfaceClass,
                                subclass_code=intf.bInterfaceSubClass,
                                protocol_code=intf.bInterfaceProtocol
                            )
                        )

                mode = infer_mode(identifier, product, None)
                devices.append(
                    UsbDeviceDescriptor(
                        identifier=identifier,
                        serial_number=serial,
                        manufacturer=manufacturer,
                        product=product,
                        device_class=dev.bDeviceClass,
                        device_subclass=dev.bDeviceSubClass,
                        device_protocol=dev.bDeviceProtocol,
                        interfaces=tuple(interfaces),
                        mode=mode
                    )
                )
        except Exception as e:
            logger.debug(f"PyUSB detection fallback failed: {e}")
        return devices

    def descriptor_from_udev(self, udev_device: Any) -> UsbDeviceDescriptor | None:
        usb_dev = self._as_usb_device(udev_device)
        if not usb_dev:
            return None

        vid = parse_hex(self._attribute(usb_dev, "idVendor"))
        pid = parse_hex(self._attribute(usb_dev, "idProduct"))
        if vid is None or pid is None:
            return None

        identifier = UsbIdentifier(vid, pid)
        serial = self._attribute(usb_dev, "serial")
        mfg = self._attribute(usb_dev, "manufacturer")
        prod = self._attribute(usb_dev, "product")

        interfaces = []
        for child in usb_dev.children:
            if child.get("DEVTYPE") == "usb_interface":
                interfaces.append(
                    UsbInterfaceDescriptor(
                        number=parse_hex(self._attribute(child, "bInterfaceNumber")),
                        class_code=parse_hex(self._attribute(child, "bInterfaceClass")),
                        subclass_code=parse_hex(self._attribute(child, "bInterfaceSubClass")),
                        protocol_code=parse_hex(self._attribute(child, "bInterfaceProtocol")),
                        driver=child.get("DRIVER"),
                        name=child.get("INTERFACE")
                    )
                )

        sys_path = Path(usb_dev.sys_path) if usb_dev.sys_path else None
        props = dict(usb_dev.properties)
        mode = infer_mode(identifier, prod, None)

        return UsbDeviceDescriptor(
            identifier=identifier,
            bus=parse_hex(self._attribute(usb_dev, "busnum")),
            address=parse_hex(self._attribute(usb_dev, "devnum")),
            port_path=self._attribute(usb_dev, "devpath"),
            sys_path=sys_path,
            serial_number=serial,
            manufacturer=mfg,
            product=prod,
            device_class=parse_hex(self._attribute(usb_dev, "bDeviceClass")),
            device_subclass=parse_hex(self._attribute(usb_dev, "bDeviceSubClass")),
            device_protocol=parse_hex(self._attribute(usb_dev, "bDeviceProtocol")),
            interfaces=tuple(interfaces),
            properties=props,
            mode=mode
        )

    def _parse_sysfs_device(self, entry: Path) -> UsbDeviceDescriptor | None:
        vid_raw = self._read(entry / "idVendor")
        pid_raw = self._read(entry / "idProduct")
        vid, pid = parse_hex(vid_raw), parse_hex(pid_raw)
        if vid is None or pid is None:
            return None

        identifier = UsbIdentifier(vid, pid)
        serial = self._read(entry / "serial")
        mfg = self._read(entry / "manufacturer")
        prod = self._read(entry / "product")

        # Parse interfaces
        interfaces = []
        for child in entry.iterdir():
            if child.name.startswith(f"{entry.name}:"):
                interfaces.append(
                    UsbInterfaceDescriptor(
                        number=parse_hex(self._read(child / "bInterfaceNumber")),
                        class_code=parse_hex(self._read(child / "bInterfaceClass")),
                        subclass_code=parse_hex(self._read(child / "bInterfaceSubClass")),
                        protocol_code=parse_hex(self._read(child / "bInterfaceProtocol")),
                        driver=self._read(child / "driver"),
                        name=self._read(child / "interface")
                    )
                )

        mode = infer_mode(identifier, prod, None)
        return UsbDeviceDescriptor(
            identifier=identifier,
            bus=parse_hex(self._read(entry / "busnum")),
            address=parse_hex(self._read(entry / "devnum")),
            port_path=self._read(entry / "devpath"),
            sys_path=entry,
            serial_number=serial,
            manufacturer=mfg,
            product=prod,
            device_class=parse_hex(self._read(entry / "bDeviceClass")),
            device_subclass=parse_hex(self._read(entry / "bDeviceSubClass")),
            device_protocol=parse_hex(self._read(entry / "bDeviceProtocol")),
            interfaces=tuple(interfaces),
            mode=mode
        )

    @staticmethod
    def _as_usb_device(device: Any) -> Any | None:
        if getattr(device, "subsystem", None) == "usb" and getattr(device, "device_type", None) == "usb_device":
            return device
        return device.find_parent(subsystem="usb", device_type="usb_device")

    @staticmethod
    def _attribute(device: Any, name: str) -> str | None:
        try:
            value = device.attributes.get(name)
        except (AttributeError, KeyError, OSError):
            return None
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode(errors="replace").strip()
        return str(value).strip()

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8", errors="replace").strip() or None
        except (FileNotFoundError, PermissionError, OSError):
            return None


class UsbHotplugAction(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class UsbHotplugEvent:
    action: UsbHotplugAction
    device: UsbDeviceDescriptor
    sequence_number: int | None = None


class UsbHotplugMonitor:
    """Threaded monitoring of Pyudev hotplug events."""
    def __init__(self, detector: UsbDetector, callback: Optional[Callable[[UsbHotplugEvent], None]] = None) -> None:
        if pyudev is None:
            raise RuntimeError("USB Hotplug monitoring requires 'pyudev'. Run 'pip install pyudev'.")
        self._detector = detector
        self._context = detector._context or pyudev.Context()
        self._callbacks = [callback] if callback else []
        self._observer: Any | None = None
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._observer is not None:
                return
            
            monitor = pyudev.Monitor.from_netlink(self._context)
            monitor.filter_by(subsystem="usb", device_type="usb_device")
            
            self._observer = pyudev.MonitorObserver(
                monitor,
                callback=self._on_udev_event,
                name="eclipse-usb-hotplug"
            )
            self._observer.start()

    def stop(self) -> None:
        with self._lock:
            observer, self._observer = self._observer, None
            if observer:
                observer.stop()

    def _on_udev_event(self, action: str, udev_device: Any) -> None:
        mapped_action = {
            "add": UsbHotplugAction.ADDED,
            "remove": UsbHotplugAction.REMOVED,
            "change": UsbHotplugAction.CHANGED,
            "bind": UsbHotplugAction.CHANGED,
            "unbind": UsbHotplugAction.CHANGED
        }.get(action)
        
        if mapped_action is None:
            return

        try:
            descriptor = self._detector.descriptor_from_udev(udev_device)
        except Exception:
            logger.exception("Failed parsing hotplug event descriptor")
            return
            
        if descriptor is None:
            return

        event = UsbHotplugEvent(
            action=mapped_action,
            device=descriptor,
            sequence_number=getattr(udev_device, "sequence_number", None)
        )

        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("Callback invocation failed on hotplug event")


class RegistryAction(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class RegisteredDevice:
    descriptor: UsbDeviceDescriptor
    first_seen: float
    last_seen: float

    @property
    def id(self) -> str:
        return self.descriptor.stable_id

    @property
    def mode(self) -> UsbMode:
        return self.descriptor.mode


@dataclass(frozen=True, slots=True)
class RegistryEvent:
    action: RegistryAction
    device: RegisteredDevice


class DeviceRegistry:
    """Thread-safe synchronization of active USB hardware components."""
    def __init__(self, detector: UsbDetector, monitor: UsbHotplugMonitor) -> None:
        self._detector = detector
        self._monitor = monitor
        self._devices: dict[str, RegisteredDevice] = {}
        self._callbacks: list[Callable[[RegistryEvent], None]] = []
        self._lock = RLock()

    def register_callback(self, cb: Callable[[RegistryEvent], None]) -> None:
        with self._lock:
            self._callbacks.append(cb)

    def start(self) -> None:
        with self._lock:
            # Seed current state
            now = time()
            for device in self._detector.scan():
                self._devices[device.stable_id] = RegisteredDevice(device, now, now)
            self._monitor._callbacks.append(self._handle_hotplug_event)
            self._monitor.start()

    def stop(self) -> None:
        self._monitor.stop()

    def get_devices(self) -> list[RegisteredDevice]:
        with self._lock:
            return list(self._devices.values())

    def _handle_hotplug_event(self, event: UsbHotplugEvent) -> None:
        now = time()
        stable_id = event.device.stable_id
        registry_event = None

        with self._lock:
            existing = self._devices.get(stable_id)
            if event.action == UsbHotplugAction.REMOVED:
                if existing:
                    removed = self._devices.pop(stable_id)
                    registry_event = RegistryEvent(
                        RegistryAction.REMOVED,
                        RegisteredDevice(removed.descriptor, removed.first_seen, now)
                    )
            elif existing is None:
                registered = RegisteredDevice(event.device, now, now)
                self._devices[stable_id] = registered
                registry_event = RegistryEvent(RegistryAction.ADDED, registered)
            else:
                registered = RegisteredDevice(event.device, existing.first_seen, now)
                self._devices[stable_id] = registered
                registry_event = RegistryEvent(RegistryAction.UPDATED, registered)

        if registry_event:
            for cb in self._callbacks:
                try:
                    cb(registry_event)
                except Exception:
                    logger.exception("Registry update dispatch failed")