#!/usr/bin/env python3
"""
Motorola FRP Bypass Module - Combined Version
=============================================
Combined from motorola_frp.py and motorola_frp2.py.
Consolidates all Motorola FRP bypass methods into a single MotorolaFRP class.

Motorola model patterns: XT* (most Motorola phones)
"""

import logging
import subprocess
import time
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MotorolaFRPMethod(Enum):
    """Available Motorola FRP bypass methods"""
    ADB_REMOVE_ACCOUNT = "adb_remove_account"
    ADB_GATEKEEPER = "adb_gatekeeper"
    ADB_MOTOROLA_SPECIFIC = "adb_motorola"
    FASTBOOT_OEM = "fastboot_oem"
    FASTBOOT_FLASHING = "fastboot_flashing"
    EMERGENCY_DIALER = "emergency_dialer"
    SIM_PUK = "sim_puk"
    ACCESSIBILITY = "accessibility"
    BOOTLOADER_UNLOCK = "bootloader_unlock"


@dataclass
class MotorolaFRPResult:
    """Result of Motorola FRP bypass attempt"""
    success: bool
    method: MotorolaFRPMethod
    message: str
    details: Optional[str] = None
    requires_manual: bool = False


class MotorolaFRP:
    """
    Motorola FRP Bypass Implementation

    Supports multiple methods for bypassing Factory Reset Protection
    on Motorola devices including Moto G, Moto E, Moto X, Edge, and Razr series.

    Combined from motorola_frp.py and motorola_frp2.py.
    """

    MOTOROLA_MODELS = {
        'XT1': 'Moto E series',
        'XT2': 'Moto G series (older)',
        'XT3': 'Moto G series',
        'XT4': 'Moto G Power/Stylus',
        'XT5': 'Moto G Fast/Play',
        'XT6': 'Moto E/One series',
        'XT7': 'Moto Edge series',
        'XT8': 'Moto Edge+/Razr',
        'XT9': 'Moto Razr/Fold',
        'Moto': 'Moto series',
    }

    MOTOROLA_FRP_CODES = [
        "*#*#7378423#*#*",
        "*#*#7873742#*#*",
        "*#*#7780#*#*",
        "*#06#",
        "##7764726",
        "*#*#4636#*#*",
        "*#*#2432546#*#*",
        "*#*#6483#*#*",
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

    def is_motorola_device(self, model: str) -> bool:
        """Check if device is Motorola based on model number"""
        if not model:
            return False
        model_upper = model.upper()
        return any(model_upper.startswith(prefix.upper()) for prefix in self.MOTOROLA_MODELS.keys())

    def get_motorola_series(self, model: str) -> str:
        """Get the Motorola device series from model number"""
        model_upper = model.upper()
        for prefix, series in self.MOTOROLA_MODELS.items():
            if model_upper.startswith(prefix.upper()):
                return series
        return "Unknown Motorola Device"

    def check_device_state(self) -> str:
        """Check if device is in ADB or Fastboot mode"""
        ret, out, _ = self.run_adb(['get-state'])
        if ret == 0 and 'device' in out:
            return 'adb'

        ret, out, _ = self.run_fastboot(['getvar', 'is-userspace'])
        if ret == 0:
            return 'fastboot'

        return 'unknown'

    def bypass_adb_remove_account(self) -> MotorolaFRPResult:
        """
        Method 1: Remove Google account via ADB

        Works on older Motorola devices with accessible ADB.
        Removes the Google account data that triggers FRP.
        """
        commands = [
            ['shell', 'rm', '-rf', '/data/data/com.google.android.gsf'],
            ['shell', 'rm', '-rf', '/data/data/com.google.android.gms'],
            ['shell', 'rm', '-rf', '/data/data/com.google.android.apps.maps'],
            ['shell', 'rm', '-rf', '/data/system/users/0/accounts.db'],
            ['shell', 'rm', '-rf', '/data/system/users/0/accounts.db-journal'],
            ['shell', 'pm', 'clear', 'com.google.android.gsf'],
            ['shell', 'pm', 'clear', 'com.google.android.gms'],
        ]

        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))

        success_count = sum(1 for _, success in results if success)
        self.run_adb(['reboot'])

        if success_count > 0:
            return MotorolaFRPResult(
                success=True,
                method=MotorolaFRPMethod.ADB_REMOVE_ACCOUNT,
                message=f"FRP bypass completed. {success_count}/{len(commands)} commands executed successfully.",
                details="Device is rebooting. FRP should be bypassed after restart.",
            )

        return MotorolaFRPResult(
            success=False,
            method=MotorolaFRPMethod.ADB_REMOVE_ACCOUNT,
            message="Commands failed. Device may require root access.",
            details="Device is rebooting. Check if FRP was bypassed after restart.",
        )

    def bypass_adb_gatekeeper(self) -> MotorolaFRPResult:
        """
        Method 2: Remove Gatekeeper keys via ADB

        Works on devices where Gatekeeper stores the FRP state.
        Requires root access or ADB root.
        """
        commands = [
            ['shell', 'rm', '/data/system/gatekeeper.password.key'],
            ['shell', 'rm', '/data/system/gatekeeper.pattern.key'],
            ['shell', 'rm', '/data/system/gatekeeper.gesture.key'],
            ['shell', 'rm', '/data/system/locksettings.db'],
            ['shell', 'rm', '/data/system/locksettings.db-wal'],
            ['shell', 'rm', '/data/system/locksettings.db-shm'],
            ['shell', 'rm', '-rf', '/data/misc/keystore/user_0'],
            ['shell', 'rm', '-rf', '/data/system/users/0/frp'],
            ['shell', 'rm', '-rf', '/data/system/users/0/fpData.xml'],
        ]

        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))

        success_count = sum(1 for _, success in results if success)
        self.run_adb(['reboot'])

        if success_count > 0:
            return MotorolaFRPResult(
                success=True,
                method=MotorolaFRPMethod.ADB_GATEKEEPER,
                message=f"Gatekeeper keys removed. {success_count}/{len(commands)} commands successful.",
                details="Device is rebooting. FRP lock should be cleared.",
            )

        return MotorolaFRPResult(
            success=False,
            method=MotorolaFRPMethod.ADB_GATEKEEPER,
            message="Commands failed. Root access may be required.",
            details="Device is rebooting. Check if FRP was bypassed after restart.",
        )

    def bypass_adb_motorola_specific(self) -> MotorolaFRPResult:
        """
        Method 3: Motorola-specific ADB FRP Bypass

        Uses Motorola-specific system paths and commands.
        """
        commands = [
            ['shell', 'pm', 'clear', 'com.motorola.android.providers.settings'],
            ['shell', 'pm', 'clear', 'com.motorola.moto'],
            ['shell', 'rm', '-rf', '/data/data/com.motorola.setup'],
            ['shell', 'rm', '-rf', '/data/data/com.motorola.android.setup'],
            ['shell', 'rm', '-rf', '/data/data/com.motorola.cnw'],
            ['shell', 'rm', '-rf', '/data/data/com.motorola.wapi'],
            ['shell', 'pm', 'disable', 'com.motorola.android.setup'],
            ['shell', 'pm', 'disable', 'com.google.android.setupwizard'],
            ['shell', 'rm', '/data/system/users/0/frp.xml'],
            ['shell', 'rm', '/data/system/frp.dat'],
            ['shell', 'settings', 'put', 'secure', 'user_setup_complete', '1'],
            ['shell', 'settings', 'put', 'global', 'device_provisioned', '1'],
        ]

        results = []
        for cmd in commands:
            ret, out, err = self.run_adb(cmd)
            results.append((cmd, ret == 0))

        success_count = sum(1 for _, success in results if success)
        self.run_adb(['reboot'])

        if success_count > 0:
            return MotorolaFRPResult(
                success=True,
                method=MotorolaFRPMethod.ADB_MOTOROLA_SPECIFIC,
                message=f"Motorola FRP bypass completed. {success_count}/{len(commands)} commands executed.",
                details="Device is rebooting. FRP should be bypassed after restart.",
            )

        return MotorolaFRPResult(
            success=False,
            method=MotorolaFRPMethod.ADB_MOTOROLA_SPECIFIC,
            message="Commands failed. Device may require root access.",
            details="Device is rebooting. Check if FRP was bypassed after restart.",
        )

    def bypass_fastboot_oem(self) -> MotorolaFRPResult:
        """
        Method 4: Fastboot OEM commands for Motorola

        Uses Motorola-specific fastboot commands to disable FRP.
        Works on devices with unlockable bootloader.
        """
        unlock_commands = [
            ['oem', 'unlock'],
            ['oem', 'unlock-go'],
            ['flashing', 'unlock'],
            ['oem', 'get_identifier_token'],
        ]

        frp_commands = [
            ['oem', 'frp-unlock'],
            ['oem', 'unlock-frp'],
            ['oem', 'frp_reset'],
            ['oem', 'reset_frp'],
            ['oem', 'format userdata'],
            ['oem', 'wipe_data'],
        ]

        ret, out, _ = self.run_fastboot(['getvar', 'unlocked'])

        if 'unlocked: no' in out.lower():
            ret, info_out, _ = self.run_fastboot(['getvar', 'product'])

            for cmd in unlock_commands:
                ret, out, err = self.run_fastboot(cmd)
                if ret == 0 or 'success' in out.lower() or 'success' in err.lower():
                    time.sleep(2)
                    break

        for cmd in frp_commands:
            ret, out, err = self.run_fastboot(cmd)
            if ret == 0 or 'success' in out.lower() or 'success' in err.lower():
                self.run_fastboot(['reboot'])
                return MotorolaFRPResult(
                    success=True,
                    method=MotorolaFRPMethod.FASTBOOT_OEM,
                    message=f"FRP bypass successful via fastboot {cmd[1]}",
                    details="Device will reboot with FRP disabled.",
                )

        return MotorolaFRPResult(
            success=False,
            method=MotorolaFRPMethod.FASTBOOT_OEM,
            message="Fastboot OEM commands not supported on this device or bootloader locked.",
        )

    def bypass_accessibility(self) -> MotorolaFRPResult:
        """
        Method 5: Accessibility menu bypass

        Uses accessibility services to bypass FRP setup.
        Requires user interaction.
        """
        instructions = """
Motorola FRP Bypass via Accessibility:

Method A - TalkBack Bypass:
1. On the FRP lock screen, tap "Vision Settings" or "Accessibility"
2. Enable "TalkBack" or "Select to Speak"
3. Draw an 'L' shape on the screen to open TalkBack settings
4. Scroll down and tap "Help & Feedback"
5. Search for any term and tap a result
6. This will open a browser - navigate to:
   - google.com and sign in with a new account
   - OR download a FRP bypass APK
7. After signing in, restart the setup process

Method B - Setup Wizard Bypass:
1. Go to Settings > Apps
2. Find "Google Play Services"
3. Tap "Disable"
4. Complete setup
5. Re-enable Google Play Services

Method C - Motorola Quick Shortcuts:
1. From accessibility menu, enable "Moto Actions" if available
2. Use chop gesture twice for flashlight (activates system)
3. Twist gesture twice for camera
4. These can sometimes access system before FRP check

Method D - Notification Access:
1. Long press on notification area if accessible
2. Look for "Notifications" or "Settings"
3. Navigate to Accounts > Add account
4. Add Google account

Important for Motorola:
- Moto devices often respond well to TalkBack method
- Some Moto G models have quick bypass via emergency dialer
- Moto Edge and Razr may need multiple attempts
"""

        return MotorolaFRPResult(
            success=True,
            method=MotorolaFRPMethod.ACCESSIBILITY,
            message="Manual bypass instructions provided.",
            details=instructions,
            requires_manual=True,
        )

    def bypass_emergency_dialer(self) -> MotorolaFRPResult:
        """
        Method 6: Emergency dialer bypass

        Uses emergency dialer to access settings.
        Device-specific codes may vary.
        """
        instructions = f"""
Motorola FRP Bypass via Emergency Dialer:

Step 1: Access Emergency Dialer
1. From the FRP lock screen, tap "Emergency Call"

Step 2: Try Dialer Codes
Try these codes one by one:

{chr(10).join(f'   - {code}' for code in self.MOTOROLA_FRP_CODES)}

Step 3: If Service Menu Opens
Look for:
- "FRP Unlock" option
- "Factory Reset" without FRP
- "Skip Setup" option
- "Wipe Data" option

Step 4: Alternative Methods

Method A - Fake Emergency:
1. Dial any number quickly and cancel
2. Rapidly tap on settings or notification area
3. Some Motorola devices allow brief system access

Method B - SIM Card Method:
1. Insert a locked SIM card
2. Enter wrong PUK code multiple times
3. When prompted, select "Emergency Call"
4. Try to access Settings from there

Method C - Notification Pull-Down:
1. Some Motorola devices allow notification access during emergency call
2. Pull down notification shade
3. Tap Settings icon
4. Navigate to Accounts

Motorola-Specific Tips:
- Moto G series: Try dialer codes first
- Moto E series: Accessibility method works best
- Moto Edge/Razr: May need multiple attempts
- Older Moto X: Fastboot OEM unlock often works
"""

        return MotorolaFRPResult(
            success=True,
            method=MotorolaFRPMethod.EMERGENCY_DIALER,
            message="Manual bypass instructions provided.",
            details=instructions,
            requires_manual=True,
        )

    def bypass_sim_puk(self) -> MotorolaFRPResult:
        """
        Method 7: SIM PUK bypass method

        Uses SIM PUK lock screen to bypass FRP.
        """
        instructions = """
Motorola FRP Bypass via SIM PUK Method:

Requirements:
- A SIM card with unknown PUK code (locked SIM)
- Or a SIM card you can lock

Step 1: Lock SIM Card (if not already locked)
1. Insert SIM into another phone
2. Go to Settings > Security > SIM Lock
3. Enter wrong PIN 3 times to lock SIM
4. SIM now requires PUK code

Step 2: Insert Locked SIM
1. Insert the locked SIM into Motorola device
2. Boot the device
3. When prompted for PUK code, enter wrong code 5-10 times

Step 3: Access System
1. After multiple wrong PUK attempts, options may appear:
   - "Emergency Call"
   - "Settings"
   - "Skip"

2. If Settings is accessible:
   - Go to Accounts
   - Add Google account
   - Restart device

3. If Emergency Call accessible:
   - Try dialer codes
   - Try to access notification shade

Step 4: Alternative - Call Method
1. Enter wrong PUK code until prompted for emergency call
2. Make a call to any number
3. During call, try to access Settings via notification
4. Some Motorola models allow account addition during call

Note:
- This method exploits the SIM lock screen's emergency features
- Works best on older Motorola devices
- Newer Android versions may block this method
"""

        return MotorolaFRPResult(
            success=True,
            method=MotorolaFRPMethod.SIM_PUK,
            message="SIM PUK bypass instructions provided.",
            details=instructions,
            requires_manual=True,
        )

    def bypass_bootloader_unlock(self) -> MotorolaFRPResult:
        """
        Method 8: Bootloader Unlock FRP Bypass

        Unlocking bootloader removes FRP on most Motorola devices.
        """
        instructions = """
Motorola FRP Bypass via Bootloader Unlock:

WARNING: This will erase all data on the device!

Step 1: Enable OEM Unlocking
1. If you can access developer options:
   - Go to Settings > About Phone
   - Tap "Build Number" 7 times
   - Go to Developer Options
   - Enable "OEM Unlocking"

Step 2: Enter Fastboot Mode
1. Power off the device completely
2. Press and hold: Volume Down + Power button
3. Keep holding until you see "Fastboot" on screen
4. Release buttons

Step 3: Connect to PC
1. Connect device to PC via USB cable
2. Open command prompt/terminal
3. Type: fastboot devices
4. Confirm your device is listed

Step 4: Get Unlock Data
Type: fastboot oem get_unlock_data

You will see a code like:
(Device-specific unlock code)

Step 5: Request Unlock Key
1. Go to Motorola's unlock website:
   https://motorola-global-portal.custhelp.com/app/standalone/bootloader/unlock-your-device-a
2. Create account or sign in
3. Enter the unlock data from step 4
4. Motorola will generate unlock code
5. Check your email for the code

Step 6: Unlock Bootloader
Type: fastboot oem unlock YOUR_CODE_HERE

Replace YOUR_CODE_HERE with the code from Motorola.

Step 7: Confirm Unlock
1. Use Volume buttons to select "UNLOCK"
2. Press Power button to confirm
3. Device will wipe and reboot
4. FRP is now removed!

Alternative for Some Models:
fastboot flashing unlock
fastboot oem unlock-go

Post-Unlock:
- Device will show "Bootloader Unlocked" warning on boot
- FRP is completely removed
- You can now use device or install custom ROM

Note:
- Some carriers (Verizon, AT&T) block bootloader unlock
- This erases ALL data on device
- Warranty may be voided
"""

        return MotorolaFRPResult(
            success=True,
            method=MotorolaFRPMethod.BOOTLOADER_UNLOCK,
            message="Bootloader unlock instructions provided.",
            details=instructions,
            requires_manual=True,
        )

    def get_recommended_method(self, android_version: str = None, model: str = None) -> MotorolaFRPMethod:
        """Get the recommended FRP bypass method based on device info"""
        if model and self.is_motorola_device(model):
            series = self.get_motorola_series(model)

            if 'Edge' in series or 'Razr' in series:
                return MotorolaFRPMethod.ACCESSIBILITY

            if 'Power' in series or 'Stylus' in series:
                return MotorolaFRPMethod.EMERGENCY_DIALER

            if android_version:
                try:
                    version = float(android_version.split('.')[0])
                    if version >= 12:
                        return MotorolaFRPMethod.ACCESSIBILITY
                    elif version >= 10:
                        return MotorolaFRPMethod.BOOTLOADER_UNLOCK
                    elif version >= 7:
                        return MotorolaFRPMethod.ADB_GATEKEEPER
                    else:
                        return MotorolaFRPMethod.ADB_REMOVE_ACCOUNT
                except Exception:
                    pass

            return MotorolaFRPMethod.ACCESSIBILITY

        return MotorolaFRPMethod.ACCESSIBILITY

    def auto_bypass(self, model: str = None, android_version: str = None) -> MotorolaFRPResult:
        """Automatically attempt FRP bypass using the best available method"""
        state = self.check_device_state()

        if state == 'adb':
            result = self.bypass_adb_motorola_specific()
            if result.success:
                return result

            result = self.bypass_adb_gatekeeper()
            if result.success:
                return result

            result = self.bypass_adb_remove_account()
            if result.success:
                return result

            return self.bypass_accessibility()

        elif state == 'fastboot':
            result = self.bypass_fastboot_oem()
            if result.success:
                return result

            return self.bypass_bootloader_unlock()

        else:
            return MotorolaFRPResult(
                success=False,
                method=MotorolaFRPMethod.ACCESSIBILITY,
                message="No device detected. Please connect device and enable USB debugging or boot to fastboot mode.",
                details="Connect device via USB and ensure:\n1. USB debugging is enabled (ADB mode)\n2. Or device is in fastboot/bootloader mode",
            )
