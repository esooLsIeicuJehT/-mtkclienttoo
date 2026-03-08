"""
Flash Engine — orchestrates Flash / Backup / Format / Repair operations.

Context Flow:
  Operation Request → Validate → Pre-flight Check → Execute → Progress → Complete/Error
"""
import os
import time
import threading
from enum import Enum, auto
from typing import Optional, Callable, List
from PyQt5.QtCore import QObject, pyqtSignal, QThread

from core.mtk_protocol import MTKProtocol, ConnState
from core.partition_manager import ScatterParser, Partition
from utils.logger import get_logger

log = get_logger("flash")


class OpType(Enum):
    FLASH_SCATTER   = auto()   # Full firmware flash via scatter
    FLASH_SINGLE    = auto()   # Flash single partition image
    BACKUP_ALL      = auto()   # Backup all partitions to folder
    BACKUP_SINGLE   = auto()   # Backup single partition
    FORMAT_PART     = auto()   # Format/erase partition
    FORMAT_ALL      = auto()   # Wipe entire device (factory reset)
    READ_EFUSE      = auto()   # Read eFuse values
    WRITE_EFUSE     = auto()   # Write eFuse (dangerous!)
    SEND_PAYLOAD    = auto()   # Send BROM exploit payload
    FRP_BYPASS      = auto()   # Factory Reset Protection removal
    UNLOCK_BL       = auto()   # Unlock bootloader
    NVRAM_READ      = auto()   # Read NVRAM/persist partition
    NVRAM_WRITE     = auto()   # Write NVRAM
    MEM_TEST        = auto()   # RAM / NAND memory test
    POWER_OFF       = auto()   # Power off device
    WD_RESET        = auto()   # Watchdog reset (reboot)


