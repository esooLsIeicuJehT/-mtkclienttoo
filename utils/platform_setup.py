"""
Platform Setup — handles OS-specific prerequisites:
  - Fedora/Linux: udev rules, ModemManager blacklist, group membership
  - Windows: driver detection hints
  - macOS: libusb check
"""
import os
import sys
import platform
import subprocess
import shutil

UDEV_RULE_PATH = "/etc/udev/rules.d/51-mtk-devices.rules"
UDEV_RULE_CONTENT = """# MTK Client 2.0 — MediaTek Device Rules
# MediaTek Preloader
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev", TAG+="uaccess"
# MediaTek BROM
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0666", GROUP="plugdev", TAG+="uaccess"
# Blacklist ModemManager interference
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"
"""

MM_BLACKLIST_PATH = "/etc/udev/rules.d/20-mm-blacklist-mtk.rules"
MM_BLACKLIST_CONTENT = """# Block ModemManager from grabbing MTK devices
SUBSYSTEM=="usb", ACTION=="add", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"
"""


class PlatformSetup:
    def __init__(self):
        self.system = platform.system()
        self.issues = []
        self.warnings = []

    def ensure_prerequisites(self):
        if self.system == "Linux":
            self._check_linux()
        elif self.system == "Windows":
            self._check_windows()
        elif self.system == "Darwin":
            self._check_macos()

    # ── Linux / Fedora ────────────────────────────────────────────────────────
    def _check_linux(self):
        self._check_udev_rules()
        self._check_modemmanager()
        self._check_group_membership()
        self._check_libusb()

    def _check_udev_rules(self):
        """Install udev rules if missing (requires pkexec/sudo)."""
        if not os.path.exists(UDEV_RULE_PATH):
            self._try_write_udev()

    def _try_write_udev(self):
        """Attempt to write udev rules via pkexec."""
        script = f"""#!/bin/bash
cat > {UDEV_RULE_PATH} << 'EOF'
{UDEV_RULE_CONTENT}
EOF
cat > {MM_BLACKLIST_PATH} << 'EOF'
{MM_BLACKLIST_CONTENT}
EOF
udevadm control --reload-rules
udevadm trigger
"""
        tmp = "/tmp/mtk_udev_setup.sh"
        with open(tmp, "w") as f:
            f.write(script)
        os.chmod(tmp, 0o755)
        # Try pkexec (polkit GUI prompt), fall back to silent
        if shutil.which("pkexec"):
            try:
                subprocess.run(["pkexec", tmp], timeout=30)
            except Exception:
                self.warnings.append("udev rules not installed — run as root manually.")
        else:
            self.warnings.append("udev rules missing. Run: sudo bash /tmp/mtk_udev_setup.sh")

    def _check_modemmanager(self):
        """Warn if ModemManager is running and could interfere."""
        result = subprocess.run(
            ["systemctl", "is-active", "ModemManager"],
            capture_output=True, text=True
        )
        if result.stdout.strip() == "active":
            self.warnings.append(
                "ModemManager is running and may interfere with device detection. "
                "Consider: sudo systemctl stop ModemManager"
            )

    def _check_group_membership(self):
        import grp
        username = os.environ.get("USER", "")
        for grp_name in ("plugdev", "dialout", "uucp"):
            try:
                g = grp.getgrnam(grp_name)
                if username not in g.gr_mem:
                    self.warnings.append(
                        f"User '{username}' not in '{grp_name}' group. "
                        f"Run: sudo usermod -aG {grp_name} {username}"
                    )
            except KeyError:
                pass

    def _check_libusb(self):
        try:
            import usb.core  # noqa
        except ImportError:
            self.issues.append("pyusb not installed. Run: pip install pyusb")

    # ── Windows ───────────────────────────────────────────────────────────────
    def _check_windows(self):
        self.warnings.append(
            "Windows: Install MediaTek VCOM USB drivers and UsbDk. "
            "See: https://github.com/bkerler/mtkclient#windows-setup"
        )

    # ── macOS ─────────────────────────────────────────────────────────────────
    def _check_macos(self):
        if not shutil.which("brew"):
            self.warnings.append("Homebrew not found. Install libusb: brew install libusb")

    # ── Public API ────────────────────────────────────────────────────────────
    def get_status(self) -> dict:
        return {
            "system": self.system,
            "issues": self.issues,
            "warnings": self.warnings,
            "ready": len(self.issues) == 0,
        }

    @staticmethod
    def get_fedora_install_cmd() -> str:
        return "sudo dnf install python3-pyusb libusb1 python3-pyserial python3-qt5 -y"

    @staticmethod
    def get_ubuntu_install_cmd() -> str:
        return "sudo apt install python3-usb libusb-1.0-0 python3-serial python3-pyqt5 -y"
