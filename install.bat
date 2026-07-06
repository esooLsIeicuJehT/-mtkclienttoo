@echo off
echo ============================================
echo   MTK Client 2.0 -- Windows Installer
echo   Enhanced Version 2.1
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://python.org
    echo [INFO] Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Python architecture
python -c "import sys; print('64-bit' if sys.maxsize > 2**32 else '32-bit')" 2>nul
echo [INFO] Python architecture detected

echo.
echo [1/5] Installing Python dependencies...
pip install PyQt5 pyusb pyserial requests cryptography Pillow colorlog sqlmodel
if errorlevel 1 (
    echo [WARN] pip install had warnings. Try: pip install --user ...
)
echo [OK] Python deps installed

echo.
echo [2/5] Checking for UsbDk (USB driver)...
if exist "C:\Windows\System32\UsbDk.dll" (
    echo [OK] UsbDk found
) else if exist "C:\Program Files\UsbDk\UsbDk.dll" (
    echo [OK] UsbDk found
) else if exist "C:\Program Files (x86)\UsbDk\UsbDk.dll" (
    echo [OK] UsbDk found
) else (
    echo [WARN] UsbDk not found.
    echo        Download from: https://github.com/daynix/UsbDk/releases
    echo        REQUIRED for USB device access on Windows.
    echo        Install UsbDk BEFORE connecting MTK devices.
)

echo.
echo [3/5] Checking for MediaTek VCOM drivers...
reg query "HKLM\SYSTEM\CurrentControlSet\Enum\USB\VID_0E8D" >nul 2>&1
if not errorlevel 1 (
    echo [OK] MTK VCOM drivers registered in registry
) else (
    echo [WARN] MTK VCOM drivers not detected.
    echo        Download from: https://github.com/bkerler/mtkclient#windows-setup
    echo        Install drivers from your device firmware package when needed.
)

echo.
echo [4/5] Checking for ADB (Android Debug Bridge)...
adb --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] ADB not found. Actions may be limited.
    echo        Download platform-tools from:
    echo        https://developer.android.com/studio/releases/platform-tools
    echo        Extract to C:\platform-tools and add to PATH
) else (
    echo [OK] ADB found
)

echo.
echo [5/5] Creating launcher and desktop shortcut...
set SCRIPT_DIR=%~dp0
echo @echo off > "%SCRIPT_DIR%run.bat"
echo cd /d "%SCRIPT_DIR%" >> "%SCRIPT_DIR%run.bat"
echo python main.py >> "%SCRIPT_DIR%run.bat"
echo pause >> "%SCRIPT_DIR%run.bat"
echo [OK] run.bat created

:: Create desktop shortcut
set DESKTOp=%USERPROFILE%\Desktop
if exist "%DESKTOP%" (
    echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\shortcut.vbs"
    echo sLinkFile = "%DESKTOP%\MTK Client 2.0.lnk" >> "%TEMP%\shortcut.vbs"
    echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%TEMP%\shortcut.vbs"
    echo oLink.TargetPath = "%SCRIPT_DIR%run.bat" >> "%TEMP%\shortcut.vbs"
    echo oLink.WorkingDirectory = "%SCRIPT_DIR%" >> "%TEMP%\shortcut.vbs"
    echo oLink.IconLocation = "%SystemRoot%\System32\shell32.dll,13" >> "%TEMP%\shortcut.vbs"
    echo oLink.Save >> "%TEMP%\shortcut.vbs"
    cscript //nologo "%TEMP%\shortcut.vbs" 2>nul
    del "%TEMP%\shortcut.vbs" 2>nul
)

echo.
echo ============================================
echo   Installation complete!
echo   Run: run.bat   or   python main.py
echo ============================================
echo.
echo IMPORTANT Windows notes:
echo   1. Install UsbDk BEFORE connecting devices
echo   2. Install MediaTek VCOM drivers from firmware
echo   3. Run as Administrator if USB access fails
echo   4. Disable Windows Defender real-time if blocked
echo   5. For BROM mode: try different USB ports/cables
echo.
echo Press any key to exit...
pause >nul