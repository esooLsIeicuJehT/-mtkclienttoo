#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Fallback persistence import (SQLModel)
try:
    from sqlmodel import Field, SQLModel, Session, create_engine, select
    HAS_SQLMODEL = True
except ImportError:
    HAS_SQLMODEL = False
    class SQLModel: pass # Fallback stub


class DeviceState(Enum):
    UNKNOWN = "unknown"
    BOOTLOADER = "bootloader"
    FASTBOOT = "fastboot"
    ADB = "adb"
    RECOVERY = "recovery"
    DOWNLOAD = "download"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"


@dataclass
class DeviceInfo:
    """Consolidated stateful metrics representing logical and physical Android endpoints."""
    serial: str
    state: DeviceState
    brand: str = "unknown"
    model: str = "unknown"
    manufacturer: str = "unknown"
    android_version: str = "unknown"
    sdk_version: str = "unknown"
    bootloader_version: str = "unknown"
    security_patch: str = "unknown"
    frp_status: str = "unknown"
    connection_type: str = "unknown"  # adb, fastboot, download, serial-modem
    chipset: str = "unknown"
    imei: str = ""
    bootloader_status: str = "unknown"
    root_status: str = "unknown"
    encryption_status: str = "unknown"
    build_id: str = "unknown"
    product: str = "unknown"
    device_codename: str = "unknown"
    is_mtk: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


# --- Optional Historical Database Tables via SQLModel ---
if HAS_SQLMODEL:
    class DeviceRecord(SQLModel, table=True): # type: ignore
        __tablename__: str = "device_history"
        id: Optional[int] = Field(default=None, primary_key=True)
        serial: str = Field(index=True)
        vid: Optional[int] = None
        pid: Optional[int] = None
        mode: str = "unknown"
        first_seen: float = Field(default_factory=time.time)
        last_seen: float = Field(default_factory=time.time)
        detection_method: str = "SYSTEM"
else:
    class DeviceRecord: pass # Fallback stub


