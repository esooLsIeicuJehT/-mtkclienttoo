#!/usr/bin/env python3
"""
MDM Guard Module - Mobile Device Management Bypass
Implements methods to remove MDM profiles and restrictions

Based on reverse engineering analysis of MultiUnlock_Setup.exe
and industry-standard MDM removal techniques.

MDM types supported:
- Samsung Knox
- Android Enterprise
- iOS MDM Profiles
- Work Profiles
"""

import subprocess
import time
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

class MDMMethod(Enum):
    """Available MDM bypass methods"""
    ADB_REMOVE_MDM = "adb_remove_mdm"
    ADB_REMOVE_WORK_PROFILE = "adb_work_profile"
    ADB_DEVICE_OWNER = "adb_device_owner"
    FASTBOOT_WIPE = "fastboot_wipe"
    IOS_PROFILE_REMOVAL = "ios_profile"
    MANUAL_INSTRUCTIONS = "manual"

@dataclass
class MDMResult:
    """Result of MDM bypass attempt"""
    success: bool
    method: MDMMethod
    message: str
    details: Optional[str] = None
    requires_manual: bool = False

class MDMGuard:
    """
    MDM (Mobile Device Management) Bypass Implementation
    
    Supports removal of:
    - Samsung Knox
    - Android Enterprise/Work Profiles
    - Device Owner apps
    - iOS MDM Profiles
    """
    
    # Common MDM apps
    MDM_APPS = [
        'com.samsung.android.knox.containeragent',
        'com.samsung.android.knox.containercore',
        'com.samsung.klmsagent',
        'com.samsung.android.app.mcms',
        'com.android.managedprovisioning',
        'com.android.providers.downloads.ui',
        'com.microsoft.windowsintune.companyportal',
        'com.airwatch.androidagent',
        'com.mobileiron',
        'com.vmware.workspace',
        'com.ibm.mam.admin',
        'com.sap.mobile.secure.store',
        'com.blackberry.ume.client',
        'com.soti.mobicontrol',
        'com.zebra.mdagent',
    ]
    
    # Device admin receiver classes
    DEVICE_ADMIN_APPS = [
        'com.samsung.android.knox.containercore/KnoxContainerAdminReceiver',
        'com.airwatch.androidagent/AirWatchAdminReceiver',
        'com.mobileiron/android.enterprise.AdminReceiver',
    ]
    
    def __init__(self, adb_path: str = 'adb', fastboot_path: str = 'fastboot'):
        self.adb_path = adb_path
        self.fastboot_path = fastboot_path
        self.device_serial: Optional[str] = None
    
    def run_adb(self, args: List[str], timeout: int = 30) -> Tuple[int, str, str]:
        """Execute ADB command"""
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        cmd.extend(args)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, '', 'Command timed out'
        except FileNotFoundError:
            return -1, '', 'ADB not found'
    
    def run_fastboot(self, args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
        """Execute Fastboot command"""
        cmd = [self.fastboot_path]
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        cmd.extend(args)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, '', 'Command timed out'
        except FileNotFoundError:
            return -1, '', 'Fastboot not found'
    
    def check_mdm_status(self) -> dict:
        """Check if device has MDM installed"""
        mdm_found = []
        
        # Check for installed MDM apps
        ret, out, _ = self.run_adb(['shell', 'pm', 'list', 'packages'])
        if ret == 0:
            for app in self.MDM_APPS:
                if app in out:
                    mdm_found.append(app)
        
        # Check for device owner
        ret, out, _ = self.run_adb(['shell', 'dpm', 'list-owners'])
        device_owner = out.strip() if ret == 0 else None
        
        return {
            'mdm_apps': mdm_found,
            'device_owner': device_owner,
            'has_mdm': len(mdm_found) > 0 or device_owner is not None
        }
    
    def bypass_adb_remove_mdm(self) -> MDMResult:
        """
        Method 1: Remove MDM apps via ADB
        
        Works on rooted devices or devices with ADB access.
        Removes MDM applications and their data.
        """
        commands = []
        
        # Build uninstall commands for MDM apps
        for app in self.MDM_APPS:
            commands.append(['shell', 'pm', 'uninstall', '-k', '--user', '0', app])
            commands.append(['shell', 'pm', 'disable-user', '--user', '0', app])
        
        # Remove Knox components
        knox_commands = [
            ['shell', 'rm', '-rf', '/data/system/users/0/knox'],
            ['shell', 'rm', '-rf', '/data/system/knox'],
            ['shell', 'rm', '-rf', '/data/data/com.samsung.android.knox.containercore'],
            ['shell', 'rm', '-rf', '/data/data/com.samsung.klmsagent'],
        ]
        commands.extend(knox_commands)
        
        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))
        
        success_count = sum(1 for _, success in results if success)
        
        # Always reboot after attempt
        self.run_adb(['reboot'])
        
        if success_count > 0:
            return MDMResult(
                success=True,
                method=MDMMethod.ADB_REMOVE_MDM,
                message=f"MDM removal completed. {success_count}/{len(commands)} commands executed.",
                details="Device is rebooting. MDM should be removed after restart."
            )
        
        return MDMResult(
            success=False,
            method=MDMMethod.ADB_REMOVE_MDM,
            message="Failed to remove MDM. Root access may be required.",
            details="Device is rebooting. Check if MDM was removed after restart."
        )
    
    def bypass_adb_remove_work_profile(self) -> MDMResult:
        """
        Method 2: Remove Work Profile via ADB
        
        Removes Android work profile that may be managed by MDM.
        """
        commands = [
            # Remove work profile
            ['shell', 'pm', 'remove-user', '10'],  # Work profile is usually user 10
            
            # Disable managed provisioning
            ['shell', 'pm', 'disable-user', 'com.android.managedprovisioning'],
            
            # Remove profile owner
            ['shell', 'dpm', 'remove-active-admin', 'com.android.managedprovisioning/.DeviceAdminReceiver'],
            
            # Clear managed provisioning data
            ['shell', 'pm', 'clear', 'com.android.managedprovisioning'],
            
            # Remove work profile data
            ['shell', 'rm', '-rf', '/data/user/10'],
            ['shell', 'rm', '-rf', '/data/system/users/10'],
        ]
        
        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))
        
        success_count = sum(1 for _, success in results if success)
        
        # Always reboot after attempt
        self.run_adb(['reboot'])
        
        if success_count > 0:
            return MDMResult(
                success=True,
                method=MDMMethod.ADB_REMOVE_WORK_PROFILE,
                message=f"Work profile removal completed. {success_count}/{len(commands)} commands executed.",
                details="Device is rebooting. Work profile should be removed."
            )
        
        return MDMResult(
            success=False,
            method=MDMMethod.ADB_REMOVE_WORK_PROFILE,
            message="Failed to remove work profile.",
            details="Device is rebooting. Check if work profile was removed."
        )
    
    def bypass_adb_device_owner(self) -> MDMResult:
        """
        Method 3: Remove Device Owner via ADB
        
        Removes device owner app which may be controlling MDM.
        """
        # First, get current device owner
        ret, out, _ = self.run_adb(['shell', 'dpm', 'list-owners'])
        
        device_owners = []
        if ret == 0 and out.strip():
            device_owners = [line.strip() for line in out.strip().split('\n') if line.strip()]
        
        if not device_owners:
            return MDMResult(
                success=False,
                method=MDMMethod.ADB_DEVICE_OWNER,
                message="No device owner found.",
                details="Device appears to not have a device owner set."
            )
        
        commands = []
        for owner in device_owners:
            # Remove device owner
            commands.append(['shell', 'dpm', 'remove-active-admin', owner])
            
            # Try to get package name from owner
            if '/' in owner:
                pkg = owner.split('/')[0]
                commands.append(['shell', 'pm', 'clear', pkg])
                commands.append(['shell', 'pm', 'disable-user', pkg])
        
        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))
        
        success_count = sum(1 for _, success in results if success)
        
        # Always reboot
        self.run_adb(['reboot'])
        
        return MDMResult(
            success=True,
            method=MDMMethod.ADB_DEVICE_OWNER,
            message=f"Device owner removal attempted. {success_count}/{len(commands)} commands executed.",
            details="Device is rebooting. Device owner should be removed."
        )
    
    def bypass_fastboot_wipe(self) -> MDMResult:
        """
        Method 4: Wipe MDM via Fastboot
        
        Factory reset via fastboot to remove MDM.
        WARNING: This will erase all data!
        """
        # Check if in fastboot mode
        ret, out, _ = self.run_fastboot(['getvar', 'product'])
        
        if ret != 0:
            return MDMResult(
                success=False,
                method=MDMMethod.FASTBOOT_WIPE,
                message="Device not in fastboot mode.",
                details="Boot device to fastboot mode and try again."
            )
        
        # Try wipe commands
        wipe_commands = [
            ['erase', 'userdata'],
            ['erase', 'cache'],
            ['oem', 'wipe_data'],
            ['flashing', 'unlock'],
        ]
        
        for cmd in wipe_commands:
            ret, out, err = self.run_fastboot(cmd)
            if ret == 0 or 'success' in out.lower() or 'success' in err.lower():
                self.run_fastboot(['reboot'])
                return MDMResult(
                    success=True,
                    method=MDMMethod.FASTBOOT_WIPE,
                    message=f"Device wiped via fastboot {cmd[0]}",
                    details="All data erased. MDM removed."
                )
        
        return MDMResult(
            success=False,
            method=MDMMethod.FASTBOOT_WIPE,
            message="Fastboot wipe commands not supported on this device."
        )
    
    def bypass_ios_profile_removal(self) -> MDMResult:
        """
        Method 5: iOS MDM Profile Removal Instructions
        
        Provides instructions for removing MDM from iOS devices.
        """
        instructions = """
iOS MDM Profile Removal Guide:

Method 1: Settings Removal (If Allowed by MDM)
1. Go to Settings > General > VPN & Device Management
2. Tap on the MDM profile
3. Tap "Remove Management"
4. Enter device passcode if prompted
5. Confirm removal

Method 2: Factory Reset
1. Go to Settings > General > Transfer or Reset iPhone
2. Tap "Erase All Content and Settings"
3. Enter passcode and confirm
4. Device will restart without MDM

Method 3: iTunes/Finder Restore
1. Connect iPhone to computer
2. Open iTunes (Windows/older Mac) or Finder (newer Mac)
3. Put device in Recovery Mode:
   - iPhone 8 and newer: Press Volume Up, Volume Down, then hold Side button
   - iPhone 7/7 Plus: Hold Volume Down and Side button together
   - Older iPhones: Hold Home and Power button together
4. Click "Restore" when prompted
5. Wait for restore to complete

Method 4: Apple Business Manager Removal
If device is supervised:
1. Contact your IT administrator
2. They can remove MDM from Apple Business Manager
3. Device will be released from supervision

Method 5: Activation Lock Bypass (Requires Original Owner)
1. Contact original owner
2. Ask them to remove device from their iCloud account
3. Go to iCloud.com/find and remove device

⚠️ IMPORTANT NOTES:
- Supervised devices have limited removal options
- Some MDM profiles are non-removable
- Factory reset may not remove supervision
- Check if device is iCloud locked before purchasing

WARNING: Do not use unauthorized MDM bypass tools as they may:
- Void warranty
- Violate terms of service
- Contain malware
- Be illegal in some jurisdictions
"""
        
        return MDMResult(
            success=True,
            method=MDMMethod.IOS_PROFILE_REMOVAL,
            message="iOS MDM removal instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def get_manual_instructions(self) -> MDMResult:
        """
        Method 6: Manual MDM Bypass Instructions
        
        Provides comprehensive manual bypass instructions.
        """
        instructions = """
Complete MDM Bypass Guide:

=== ANDROID MDM BYPASS ===

Method 1: Knox Uninstall (Samsung)
Requirements: Root access or ADB enabled
1. Enable USB Debugging
2. Connect to PC with ADB
3. Run: adb shell pm uninstall -k --user 0 com.samsung.android.knox.containercore
4. Run: adb shell pm uninstall -k --user 0 com.samsung.klmsagent
5. Reboot device

Method 2: Device Owner Removal
1. Find device owner: adb shell dpm list-owners
2. Remove owner: adb shell dpm remove-active-admin <package>/<receiver>
3. Reboot device

Method 3: Work Profile Removal
1. Go to Settings > Accounts
2. Remove work profile
3. Or use: adb shell pm remove-user 10

Method 4: Factory Reset
1. Boot to recovery mode (Power + Volume Up)
2. Select "Wipe data/factory reset"
3. Confirm and reboot

Method 5: Enterprise Reset
1. Go to Settings > System > Reset options
2. Select "Erase all data (factory reset)"
3. This removes MDM but may trigger FRP

=== iOS MDM BYPASS ===

Method 1: Profile Removal
1. Settings > General > VPN & Device Management
2. Select MDM profile
3. Tap "Remove Management"

Method 2: Supervised Device Removal
1. Requires Apple Configurator 2
2. Connect to Mac with Configurator
3. Select device > Actions > Prepare
4. Choose "Don't enroll in MDM"

=== UNIVERSAL METHODS ===

Method 1: Enterprise WiFi Bypass
1. Forget all WiFi networks
2. Connect to new WiFi during setup
3. Some MDM cannot re-enroll without known WiFi

Method 2: Date/Time Trick
1. Set device date to past (before MDM enrollment)
2. Some MDM profiles may expire or fail to check in
3. Remove MDM while offline

Method 3: VPN Interference
1. Use a VPN to block MDM server connections
2. Attempt to remove MDM while blocked

⚠️ WARNING: These methods may not work on all devices.
MDM implementations vary by vendor and configuration.
"""
        
        return MDMResult(
            success=True,
            method=MDMMethod.MANUAL_INSTRUCTIONS,
            message="Manual MDM bypass instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def auto_bypass(self) -> MDMResult:
        """Automatically attempt MDM bypass using the best available method"""
        # Check device state
        ret, _, _ = self.run_adb(['get-state'])
        
        if ret == 0:
            # Device in ADB mode - try ADB methods
            result = self.bypass_adb_device_owner()
            if result.success:
                return result
            
            result = self.bypass_adb_remove_mdm()
            if result.success:
                return result
            
            return self.bypass_adb_remove_work_profile()
        
        # Check fastboot
        ret, _, _ = self.run_fastboot(['getvar', 'product'])
        if ret == 0:
            return self.bypass_fastboot_wipe()
        
        # No device found - provide manual instructions
        return self.get_manual_instructions()