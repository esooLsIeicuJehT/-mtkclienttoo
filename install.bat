@echo off
echo ============================================
echo   MTK Client 2.0 -- Windows Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://python.org
    pause
    exit /b 1
)

echo [1/4] Installing Python dependencies...
pip install PyQt5 pyusb pyserial requests cryptography Pillow colorlog
if errorlevel 1 (
    echo [ERROR] pip install failed. Try: pip install --user ...
    pause
    exit /b 1
)
echo [OK] Python deps installed

echo.
echo [2/4] Checking for UsbDk...
if exist "C:\Windows\System32\UsbDk.dll" (
    echo [OK] UsbDk found
) else (
    echo [WARN] UsbDk not found.
    echo        Download from: https://github.com/daynix/UsbDk/releases
    echo        Required for USB device access without admin rights.
)

echo.
echo [3/4] Checking for ADB...
adb --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] ADB not found. Download platform-tools from:
    echo        https://developer.android.com/studio/releases/platform-tools
) else (
    echo [OK] ADB found
)

echo.
echo [4/4] Creating launcher...
set SCRIPT_DIR=%~dp0
echo @echo off > "%SCRIPT_DIR%run.bat"
echo cd /d "%SCRIPT_DIR%" >> "%SCRIPT_DIR%run.bat"
echo python main.py >> "%SCRIPT_DIR%run.bat"
echo pause >> "%SCRIPT_DIR%run.bat"
echo [OK] run.bat created

echo.
echo ============================================
echo   Installation complete!
echo   Run: python main.py   or   run.bat
echo ============================================
echo.
echo IMPORTANT Windows notes:
echo   1. Install MediaTek VCOM USB drivers from your firmware folder
echo   2. Install UsbDk for low-level USB access
echo   3. Run as Administrator if USB access fails
echo   4. Disable Windows Defender real-time protection if tool is blocked
echo.
pause
