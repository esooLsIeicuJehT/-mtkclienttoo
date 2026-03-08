"""
Scatter Generator — auto-generates MTK scatter files from live device data.

Context Flow:
  Device Connected (BROM/ADB) → Read Partition Table →
  Parse GPT/MTK Headers → Build Partition List → Emit Scatter File

Sources (in priority order):
  1. BROM: read raw GPT sectors via protocol
  2. ADB: /proc/partitions + /dev/block/by-name/ symlinks
  3. ADB: sgdisk --print /dev/block/mmcblk0 (if available)
  4. Manual: user provides partition size/offset info
"""
import os
import struct
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from utils.logger import get_logger

log = get_logger("scatter_gen")

# ── GPT constants ─────────────────────────────────────────────────────────────
GPT_HEADER_MAGIC  = b"EFI PART"
GPT_HEADER_OFFSET = 512        # LBA 1 (sector size 512)
GPT_ENTRY_SIZE    = 128
GPT_PART_NAME_OFF = 56         # offset of name inside entry (UTF-16LE)
GPT_PART_NAME_LEN = 72         # bytes (36 UTF-16LE chars)
SECTOR_SIZE       = 512

# ── Scatter format constants ──────────────────────────────────────────────────
SCATTER_VERSION   = "1.0"

# ── Well-known partition names MTK uses ──────────────────────────────────────
from core.mtk_chipset_db import STANDARD_PARTITIONS


@dataclass
class PartEntry:
    name:   str
    start:  int    # byte offset on storage
    size:   int    # bytes
    lba_start: int = 0
    lba_end:   int = 0
    file_name: str = ""   # associated .bin filename (if known)
    region:    int = 0    # MTK scatter region type

    @property
    def hex_start(self) -> str:
        return f"0x{self.start:016X}"

    @property
    def hex_size(self) -> str:
        return f"0x{self.size:08X}"

    def guess_filename(self) -> str:
        """Guess the standard MTK firmware filename for this partition."""
        mapping = {
            "preloader":   "preloader_{codename}.bin",
            "lk":          "lk.bin",
            "lk2":         "lk2.bin",
            "boot":        "boot.img",
            "recovery":    "recovery.img",
            "system":      "system.img",
            "vendor":      "vendor.img",
            "product":     "product.img",
            "odm":         "odm.img",
            "super":       "super.img",
            "logo":        "logo.bin",
            "tee1":        "tee.img",
            "tee2":        "tee.img",
            "spmfw":       "spmfw.img",
            "md1img":      "md1img.img",
            "md3img":      "md3img.img",
            "nvram":       "nvram.bin",
            "nvdata":      "nvdata.bin",
            "protect1":    "protect1.bin",
            "protect2":    "protect2.bin",
            "persist":     "persist.img",
            "frp":         "frp.img",
            "dtbo":        "dtbo.img",
            "vbmeta":      "vbmeta.img",
            "vbmeta_system": "vbmeta_system.img",
        }
        return mapping.get(self.name, f"{self.name}.bin")


class GPTParser:
    """Parse a GPT partition table from raw sector data."""

    @staticmethod
    def parse(data: bytes, sector_size: int = 512) -> Optional[List[PartEntry]]:
        """
        Parse GPT from raw bytes.
        data: must include at least the LBA0 (protective MBR) + LBA1 (GPT header)
              + enough LBAs for partition entries.
        Returns list of PartEntry or None if not a valid GPT.
        """
        # GPT header is at LBA1
        hdr_off = sector_size
        if len(data) < hdr_off + 92:
            return None

        magic = data[hdr_off:hdr_off + 8]
        if magic != GPT_HEADER_MAGIC:
            # Try without the MBR (data starts at LBA1)
            if data[:8] == GPT_HEADER_MAGIC:
                hdr_off = 0
            else:
                return None

        # GPT Header fields (all LE)
        # Offset 72: partition entry LBA (8 bytes)
        # Offset 80: num partition entries (4 bytes)
        # Offset 84: partition entry size (4 bytes)
        try:
            part_entry_lba = struct.unpack_from("<Q", data, hdr_off + 72)[0]
            num_parts      = struct.unpack_from("<I", data, hdr_off + 80)[0]
            entry_size     = struct.unpack_from("<I", data, hdr_off + 84)[0]
        except struct.error:
            return None

        if num_parts > 128 or entry_size < 128:
            return None

        entries_off = int(part_entry_lba) * sector_size
        parts = []
        for i in range(num_parts):
            off = entries_off + i * entry_size
            if off + entry_size > len(data):
                break
            entry = data[off:off + entry_size]

            # Skip empty entries (type GUID = all zeros)
            if entry[:16] == b'\x00' * 16:
                continue

            # LBA start/end
            try:
                lba_start = struct.unpack_from("<Q", entry, 32)[0]
                lba_end   = struct.unpack_from("<Q", entry, 40)[0]
            except struct.error:
                continue

            # Name: UTF-16LE at offset 56, 72 bytes = 36 chars
            raw_name = entry[56:56 + 72]
            try:
                name = raw_name.decode("utf-16-le").rstrip("\x00").strip()
            except Exception:
                name = f"part_{i}"

            if not name:
                continue

            byte_start = lba_start * sector_size
            byte_size  = (lba_end - lba_start + 1) * sector_size

            parts.append(PartEntry(
                name=name,
                start=byte_start,
                size=byte_size,
                lba_start=lba_start,
                lba_end=lba_end,
            ))

        return parts if parts else None


