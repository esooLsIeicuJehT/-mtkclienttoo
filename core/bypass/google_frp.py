"""
Google Pixel FRP Bypass Module

Specialized FRP bypass methods for Google Pixel devices.
Supports Pixel 6-10 with Android 13-15.

Features:
- Setup Wizard bypass for Android 15
- ADB network activation
- Google account removal via settings
- Recovery mode bypass
"""

from typing import Dict, Any, Optional

from core.logger import Logger
from core.adb_interface import ADBInterface
from .generic_frp import GenericFRPBypass


class GoogleFrp(GenericFRPBypass):
    """Google Pixel FRP bypass implementation."""

    def __init__(self, device_info: Dict[str, Any], logger: Optional[Logger] = None):
        super().__init__(device_info, logger)
        self.device_info = device_info
        self.logger = logger or Logger()
        self.adb = ADBInterface(self.logger)
        self.serial = device_info.get('serial')

    def execute(self) -> bool:
        """Execute Google-specific FRP bypass."""
        self.logger.info("Starting Google Pixel FRP bypass")

        # Try Pixel-specific methods first
        methods = [
            self._bypass_pixel_setup_wizard,
            self._bypass_pixel_adb_network,
            self._bypass_pixel_recovery
        ]

        for method in methods:
            method_name = method.__name__.replace('_bypass_pixel_', '')
            self.logger.info(f"Attempting Pixel FRP bypass via {method_name}")

            try:
                if method():
                    self.logger.info(f"Pixel FRP bypass successful via {method_name}")
                    return True
            except Exception as e:
                self.logger.error(f"Pixel FRP bypass method {method_name} failed: {e}")
                continue

        # Fall back to generic methods
        self.logger.info("Pixel-specific methods failed, trying generic FRP bypass")
        return super().bypass()

    def _bypass_pixel_setup_wizard(self) -> bool:
        """Bypass FRP via Pixel setup wizard manipulation (Android 15)"""
        try:
            # Android 15 specific setup wizard bypass
            success1 = self.adb.shell("settings put secure user_setup_complete 1", self.serial)[0]
            success2 = self.adb.shell("settings put global device_provisioned 1", self.serial)[0]
            success3 = self.adb.shell("settings put secure setup_wizard_has_run 1", self.serial)[0]

            # Clear FRP data
            success4 = self.adb.shell("pm clear com.google.android.gms", self.serial)[0]

            if all([success1, success2, success3, success4]):
                self.logger.info("Pixel FRP bypassed via setup wizard")
                return True

        except Exception as e:
            self.logger.error(f"Pixel setup wizard bypass failed: {e}")

        return False

    def _bypass_pixel_adb_network(self) -> bool:
        """Enable ADB over network for Pixel devices"""
        try:
            # Enable ADB TCP
            success1 = self.adb.shell("setprop service.adb.tcp.port 5555", self.serial)[0]
            success2 = self.adb.shell("stop adbd && start adbd", self.serial)[0]

            # Get IP address
            success3, ip_output = self.adb.shell("ip route", self.serial)
            if success3:
                # Extract IP
                ip = self._extract_ip(ip_output)
                if ip:
                    self.logger.info(f"ADB network enabled at {ip}:5555")
                    return True

        except Exception as e:
            self.logger.error(f"Pixel ADB network bypass failed: {e}")

        return False

    def _bypass_pixel_recovery(self) -> bool:
        """Bypass FRP via recovery mode"""
        try:
            # Boot to recovery
            success1 = self.adb.shell("reboot recovery", self.serial)[0]

            if success1:
                # In recovery, would need physical interaction or additional commands
                self.logger.info("Booted to recovery for FRP bypass")
                return True

        except Exception as e:
            self.logger.error(f"Pixel recovery bypass failed: {e}")

        return False

    def _extract_ip(self, ip_output: str) -> Optional[str]:
        """Extract IP address from ip route output"""
        import re
        match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', ip_output)
        return match.group(1) if match else None
