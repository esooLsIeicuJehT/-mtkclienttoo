"""
Fastboot flashing module for Android firmware operations.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from zipfile import ZipFile

from core.logger import Logger
from core.fastboot_interface import FastbootInterface
from core.safe_operations import SafeOperations


class FastbootFlash:
    """
    Fastboot-based firmware flashing operations.

    Supports flashing Android firmware images via fastboot protocol.
    Handles ZIP archives, individual image files, and device-specific flashing.
    """

    def __init__(self, device_info: Dict[str, Any], logger: Optional[Logger] = None):
        self.device_info = device_info
        self.logger = logger or Logger()
        self.fastboot = FastbootInterface(self.logger)
        self.serial = device_info.get('serial')
        self.firmware_path = device_info.get('firmware_path')
        self.safe_ops = SafeOperations(self.logger)

    def flash_firmware(self) -> bool:
        """
        Flash firmware to device using fastboot.

        Returns:
            True if flashing successful, False otherwise
        """
        if not self.firmware_path:
            self.logger.error("No firmware path specified")
            return False

        firmware_path = Path(self.firmware_path)
        if not firmware_path.exists():
            self.logger.error(f"Firmware file does not exist: {firmware_path}")
            return False

        self.logger.info(f"Starting firmware flash: {firmware_path}")

        try:
            # Extract firmware if it's a ZIP
            if firmware_path.suffix.lower() == '.zip':
                return self._flash_zip_firmware(firmware_path)
            else:
                return self._flash_image_file(firmware_path)

        except Exception as e:
            self.logger.error(f"Firmware flash failed: {e}")
            return False

    def _flash_zip_firmware(self, zip_path: Path) -> bool:
        """Extract and flash firmware from ZIP archive."""
        self.logger.info(f"Extracting firmware from: {zip_path}")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Look for common firmware files
                firmware_files = self._find_firmware_files(temp_dir)

                if not firmware_files:
                    self.logger.error("No valid firmware files found in ZIP")
                    return False

                # Flash each partition
                success = True
                for partition, image_path in firmware_files.items():
                    if not self.safe_ops.safe_flash(partition, image_path, True, self.device_info):
                        self.logger.error(f"Failed to flash {partition}")
                        success = False
                        break

                return success

            except Exception as e:
                self.logger.error(f"Failed to extract ZIP: {e}")
                return False

    def _flash_image_file(self, image_path: Path) -> bool:
        """Flash individual image file."""
        # Determine partition from filename
        partition = self._guess_partition(image_path.name)

        if not partition:
            self.logger.error(f"Could not determine partition for: {image_path.name}")
            return False

        self.logger.info(f"Flashing {partition} with {image_path}")
        return self.safe_ops.safe_flash(partition, str(image_path), True, self.device_info)

    def _find_firmware_files(self, directory: str) -> Dict[str, str]:
        """Find firmware files in extracted directory."""
        firmware_files = {}
        dir_path = Path(directory)

        # Common partition names and their file patterns
        partition_patterns = {
            'boot': ['boot.img', 'bootimage.img'],
            'recovery': ['recovery.img', 'recoveryimage.img'],
            'system': ['system.img', 'systemimage.img'],
            'vendor': ['vendor.img', 'vendorimage.img'],
            'vbmeta': ['vbmeta.img'],
            'dtbo': ['dtbo.img'],
            'super': ['super.img']
        }

        for partition, patterns in partition_patterns.items():
            for pattern in patterns:
                file_path = dir_path / pattern
                if file_path.exists():
                    firmware_files[partition] = str(file_path)
                    break

        return firmware_files

    def _guess_partition(self, filename: str) -> Optional[str]:
        """Guess partition name from filename."""
        filename_lower = filename.lower()

        if 'boot' in filename_lower:
            return 'boot'
        elif 'recovery' in filename_lower:
            return 'recovery'
        elif 'system' in filename_lower:
            return 'system'
        elif 'vendor' in filename_lower:
            return 'vendor'
        elif 'vbmeta' in filename_lower:
            return 'vbmeta'
        elif 'dtbo' in filename_lower:
            return 'dtbo'
        elif 'super' in filename_lower:
            return 'super'
        elif 'cache' in filename_lower:
            return 'cache'
        elif 'userdata' in filename_lower:
            return 'userdata'

        return None