class ADBPartitionReader:
    """Read partition table from a connected ADB device."""

    def __init__(self, adb):
        self._adb = adb

    def read(self, serial: str = "") -> Optional[List[PartEntry]]:
        """
        Try multiple methods to get partition list via ADB.
        Returns list of PartEntry or None.
        """
        parts = self._try_proc_partitions(serial)
        if parts:
            log.info(f"ADB: got {len(parts)} partitions via /proc/partitions")
            return parts

        parts = self._try_sgdisk(serial)
        if parts:
            log.info(f"ADB: got {len(parts)} partitions via sgdisk")
            return parts

        parts = self._try_by_name_links(serial)
        if parts:
            log.info(f"ADB: got {len(parts)} partitions via by-name symlinks")
            return parts

        return None

    def _try_proc_partitions(self, serial: str) -> Optional[List[PartEntry]]:
        code, out = self._adb.shell(
            "cat /proc/partitions 2>/dev/null", serial
        )
        if code != 0 or not out:
            return None

        parts = []
        for line in out.splitlines():
            # Format: major minor #blocks name
            m = re.match(r'\s*\d+\s+\d+\s+(\d+)\s+(\w+)', line)
            if m:
                blocks = int(m.group(1))
                name   = m.group(2).strip()
                # Skip whole device entries (mmcblk0, sda etc.)
                if re.match(r'^(mmcblk|sd[a-z]|nvme)\d*$', name):
                    continue
                # blocks are in 1K units
                size = blocks * 1024
                parts.append(PartEntry(name=name, start=0, size=size))

        return self._enrich_with_offsets(parts, serial) if parts else None

    def _enrich_with_offsets(self, parts: List[PartEntry],
                              serial: str) -> List[PartEntry]:
        """Try to get actual byte offsets from sysfs."""
        enriched = []
        for p in parts:
            # Try sysfs: /sys/class/block/{name}/start  (in 512-byte sectors)
            code, start_str = self._adb.shell(
                f"cat /sys/class/block/{p.name}/start 2>/dev/null", serial
            )
            if code == 0 and start_str.strip().isdigit():
                p.start = int(start_str.strip()) * SECTOR_SIZE
            enriched.append(p)
        return enriched

    def _try_sgdisk(self, serial: str) -> Optional[List[PartEntry]]:
        code, out = self._adb.shell(
            "sgdisk --print /dev/block/mmcblk0 2>/dev/null || "
            "sgdisk --print /dev/block/sda 2>/dev/null", serial
        )
        if code != 0 or not out:
            return None

        parts = []
        # Line format: "   1  2048  34815  16384.0 KiB  0700  preloader"
        for line in out.splitlines():
            m = re.match(
                r'\s*\d+\s+(\d+)\s+(\d+)\s+[\d.]+\s+\w+\s+\w+\s+(\S+)', line
            )
            if m:
                lba_start = int(m.group(1))
                lba_end   = int(m.group(2))
                name      = m.group(3)
                parts.append(PartEntry(
                    name=name,
                    start=lba_start * SECTOR_SIZE,
                    size=(lba_end - lba_start + 1) * SECTOR_SIZE,
                    lba_start=lba_start, lba_end=lba_end,
                ))
        return parts if len(parts) > 3 else None

    def _try_by_name_links(self, serial: str) -> Optional[List[PartEntry]]:
        """List /dev/block/by-name/ to get partition names."""
        code, out = self._adb.shell(
            "ls -la /dev/block/by-name/ 2>/dev/null", serial
        )
        if code != 0 or not out:
            code, out = self._adb.shell(
                "ls -la /dev/block/bootdevice/by-name/ 2>/dev/null", serial
            )
        if code != 0 or not out:
            return None

        parts = []
        for line in out.splitlines():
            # lrwxrwxrwx ... name -> ../sda5
            m = re.search(r'(\S+)\s*->\s*\.\./(\S+)$', line)
            if m:
                name  = m.group(1)
                block = m.group(2)  # e.g. "sda5"
                # Try to get size from sysfs
                _, size_str = self._adb.shell(
                    f"cat /sys/class/block/{block}/size 2>/dev/null", serial
                )
                size = int(size_str.strip()) * SECTOR_SIZE if size_str.strip().isdigit() else 0
                _, start_str = self._adb.shell(
                    f"cat /sys/class/block/{block}/start 2>/dev/null", serial
                )
                start = int(start_str.strip()) * SECTOR_SIZE if start_str.strip().isdigit() else 0
                parts.append(PartEntry(name=name, start=start, size=size))

        return parts if len(parts) > 3 else None


