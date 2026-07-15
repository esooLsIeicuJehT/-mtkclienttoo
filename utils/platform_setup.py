"""
Platform Setup — handles OS-specific prerequisites:
  - Fedora/Linux: udev rules, ModemManager blacklist, group membership
  - Windows: driver detection hints, UsbDk check, registry access
  - macOS: libusb check, security permissions
"""
import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict

# Cross-platform path handling
if platform.system() == "Windows":
    UDEV_RULE_PATH = Path("C:\\mtk_setup\\51-mtk-devices.rules")
    LOCAL_DB_PATH = Path(os.environ.get("APPDATA", "")) / "MTKClient2" / "database"
else:
    UDEV_RULE_PATH = Path("/etc/udev/rules.d/51-mtk-devices.rules")
    LOCAL_DB_PATH = Path.home() / ".local" / "share" / "mtkclient2" / "database"

# Linux udev rules
UDEV_RULE_CONTENT = """# MTK Client 2.0 — MediaTek Device Rules
# MediaTek Preloader
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev", TAG+="uaccess"
# MediaTek BROM
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0666", GROUP="plugdev", TAG+="uaccess"
# Blacklist ModemManager interference
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"
"""

MM_BLACKLIST_CONTENT = """# Block ModemManager from grabbing MTK devices
SUBSYSTEM=="usb", ACTION=="add", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"
"""