class DeviceManager:
    """Manages active processes, status polling, and database history for devices."""
    def __init__(self, db_url: Optional[str] = None) -> None:
        self.adb_path = shutil.which("adb") or "adb"
        self.fastboot_path = shutil.which("fastboot") or "fastboot"
        self.connected_devices: List[DeviceInfo] = []
        
        self._engine = None
        if db_url and HAS_SQLMODEL:
            try:
                self._engine = create_engine(db_url)
                SQLModel.metadata.create_all(self._engine)
            except Exception as e:
                logger.error(f"Failed establishing SQLite repository: {e}")

    def run_command(self, cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
        """Safely executes a shell subprocess with explicit timeouts."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout expired running command: {cmd}")
            return -99, "", "Timeout expired"
        except Exception as e:
            logger.error(f"Execution engine failure on: {cmd}. Error: {e}")
            return -1, "", str(e)

    def scan_devices(self) -> List[DeviceInfo]:
        """Performs a comprehensive logical scan of connected systems (ADB & Fastboot)."""
        scanned: List[DeviceInfo] = []
        
        # 1. Parse ADB endpoints
        rc, out, _ = self.run_command([self.adb_path, "devices"])
        if rc == 0:
            for line in out.strip().split("\n")[1:]:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial, state_str = parts[0], parts[1]
                    state = DeviceState.ADB
                    if state_str == "recovery":
                        state = DeviceState.RECOVERY
                    elif state_str == "unauthorized":
                        state = DeviceState.UNAUTHORIZED
                    elif state_str == "offline":
                        state = DeviceState.OFFLINE
                    
                    device = self._fetch_adb_details(serial, state)
                    scanned.append(device)
                    self._record_to_db(serial, mode=state.value)

        # 2. Parse Fastboot/Bootloader targets
        rc, out, _ = self.run_command([self.fastboot_path, "devices"])
        if rc == 0:
            for line in out.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial, state_str = parts[0], parts[1]
                    state = DeviceState.FASTBOOT if "fastboot" in state_str.lower() else DeviceState.BOOTLOADER
                    device = self._fetch_fastboot_details(serial, state)
                    scanned.append(device)
                    self._record_to_db(serial, mode=state.value)

        self.connected_devices = scanned
        return self.connected_devices

    def _fetch_adb_details(self, serial: str, state: DeviceState) -> DeviceInfo:
        device = DeviceInfo(serial=serial, state=state, connection_type="adb")
        if state not in (DeviceState.ADB, DeviceState.RECOVERY):
            return device

        props = [
            ("ro.product.brand", "brand"),
            ("ro.product.model", "model"),
            ("ro.product.manufacturer", "manufacturer"),
            ("ro.build.version.release", "android_version"),
            ("ro.build.version.sdk", "sdk_version"),
            ("ro.build.version.security_patch", "security_patch"),
            ("ro.security.frp.state", "frp_status"),
            ("ro.board.platform", "chipset"),
            ("ro.crypto.state", "encryption_status"),
            ("ro.build.id", "build_id"),
            ("ro.product.name", "product"),
            ("ro.product.device", "device_codename")
        ]

        # Execute a batched command sequence
        for prop, field_name in props:
            rc, stdout, _ = self.run_command([self.adb_path, "-s", serial, "shell", "getprop", prop], timeout=5)
            if rc == 0 and stdout:
                value = self._parse_getprop_output(stdout, prop)
                if value:
                    setattr(device, field_name, value)

        # Check for MTK chipsets
        if "mt" in device.chipset.lower() or "mediatek" in device.manufacturer.lower():
            device.is_mtk = True

        # Query root status
        rc, out, _ = self.run_command([self.adb_path, "-s", serial, "shell", "id"], timeout=5)
        if rc == 0 and "uid=0(root)" in out:
            device.root_status = "rooted"
        else:
            device.root_status = "unrooted"

        return device

    def _fetch_fastboot_details(self, serial: str, state: DeviceState) -> DeviceInfo:
        device = DeviceInfo(serial=serial, state=state, connection_type="fastboot")
        
        # Read standard fastboot variables
        rc, out, err = self.run_command([self.fastboot_path, "-s", serial, "getvar", "all"], timeout=5)
        raw_output = out + err
        
        variables = {
            r"product:\s*(.*)": "product",
            r"version-bootloader:\s*(.*)": "bootloader_version",
            r"unlocked:\s*(.*)": "bootloader_status",
            r"secure:\s*(.*)": "frp_status"
        }

        for regex, field_name in variables.items():
            match = re.search(regex, raw_output, re.IGNORECASE)
            if match:
                setattr(device, field_name, match.group(1).strip())

        # Clean bootloader status labels
        if device.bootloader_status.lower() in ("yes", "true"):
            device.bootloader_status = "unlocked"
        elif device.bootloader_status.lower() in ("no", "false"):
            device.bootloader_status = "locked"

        return device

    def reboot(self, serial: str, target: DeviceState, verify_timeout: int = 60) -> bool:
        """
        Triggers a device reboot, then monitors and verifies the state transition.
        """
        device = next((d for d in self.connected_devices if d.serial == serial), None)
        if not device:
            logger.error(f"Failed verification: Device with serial '{serial}' is not connected.")
            return False

        reboot_args = []
        if device.connection_type == "adb":
            reboot_args = [self.adb_path, "-s", serial, "reboot"]
        elif device.connection_type == "fastboot":
            reboot_args = [self.fastboot_path, "-s", serial, "reboot"]
        else:
            logger.error("Unsupported physical connection driver for reboot sequence")
            return False

        if target == DeviceState.BOOTLOADER:
            reboot_args.append("bootloader")
        elif target == DeviceState.RECOVERY:
            reboot_args.append("recovery")
        elif target == DeviceState.DOWNLOAD:
            reboot_args.append("download")

        logger.info(f"Issuing command string: {reboot_args}")
        rc, _, _ = self.run_command(reboot_args, timeout=15)
        if rc != 0:
            logger.error("Initial reboot instruction dispatch failed")
            return False

        # Transition validation monitor
        start_time = time.time()
        logger.info(f"Waiting for state transition to '{target.value}' (timeout: {verify_timeout}s)...")
        
        while time.time() - start_time < verify_timeout:
            time.sleep(2)
            self.scan_devices()
            current = next((d for d in self.connected_devices if d.serial == serial), None)
            
            if current:
                logger.debug(f"State transition poll: '{current.state.value}'")
                if target == DeviceState.UNKNOWN and current.state in (DeviceState.ADB, DeviceState.RECOVERY):
                    logger.info("Normal OS bootstrap confirmed")
                    return True
                if current.state == target:
                    logger.info("Device successfully achieved target recovery state")
                    return True

        logger.warning("Target state confirmation timed out")
        return False

    def _record_to_db(self, serial: str, mode: str) -> None:
        if not self._engine or not HAS_SQLMODEL:
            return
        try:
            with Session(self._engine) as session:
                existing = session.exec(
                    select(DeviceRecord).where(DeviceRecord.serial == serial)
                ).first()
                
                if existing:
                    existing.last_seen = time.time()
                    existing.mode = mode
                    session.add(existing)
                else:
                    record = DeviceRecord(serial=serial, mode=mode)
                    session.add(record)
                session.commit()
        except Exception as e:
            logger.debug(f"Database logging failure: {e}")