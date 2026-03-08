"""
Partition Manager — Scatter file parser + partition table management.

Context Flow:
  Scatter File → Parse → Partition Map → Operation Dispatch → Progress Report
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from utils.logger import get_logger

log = get_logger("partition")


@dataclass
class Partition:
    name:        str   = ""
    linear_start: int  = 0
    physical_start: int = 0
    size:        int   = 0
    file_name:   str   = ""
    is_download: bool  = False
    partition_idx: int = 0
    type:        str   = "EXT4_IMG"
    fs_type:     str   = ""
    is_selected: bool  = True
    region:      str   = "EMMC_USER"

    @property
    def size_human(self) -> str:
        return _human_size(self.size)

    @property
    def start_hex(self) -> str:
        return hex(self.physical_start)

    @property
    def has_file(self) -> bool:
        return bool(self.file_name) and os.path.exists(self.file_name)


def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class ScatterParser:
    """
    Parses MTK scatter files (.txt format used by SP Flash Tool / mtkclient).
    Handles both old-style and new-style scatter formats.
    """
    def __init__(self):
        self.partitions: List[Partition] = []
        self.platform:   str = ""
        self.version:    str = ""
        self.source_file: str = ""

    def load(self, path: str) -> bool:
        self.source_file = path
        self.partitions.clear()
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read()
            # Detect format
            if "partition_index" in content or "linear_start_addr" in content:
                return self._parse_new_format(content)
            else:
                return self._parse_legacy_format(content)
        except Exception as e:
            log.error(f"Scatter parse error: {e}")
            return False

    # ── New-Style Parser ──────────────────────────────────────────────────────
    def _parse_new_format(self, content: str) -> bool:
        """Parse modern scatter format (MT67xx, MT68xx)."""
        blocks = re.split(r'\n(?=\s*\{)', content)
        # Extract header
        hdr_match = re.search(r'platform:\s*(\S+)', content)
        if hdr_match:
            self.platform = hdr_match.group(1)
        ver_match = re.search(r'version:\s*(\S+)', content)
        if ver_match:
            self.version = ver_match.group(1)

        for block in blocks:
            p = self._parse_block(block)
            if p:
                self.partitions.append(p)
        log.info(f"Loaded {len(self.partitions)} partitions from scatter ({self.platform})")
        return len(self.partitions) > 0

    def _parse_block(self, block: str) -> Optional[Partition]:
        def grab(key: str, default="") -> str:
            m = re.search(rf'{key}\s*:\s*(\S+)', block)
            return m.group(1) if m else default

        name = grab("partition_name")
        if not name or name == "{}":
            return None

        p = Partition()
        p.name             = name.strip('"').strip("'")
        p.type             = grab("type", "EXT4_IMG")
        p.linear_start     = int(grab("linear_start_addr", "0x0"), 16)
        p.physical_start   = int(grab("physical_start_addr", "0x0"), 16)
        p.size             = int(grab("partition_size", "0x0"), 16)
        p.file_name        = grab("file_name", "")
        p.is_download      = grab("is_download", "false").lower() == "true"
        idx_str            = grab("partition_index", "SYS_NO_EXIST")
        p.partition_idx    = int(idx_str) if idx_str.isdigit() else 0
        p.region           = grab("region", "EMMC_USER")
        p.fs_type          = grab("fs_type", "")
        return p

    # ── Legacy Parser ─────────────────────────────────────────────────────────
    def _parse_legacy_format(self, content: str) -> bool:
        """Parse old-style scatter format (MT65xx)."""
        lines = content.splitlines()
        current = None
        for line in lines:
            line = line.strip()
            if line.startswith("partition_name"):
                if current:
                    self.partitions.append(current)
                current = Partition()
                current.name = line.split()[-1].strip('"')
            elif current is None:
                continue
            elif line.startswith("start_addr"):
                val = line.split()[-1]
                current.physical_start = int(val, 16)
                current.linear_start   = current.physical_start
            elif line.startswith("partition_size"):
                val = line.split()[-1]
                current.size = int(val, 16)
            elif line.startswith("file_name"):
                current.file_name = line.split()[-1].strip('"')
            elif line.startswith("is_download"):
                current.is_download = line.split()[-1].lower() == "true"
        if current:
            self.partitions.append(current)
        log.info(f"Loaded {len(self.partitions)} partitions (legacy format)")
        return len(self.partitions) > 0

    # ── Queries ───────────────────────────────────────────────────────────────
    def get_partition(self, name: str) -> Optional[Partition]:
        return next((p for p in self.partitions if p.name == name), None)

    def get_downloadable(self) -> List[Partition]:
        return [p for p in self.partitions if p.is_download and p.is_selected]

    def get_all_names(self) -> List[str]:
        return [p.name for p in self.partitions]

    def select_all(self, selected: bool = True):
        for p in self.partitions:
            p.is_selected = selected

    def select_by_name(self, name: str, selected: bool = True):
        p = self.get_partition(name)
        if p:
            p.is_selected = selected

    def resolve_file_paths(self, base_dir: str):
        """Resolve relative file paths relative to scatter file's directory."""
        for p in self.partitions:
            if p.file_name and not os.path.isabs(p.file_name):
                candidate = os.path.join(base_dir, p.file_name)
                if os.path.exists(candidate):
                    p.file_name = candidate

    @property
    def total_flash_size(self) -> int:
        return sum(p.size for p in self.partitions if p.size > 0)

    @property
    def summary(self) -> str:
        lines = [
            f"Platform : {self.platform or 'Unknown'}",
            f"Version  : {self.version or 'Unknown'}",
            f"Partitions: {len(self.partitions)}",
            f"Total Size: {_human_size(self.total_flash_size)}",
        ]
        return "\n".join(lines)