class ScatterWriter:
    """Generates MTK scatter file text from a list of PartEntry."""

    @staticmethod
    def write(parts: List[PartEntry], storage_type: str = "HW_STORAGE_EMMC",
              codename: str = "device") -> str:
        """Generate a complete MTK scatter file string."""
        lines = [
            "############################################",
            f"MTK_SCATTER_FILE_VERSION = {SCATTER_VERSION}",
            "############################################",
            "",
            "[--FLASH_DEVICE_NO&ROM_INFO--]",
            "  [Name]: MAIN_STORAGE",
            f"  [Storage_Device]: {storage_type}",
            "",
            "[partition_list]",
        ]

        for idx, p in enumerate(parts):
            fname = p.file_name or p.guess_filename().replace("{codename}", codename)
            region = p.region or (0x2 if idx == 0 else 0x1)
            lines += [
                f"  [partition_index]: SYS{idx}",
                f"  [partition] = {p.name}",
                f"  [Filename] = {fname}",
                f"  [Partition_Size] = {p.hex_size}",
                f"  [start_address] = {p.hex_start}",
                f"  [Region] = 0x{region:X}",
                f"  [Partition_Needed_Block_For_DL] = 0xFFFFFFFF",
                "",
            ]

        lines += [
            "# End of scatter file",
            f"# Auto-generated by MTK Client 2.0",
            f"# Device codename: {codename}",
        ]

        return "\n".join(lines)


class ScatterGenerator:
    """
    High-level scatter file generator.
    Tries all available methods and returns the best result.
    """

    def __init__(self, adb=None, protocol=None):
        self._adb   = adb
        self._proto = protocol

    def generate_from_adb(self, serial: str = "", codename: str = "device",
                          storage_type: str = "HW_STORAGE_EMMC") -> Optional[str]:
        """
        Try to auto-generate scatter via ADB.
        Returns scatter file text or None.
        """
        if not self._adb or not self._adb.available:
            return None

        reader = ADBPartitionReader(self._adb)
        parts  = reader.read(serial)
        if not parts:
            return None

        return ScatterWriter.write(parts, storage_type, codename)

    def generate_from_gpt_bytes(self, gpt_data: bytes,
                                 codename: str = "device",
                                 storage_type: str = "HW_STORAGE_EMMC") -> Optional[str]:
        """
        Parse GPT from raw bytes (e.g. read from BROM protocol).
        Returns scatter file text or None.
        """
        parts = GPTParser.parse(gpt_data)
        if not parts:
            return None
        log.info(f"GPT parse: found {len(parts)} partitions")
        return ScatterWriter.write(parts, storage_type, codename)

    def generate_from_device(self, serial: str = "",
                              codename: str = "device") -> Tuple[Optional[str], str]:
        """
        Try all methods. Returns (scatter_text, method_used) or (None, error).
        """
        # Method 1: ADB
        text = self.generate_from_adb(serial, codename)
        if text:
            return text, "ADB (partition table)"

        # Method 2: If BROM protocol has raw read capability
        if self._proto and hasattr(self._proto, 'read_raw_sectors'):
            try:
                # Read first 2MB which contains GPT header + partition entries
                raw = self._proto.read_raw_sectors(0, count=4096)
                if raw:
                    text = self.generate_from_gpt_bytes(raw, codename)
                    if text:
                        return text, "BROM (GPT raw read)"
            except Exception as e:
                log.warning(f"BROM read failed: {e}")

        return None, "No connected device or partition table not readable"

    @staticmethod
    def save(scatter_text: str, path: str) -> bool:
        """Save scatter text to file."""
        try:
            with open(path, "w") as f:
                f.write(scatter_text)
            return True
        except Exception as e:
            log.error(f"Failed to save scatter: {e}")
            return False