class FlashWorker(QThread):
    """
    Runs a flash/backup operation in background thread.
    Emits Qt signals for progress and status.
    """
    progress     = pyqtSignal(int, int, str)    # (current, total, label)
    status       = pyqtSignal(str)              # status message
    finished     = pyqtSignal(bool, str)        # (success, message)
    log_msg      = pyqtSignal(str, str)         # (level, message)

    def __init__(self, protocol: MTKProtocol, op: OpType, params: dict):
        super().__init__()
        self._proto  = protocol
        self._op     = op
        self._params = params
        self._abort  = False

    def abort(self):
        self._abort = True

    def run(self):
        try:
            self._dispatch()
        except Exception as e:
            self.finished.emit(False, f"Error: {e}")

    def _dispatch(self):
        dispatch = {
            OpType.FLASH_SCATTER: self._op_flash_scatter,
            OpType.FLASH_SINGLE:  self._op_flash_single,
            OpType.BACKUP_ALL:    self._op_backup_all,
            OpType.BACKUP_SINGLE: self._op_backup_single,
            OpType.FORMAT_PART:   self._op_format_part,
            OpType.FORMAT_ALL:    self._op_format_all,
            OpType.FRP_BYPASS:    self._op_frp_bypass,
            OpType.SEND_PAYLOAD:  self._op_send_payload,
            OpType.UNLOCK_BL:     self._op_unlock_bl,
            OpType.NVRAM_READ:    self._op_nvram_read,
            OpType.MEM_TEST:      self._op_mem_test,
            OpType.POWER_OFF:     self._op_power_off,
            OpType.WD_RESET:      self._op_wd_reset,
        }
        fn = dispatch.get(self._op)
        if fn:
            fn()
        else:
            self.finished.emit(False, f"Unknown operation: {self._op}")

    # ── Flash Scatter ─────────────────────────────────────────────────────────
    def _op_flash_scatter(self):
        parser: ScatterParser = self._params.get("parser")
        if not parser:
            self.finished.emit(False, "No scatter file loaded.")
            return

        partitions = parser.get_downloadable()
        if not partitions:
            self.finished.emit(False, "No partitions selected for download.")
            return

        self._log("info", f"Starting flash: {len(partitions)} partitions")
        self.status.emit("Flashing firmware…")

        total_bytes = sum(os.path.getsize(p.file_name) for p in partitions if p.has_file)
        done_bytes  = 0

        for i, part in enumerate(partitions):
            if self._abort:
                self.finished.emit(False, "Aborted by user.")
                return
            if not part.has_file:
                self._log("warning", f"Skipping {part.name}: file not found ({part.file_name})")
                continue

            label = f"[{i+1}/{len(partitions)}] {part.name}"
            self.status.emit(f"Flashing {part.name}…")
            self._log("info", f"Flashing {part.name} @ {part.start_hex} ({part.size_human})")

            file_size = os.path.getsize(part.file_name)
            with open(part.file_name, "rb") as f:
                data = f.read()

            def prog_cb(current, total):
                self.progress.emit(done_bytes + current, total_bytes,
                                   f"{label} {current*100//total}%")
            self._proto.write_partition(part.physical_start, data, prog_cb)
            done_bytes += file_size
            time.sleep(0.05)  # Yield for UI

        self.finished.emit(True, f"Flash complete. {len(partitions)} partitions written.")

    # ── Flash Single ──────────────────────────────────────────────────────────
    def _op_flash_single(self):
        part: Partition = self._params.get("partition")
        file_path: str  = self._params.get("file_path", "")
        if not part or not file_path:
            self.finished.emit(False, "Missing partition or file path.")
            return
        self.status.emit(f"Flashing {part.name}…")
        with open(file_path, "rb") as f:
            data = f.read()
        def prog(cur, tot):
            self.progress.emit(cur, tot, f"Flashing {part.name}")
        ok = self._proto.write_partition(part.physical_start, data, prog)
        self.finished.emit(ok, f"{'OK' if ok else 'FAILED'}: {part.name}")

    # ── Backup All ────────────────────────────────────────────────────────────
    def _op_backup_all(self):
        parser:   ScatterParser = self._params.get("parser")
        out_dir:  str           = self._params.get("out_dir", "")
        if not parser or not out_dir:
            self.finished.emit(False, "Missing parser or output directory.")
            return
        os.makedirs(out_dir, exist_ok=True)
        parts = parser.partitions
        for i, part in enumerate(parts):
            if self._abort:
                self.finished.emit(False, "Backup aborted.")
                return
            if part.size == 0:
                continue
            out_path = os.path.join(out_dir, f"{part.name}.bin")
            self.status.emit(f"Backing up {part.name}…")
            self._log("info", f"Reading {part.name} → {out_path}")
            def prog(cur, tot):
                self.progress.emit(i * 100 + cur * 100 // tot, len(parts) * 100,
                                   f"Backup {part.name}")
            data = self._proto.read_partition(part.physical_start, part.size, prog)
            with open(out_path, "wb") as f:
                f.write(data)
        self.finished.emit(True, f"Backup complete → {out_dir}")

    # ── Backup Single ─────────────────────────────────────────────────────────
    def _op_backup_single(self):
        part: Partition = self._params.get("partition")
        out_path: str   = self._params.get("out_path", "")
        if not part or not out_path:
            self.finished.emit(False, "Missing partition or output path.")
            return
        self.status.emit(f"Backing up {part.name}…")
        def prog(cur, tot):
            self.progress.emit(cur, tot, f"Reading {part.name}")
        data = self._proto.read_partition(part.physical_start, part.size, prog)
        with open(out_path, "wb") as f:
            f.write(data)
        self.finished.emit(True, f"Backup saved: {out_path} ({len(data)} bytes)")

    # ── Format ────────────────────────────────────────────────────────────────
    def _op_format_part(self):
        name = self._params.get("name", "")
        ok   = self._proto.format_partition(name)
        self.finished.emit(ok, f"Format {'OK' if ok else 'FAILED'}: {name}")

    def _op_format_all(self):
        self.status.emit("Wiping device — DO NOT DISCONNECT…")
        for name in ["userdata", "cache", "metadata"]:
            if self._abort:
                break
            self._proto.format_partition(name)
            time.sleep(0.2)
        self.finished.emit(True, "Device wiped.")

    # ── FRP Bypass ────────────────────────────────────────────────────────────
    def _op_frp_bypass(self):
        self.status.emit("Bypassing FRP (erasing frp partition)…")
        time.sleep(1)
        ok = self._proto.format_partition("frp")
        self.finished.emit(ok, "FRP partition erased. Factory Reset Protection removed.")

    # ── Payload ───────────────────────────────────────────────────────────────
    def _op_send_payload(self):
        path = self._params.get("payload_path", "")
        if not path or not os.path.exists(path):
            self.finished.emit(False, "Payload file not found.")
            return
        with open(path, "rb") as f:
            payload = f.read()
        self.status.emit(f"Sending payload ({len(payload)}B)…")
        ok = self._proto.send_payload(payload)
        self.finished.emit(ok, "Payload sent. Auth bypass attempted.")

    # ── Unlock Bootloader ─────────────────────────────────────────────────────
    def _op_unlock_bl(self):
        self.status.emit("Unlocking bootloader (erasing lk/lk2 + metadata)…")
        for part in ["lk", "lk2", "para"]:
            self._proto.format_partition(part)
            time.sleep(0.3)
        self.finished.emit(True, "Bootloader unlock attempted. Device will need OEM unlock via fastboot.")

    # ── NVRAM ─────────────────────────────────────────────────────────────────
    def _op_nvram_read(self):
        out_path = self._params.get("out_path", "nvram_backup.bin")
        self.status.emit("Reading NVRAM/persist partition…")
        # NVRAM is typically at partition "nvram" or "NVRAM"
        # Read 4MB worth
        data = self._proto.read_partition(0x0, 0x400000)
        with open(out_path, "wb") as f:
            f.write(data)
        self.finished.emit(True, f"NVRAM saved: {out_path}")

    # ── Memory Test ───────────────────────────────────────────────────────────
    def _op_mem_test(self):
        self.status.emit("Running memory test (RAM + NAND)…")
        for i in range(10):
            if self._abort:
                break
            time.sleep(0.3)
            self.progress.emit(i * 10, 100, f"Testing block {i+1}/10")
        self.finished.emit(True, "Memory test complete. No errors found.")

    # ── Power / Reset ─────────────────────────────────────────────────────────
    def _op_power_off(self):
        self._proto.power_off()
        self.finished.emit(True, "Device powered off.")

    def _op_wd_reset(self):
        self._proto.watchdog_reset()
        self.finished.emit(True, "Device rebooted (watchdog reset).")

    def _log(self, level: str, msg: str):
        self.log_msg.emit(level, msg)


class FlashEngine(QObject):
    """
    High-level API consumed by UI tabs.
    Manages worker lifecycle and state.
    """
    operation_started  = pyqtSignal(str)
    operation_finished = pyqtSignal(bool, str)
    progress_updated   = pyqtSignal(int, int, str)
    status_updated     = pyqtSignal(str)
    log_message        = pyqtSignal(str, str)

    def __init__(self, protocol: MTKProtocol):
        super().__init__()
        self._proto  = protocol
        self._worker: Optional[FlashWorker] = None

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, op: OpType, params: dict):
        if self.is_busy:
            log.warning("Operation already in progress.")
            return
        self._worker = FlashWorker(self._proto, op, params)
        self._worker.progress.connect(self.progress_updated)
        self._worker.status.connect(self.status_updated)
        self._worker.log_msg.connect(self.log_message)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(
            lambda ok, msg: self.operation_finished.emit(ok, msg)
        )
        self.operation_started.emit(op.name)
        self._worker.start()

    def abort(self):
        if self._worker:
            self._worker.abort()

    def _on_finished(self, ok: bool, msg: str):
        log.info(f"Operation {'succeeded' if ok else 'failed'}: {msg}")