class PlatformSetup:
    def __init__(self):
        self.system = platform.system()
        self.issues: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self._init_paths()

    def _init_paths(self):
        """Initialize platform-specific paths."""
        LOCAL_DB_PATH.mkdir(parents=True, exist_ok=True)

    def ensure_prerequisites(self) -> Dict[str, List[str]]:
        """Check and install prerequisites for current platform."""
        if self.system == "Linux":
            self._check_linux()
        elif self.system == "Windows":
            self._check_windows()
        elif self.system == "Darwin":
            self._check_macos()
        
        return self.get_status()

    def _check_linux(self):
        """Linux/FedID specific checks."""
        # Check distribution
        dist = self._get_linux_dist()
        self.info.append(f"Detected: {dist}")
        
        self._check_udev_rules()
        self._check_modemmanager()
        self._check_group_membership()
        self._check_libusb()
        self._check_adb()

    def _get_linux_dist(self) -> str:
        """Detect Linux distribution."""
        try:
            if Path("/etc/os-release").exists():
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("ID="):
                            return line.split("=")[1].strip().strip('"')
        except Exception:
            pass
        return "unknown"

    def _check_udev_rules(self):
        """Install udev rules if missing (requires pkexec/sudo)."""
        if UDEV_RULE_PATH.exists():
            self.info.append(f"udev rules present at {UDEV_RULE_PATH}")
            return
        
        # Try to write udev rules via polkit
        tmp_script = "/tmp/mtk_udev_setup.sh"
        script = f"""#!/bin/bash
mkdir -p /etc/udev/rules.d
cat > /etc/udev/rules.d/51-mtk-devices.rules << 'EOF'
{UDEV_RULE_CONTENT}
EOF
cat > /etc/udev/rules.d/20-mm-blacklist-mtk.rules << 'EOF'
{MM_BLACKLIST_CONTENT}
EOF
udevadm control --reload-rules
udevadm trigger
"""
        try:
            with open(tmp_script, "w") as f:
                f.write(script)
            os.chmod(tmp_script, 0o755)
            
            if shutil.which("pkexec"):
                subprocess.run(["pkexec", tmp_script], timeout=30, capture_output=True)
                self.info.append("udev rules installed via pkexec")
            elif shutil.which("sudo"):
                subprocess.run(["sudo", tmp_script], timeout=30, capture_output=True)
                self.info.append("udev rules installed via sudo")
            else:
                self.warnings.append(
                    "udev rules missing. Run as root or use: sudo bash /tmp/mtk_udev_setup.sh"
                )
        except Exception as e:
            self.warnings.append(f"Could not install udev rules: {e}")

    def _check_modemmanager(self):
        """Warn if ModemManager is running and could interfere."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "ModemManager"],
                capture_output=True, text=True
            )
            if result.stdout.strip() == "active":
                self.warnings.append(
                    "ModemManager is running and may interfere with device detection. "
                    "Consider: sudo systemctl stop ModemManager"
                )
        except FileNotFoundError:
            pass

    def _check_group_membership(self):
        """Check if user is in required groups for USB access."""
        import grp
        username = os.environ.get("USER", "")
        for grp_name in ("plugdev", "dialout", "uucp"):
            try:
                g = grp.getgrnam(grp_name)
                if username not in g.gr_mem:
                    self.warnings.append(
                        f"User '{username}' not in '{grp_name}' group for USB access. "
                        f"Run: sudo usermod -aG {grp_name} {username}"
                    )
            except KeyError:
                self.warnings.append(f"Group '{grp_name}' does not exist on this system.")

    def _check_libusb(self):
        """Check if pyusb/libusb is available."""
        try:
            import usb.core
            self.info.append("pyusb available")
        except ImportError:
            self.issues.append("pyusb not installed. Run: pip install pyusb")

    def _check_adb(self):
        """Check if ADB is available."""
        adb = shutil.which("adb")
        if adb:
            self.info.append(f"ADB found: {adb}")
        else:
            self.warnings.append("ADB not found. Install android-tools for ADB features.")

    def _check_windows(self):
        """Windows specific checks."""
        self.info.append("Windows platform detected")
        
        # Check for UsbDk
        usbdk_path = self._find_usbdk()
        if usbdk_path:
            self.info.append(f"UsbDk found: {usbdk_path}")
        else:
            self.warnings.append(
                "UsbDk not detected. Install from: https://github.com/daynix/UsbDk/releases\n"
                "UsbDk is required for MTK device passthrough on Windows."
            )
        
        # Check registry for MTK VCOM drivers
        mtk_drv = self._check_mtk_registry()
        if mtk_drv:
            self.info.append(f"MTK VCOM driver found: {mtk_drv}")
        else:
            self.warnings.append(
                "MediaTek VCOM USB drivers not detected.\n"
                "Download from: https://github.com/bkerler/mtkclient#windows-setup\n"
                "Also install Zadig (https://zadig.akeo.ie/) for libusb driver replacement."
            )
        
        # Check Python architecture
        if sys.maxsize > 2**32:
            self.info.append("Running 64-bit Python")
        else:
            self.info.append("Running 32-bit Python")
        
        # Check if running as admin (needed for driver install)
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if is_admin:
                self.info.append("Running with administrator privileges")
            else:
                self.warnings.append(
                    "Not running as administrator. "
                    "Some operations may fail. Consider running as admin for driver operations."
                )
        except Exception:
            pass

    def _find_usbdk(self) -> Optional[str]:
        """Find UsbDk installation on Windows."""
        if self.system != "Windows":
            return None
        
        # Check common locations
        candidates = [
            Path("C:\\Program Files\\UsbDk\\UsbDk.dll"),
            Path("C:\\Program Files (x86)\\UsbDk\\UsbDk.dll"),
            Path(os.environ.get("ProgramFiles", "")) / "UsbDk" / "UsbDk.dll",
        ]
        
        for c in candidates:
            if c.exists():
                return str(c)
        
        # Check registry
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\UsbDk")
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            if Path(path).exists():
                return path
        except Exception:
            pass
        
        return None

    def _check_mtk_registry(self) -> Optional[str]:
        """Check Windows registry for MTK VCOM drivers."""
        if self.system != "Windows":
            return None
        
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\\CurrentControlSet\\Enum\\USB\\VID_0E8D"
            )
            winreg.CloseKey(key)
            return "VCOM driver registered"
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _check_macos(self):
        """macOS specific checks."""
        self.info.append("macOS platform detected")
        
        # Check Homebrew
        if not shutil.which("brew"):
            self.warnings.append("Homebrew not found. Install libusb: brew install libusb")
        
        # Check libusb
        try:
            import usb.core
            self.info.append("libusb available via pyusb")
        except ImportError:
            self.issues.append("pyusb/libusb not available. Install: brew install libusb && pip install pyusb")
        
        # Check for necessary permissions
        self.info.append(
            "For BROM mode access on macOS, you may need to:\n"
            "1. Allow Terminal/iTerm in System Preferences → Security & Privacy → Privacy → Accessibility\n"
            "2. Or run: sudo python3 main.py"
        )

    def get_status(self) -> dict:
        return {
            "system": self.system,
            "issues": self.issues,
            "warnings": self.warnings,
            "info": self.info,
            "ready": len(self.issues) == 0,
        }

    @staticmethod
    def get_install_commands() -> Dict[str, str]:
        """Return platform-specific install commands."""
        current_system = platform.system()
        
        if current_system == "Linux":
            distro = ""
            if Path("/etc/fedora-release").exists():
                distro = "fedora"
            elif Path("/etc/debian_version").exists():
                distro = "debian"
            
            if distro == "fedora":
                cmd = "sudo dnf install python3-pyusb libusb1 python3-pyserial python3-qt5 android-tools -y"
            else:
                cmd = "sudo apt install python3-usb libusb-1.0-0 python3-serial python3-pyqt5 android-tools-adb -y"
        elif current_system == "Windows":
            cmd = "pip install pyusb pyserial requests cryptography\n# Also install UsbDk and MTK VCOM drivers"
        elif current_system == "Darwin":
            cmd = "brew install libusb python3 && pip3 install pyusb pyserial PyQt5"
        else:
            cmd = "pip install pyusb pyserial PyQt5 requests cryptography"
        
        return {"command": cmd, "notes": "Run in terminal/PowerShell"}

    @staticmethod
    def create_udev_script(output_path: Path):
        """Create udev installation script for Linux."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""#!/bin/bash
# MTK Client 2.0 - udev setup script
sudo mkdir -p /etc/udev/rules.d

sudo tee /etc/udev/rules.d/51-mtk-devices.rules > /dev/null << 'EOF'
{UDEV_RULE_CONTENT}
EOF

sudo tee /etc/udev/rules.d/20-mm-blacklist-mtk.rules > /dev/null << 'EOF'
{MM_BLACKLIST_CONTENT}
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger

# Add user to required groups
sudo usermod -aG plugdev ${{USER}} 2>/dev/null || true
sudo usermod -aG dialout ${{USER}} 2>/dev/null || true

echo "udev rules installed. Log out and back in for group changes to take effect."
"""
        output_path.write_text(content)
        output_path.chmod(0o755)