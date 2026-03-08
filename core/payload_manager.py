"""
Payload Manager — manages BROM exploit payloads for each chipset.

Context Flow:
  Chipset HW Code → PayloadManager.get(hw_code) →
    Cache Hit? → Return path
    Miss? → Download from URL → Verify size → Cache → Return path

Payloads are stored in ~/.mtkclient2/payloads/{chip_name}_payload.bin
"""
import os
import hashlib
import threading
from typing import Optional, Callable
from utils.logger import get_logger
from core.mtk_chipset_db import lookup, get_payload_url, is_v6

log = get_logger("payload_mgr")

PAYLOAD_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".mtkclient2", "payloads"
)


class PayloadManager:
    """
    Download, cache, and serve BROM payloads.
    Thread-safe via per-chip locks.
    """

    _instance: Optional["PayloadManager"] = None
    _lock = threading.Lock()

    def __init__(self, cache_dir: str = PAYLOAD_CACHE_DIR):
        self._cache_dir   = cache_dir
        self._chip_locks: dict[int, threading.Lock] = {}
        os.makedirs(self._cache_dir, exist_ok=True)

    @classmethod
    def instance(cls) -> "PayloadManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────
    def get_cached_path(self, hw_code: int) -> Optional[str]:
        """Return path to cached payload, or None if not downloaded."""
        path = self._payload_path(hw_code)
        return path if os.path.exists(path) and os.path.getsize(path) > 0 else None

    def download(self, hw_code: int,
                 on_progress: Optional[Callable[[int, int], None]] = None,
                 on_done: Optional[Callable[[bool, str], None]] = None) -> Optional[str]:
        """
        Download payload for hw_code if not already cached.
        Runs synchronously. Use download_async() for background use.
        Returns local path on success, None on failure.
        """
        chip = lookup(hw_code)
        url  = get_payload_url(hw_code)

        if not url:
            msg = f"No payload URL for HW code 0x{hw_code:04X}"
            log.warning(msg)
            if on_done:
                on_done(False, msg)
            return None

        cached = self.get_cached_path(hw_code)
        if cached:
            log.info(f"Payload cached: {cached}")
            if on_done:
                on_done(True, cached)
            return cached

        dest = self._payload_path(hw_code)
        log.info(f"Downloading payload: {url}")

        try:
            import urllib.request
            def _reporthook(count, block, total):
                if on_progress and total > 0:
                    on_progress(count * block, total)

            urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
            size = os.path.getsize(dest)
            log.info(f"Payload downloaded: {dest} ({size} bytes)")
            if on_done:
                on_done(True, dest)
            return dest

        except Exception as e:
            log.error(f"Payload download failed: {e}")
            # Clean up partial file
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception:
                    pass
            if on_done:
                on_done(False, str(e))
            return None

    def download_async(self, hw_code: int,
                       on_progress: Optional[Callable[[int, int], None]] = None,
                       on_done: Optional[Callable[[bool, str], None]] = None):
        """Download payload in a background thread."""
        t = threading.Thread(
            target=self.download,
            args=(hw_code, on_progress, on_done),
            daemon=True
        )
        t.start()

    def list_cached(self) -> list[dict]:
        """Return list of cached payloads with metadata."""
        result = []
        if not os.path.exists(self._cache_dir):
            return result
        for fname in sorted(os.listdir(self._cache_dir)):
            if not fname.endswith(".bin"):
                continue
            path = os.path.join(self._cache_dir, fname)
            size = os.path.getsize(path)
            result.append({"file": fname, "path": path, "size": size})
        return result

    def import_local(self, hw_code: int, src_path: str) -> bool:
        """Copy a user-provided payload .bin into the cache."""
        if not os.path.exists(src_path):
            log.error(f"Source payload not found: {src_path}")
            return False
        dest = self._payload_path(hw_code)
        try:
            import shutil
            shutil.copy2(src_path, dest)
            log.info(f"Payload imported: {dest}")
            return True
        except Exception as e:
            log.error(f"Import failed: {e}")
            return False

    def clear_cache(self):
        """Delete all cached payloads."""
        for item in self.list_cached():
            try:
                os.remove(item["path"])
            except Exception:
                pass
        log.info("Payload cache cleared.")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _payload_path(self, hw_code: int) -> str:
        chip = lookup(hw_code)
        name = chip.name if chip else f"mt{hw_code:04X}"
        fname = f"{name.lower()}_payload.bin"
        return os.path.join(self._cache_dir, fname)

    def status_for(self, hw_code: int) -> dict:
        """Return a status dict for UI display."""
        chip = lookup(hw_code)
        url  = get_payload_url(hw_code)
        cached = self.get_cached_path(hw_code)
        return {
            "hw_code":    hw_code,
            "chip_name":  chip.name if chip else f"Unknown (0x{hw_code:04X})",
            "has_url":    bool(url),
            "url":        url,
            "is_cached":  cached is not None,
            "cache_path": cached or "",
            "v6_protocol": is_v6(hw_code),
        }
