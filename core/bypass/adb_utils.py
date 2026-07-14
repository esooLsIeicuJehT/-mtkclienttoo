#!/usr/bin/env python3
"""
ADB Utilities - Enhanced ADB operations for device management
Provides application management, shell commands, and device information functions
"""

import subprocess
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class AppType(Enum):
    """Application type categories"""

    ALL = "all"
    SYSTEM = "system"
    THIRD_PARTY = "third_party"
    DISABLED = "disabled"
    ENABLED = "enabled"


@dataclass
class AppInfo:
    """Application information"""

    package_name: str
    app_type: AppType
    enabled: bool
    version_name: Optional[str] = None
    version_code: Optional[int] = None
    data_size: Optional[int] = None
    cache_size: Optional[int] = None


class ADBUtils:
    """Enhanced ADB utilities for device management"""

    def __init__(self, adb_path: str = "adb"):
        self.adb_path = adb_path

    def run_adb_command(
        self, args: List[str], timeout: int = 30
    ) -> Tuple[int, str, str]:
        """
        Execute ADB command

        Args:
            args: ADB command arguments
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = [self.adb_path]
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", "ADB not found"
        except Exception as e:
            return -1, "", f"Unexpected error: {str(e)}"

    def check_device_connection(self) -> bool:
        """
        Check if a device is connected via ADB

        Returns:
            True if device is connected and authorized
        """
        ret, out, _ = self.run_adb_command(["get-state"])
        return ret == 0 and "device" in out

    def get_connected_devices(self) -> List[str]:
        """
        Get list of connected devices

        Returns:
            List of device serial numbers
        """
        ret, out, _ = self.run_adb_command(["devices"])
        if ret != 0:
            return []

        devices = []
        lines = out.strip().split("\n")[1:]  # Skip header
        for line in lines:
            if line.strip() and "\tdevice" in line:
                device_id = line.split("\t")[0]
                devices.append(device_id)

        return devices

    def execute_shell_command(
        self, command: str, timeout: int = 30
    ) -> Tuple[int, str, str]:
        """
        Execute custom ADB shell command

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        return self.run_adb_command(["shell", command], timeout)

    def get_device_properties(self) -> Dict[str, str]:
        """
        Get device properties via getprop

        Returns:
            Dictionary of device properties
        """
        ret, out, _ = self.run_adb_command(["shell", "getprop"])
        if ret != 0:
            return {}

        props = {}
        for line in out.split("\n"):
            if "[" in line and "]" in line:
                # Format: [property]: [value]
                match = re.match(r"\[(.+)\]: \[(.*)\]", line)
                if match:
                    key, value = match.groups()
                    props[key] = value

        return props

    def get_device_model(self) -> str:
        """Get device model"""
        props = self.get_device_properties()
        return props.get("ro.product.model", "Unknown")

    def get_device_brand(self) -> str:
        """Get device brand"""
        props = self.get_device_properties()
        return props.get("ro.product.brand", "Unknown")

    def get_android_version(self) -> str:
        """Get Android version"""
        props = self.get_device_properties()
        return props.get("ro.build.version.release", "Unknown")

    def get_security_patch(self) -> str:
        """Get security patch level"""
        props = self.get_device_properties()
        return props.get("ro.build.version.security_patch", "Unknown")

    def list_applications(self, app_type: AppType = AppType.ALL) -> List[AppInfo]:
        """
        List installed applications

        Args:
            app_type: Type of applications to list

        Returns:
            List of AppInfo objects
        """
        # Determine which pm list command to use
        if app_type == AppType.SYSTEM:
            cmd = ["shell", "pm", "list", "packages", "-s"]
        elif app_type == AppType.THIRD_PARTY:
            cmd = ["shell", "pm", "list", "packages", "-3"]
        elif app_type == AppType.DISABLED:
            cmd = ["shell", "pm", "list", "packages", "-d"]
        elif app_type == AppType.ENABLED:
            cmd = ["shell", "pm", "list", "packages", "-e"]
        else:  # ALL
            cmd = ["shell", "pm", "list", "packages"]

        ret, out, _ = self.run_adb_command(cmd)
        if ret != 0:
            return []

        apps = []
        for line in out.strip().split("\n"):
            if line.startswith("package:"):
                package_name = line.split(":", 1)[1].strip()

                # Get additional app info
                enabled = self._is_app_enabled(package_name)
                app_type_detected = self._get_app_type(package_name)

                app_info = AppInfo(
                    package_name=package_name,
                    app_type=app_type_detected,
                    enabled=enabled,
                )
                apps.append(app_info)

        return apps

    def _is_app_enabled(self, package_name: str) -> bool:
        """Check if an application is enabled"""
        ret, out, _ = self.run_adb_command(["shell", "pm", "list", "packages", "-e"])
        if ret == 0:
            enabled_packages = [
                line.split(":", 1)[1].strip()
                for line in out.split("\n")
                if line.startswith("package:")
            ]
            return package_name in enabled_packages
        return False

    def _get_app_type(self, package_name: str) -> AppType:
        """Determine if app is system or third-party"""
        ret, out, _ = self.run_adb_command(["shell", "pm", "list", "packages", "-s"])
        if ret == 0:
            system_packages = [
                line.split(":", 1)[1].strip()
                for line in out.split("\n")
                if line.startswith("package:")
            ]
            if package_name in system_packages:
                return AppType.SYSTEM

        return AppType.THIRD_PARTY

    def clear_app_data(self, package_name: str) -> Tuple[bool, str]:
        """
        Clear application data

        Args:
            package_name: Application package name

        Returns:
            Tuple of (success, message)
        """
        ret, out, err = self.run_adb_command(["shell", "pm", "clear", package_name])

        if ret == 0:
            return True, f"Cleared data for {package_name}"
        else:
            return False, f"Failed to clear data for {package_name}: {err}"

    def uninstall_app(
        self, package_name: str, keep_data: bool = False
    ) -> Tuple[bool, str]:
        """
        Uninstall an application

        Args:
            package_name: Application package name
            keep_data: Whether to keep app data and cache

        Returns:
            Tuple of (success, message)
        """
        args = ["shell", "pm", "uninstall"]
        if keep_data:
            args.append("-k")
        args.extend(["--user", "0", package_name])

        ret, out, err = self.run_adb_command(args)

        if ret == 0:
            return True, f"Uninstalled {package_name}"
        else:
            return False, f"Failed to uninstall {package_name}: {err}"

    def disable_app(self, package_name: str) -> Tuple[bool, str]:
        """
        Disable an application

        Args:
            package_name: Application package name

        Returns:
            Tuple of (success, message)
        """
        ret, out, err = self.run_adb_command(
            ["shell", "pm", "disable-user", "--user", "0", package_name]
        )

        if ret == 0:
            return True, f"Disabled {package_name}"
        else:
            return False, f"Failed to disable {package_name}: {err}"

    def enable_app(self, package_name: str) -> Tuple[bool, str]:
        """
        Enable an application

        Args:
            package_name: Application package name

        Returns:
            Tuple of (success, message)
        """
        ret, out, err = self.run_adb_command(
            ["shell", "pm", "enable", "--user", "0", package_name]
        )

        if ret == 0:
            return True, f"Enabled {package_name}"
        else:
            return False, f"Failed to enable {package_name}: {err}"

    def backup_apk(self, package_name: str, backup_path: str) -> Tuple[bool, str]:
        """
        Backup application APK

        Args:
            package_name: Application package name
            backup_path: Path to save the APK backup

        Returns:
            Tuple of (success, message)
        """
        # Get APK path
        ret, out, _ = self.run_adb_command(["shell", "pm", "path", package_name])

        if ret != 0:
            return False, f"Could not find APK for {package_name}"

        apk_path = out.strip().split("\n")[0].replace("package:", "")
        if not apk_path:
            return False, f"Could not determine APK path for {package_name}"

        # Pull the APK
        ret, out, err = self.run_adb_command(["pull", apk_path, backup_path])

        if ret == 0:
            return True, f"Backed up APK for {package_name} to {backup_path}"
        else:
            return False, f"Failed to backup APK for {package_name}: {err}"

    def enable_wireless_adb(self, port: int = 5555) -> Tuple[bool, str]:
        """
        Enable wireless ADB on the device

        Args:
            port: Port to use for wireless ADB

        Returns:
            Tuple of (success, message)
        """
        # Set TCP/IP mode
        ret1, out1, err1 = self.run_adb_command(["tcpip", str(port)])

        if ret1 != 0:
            return False, f"Failed to enable TCP/IP mode: {err1}"

        # Get device IP address
        ret2, out2, _ = self.run_adb_command(["shell", "ip", "addr", "show", "wlan0"])

        ip_address = None
        if ret2 == 0:
            # Extract IP address from output
            for line in out2.split("\n"):
                if "inet " in line and "127.0.0.1" not in line:
                    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        ip_address = match.group(1)
                        break

        if not ip_address:
            # Try alternative method
            ret2, out2, _ = self.run_adb_command(["shell", "getprop", "net.ip4"])
            # This is simplified - in practice would need better IP detection

        if ip_address:
            return (
                True,
                f"Wireless ADB enabled. Connect with: adb connect {ip_address}:{port}",
            )
        else:
            return (
                True,
                f"TCP/IP mode set on port {port}. Get device IP and connect manually.",
            )

    def disable_wireless_adb(self) -> Tuple[bool, str]:
        """
        Disable wireless ADB and return to USB mode

        Returns:
            Tuple of (success, message)
        """
        ret, out, err = self.run_adb_command(["usb"])

        if ret == 0:
            return True, "Wireless ADB disabled, returned to USB mode"
        else:
            return False, f"Failed to disable wireless ADB: {err}"


# Global instance for easy access
adb_utils = ADBUtils()
