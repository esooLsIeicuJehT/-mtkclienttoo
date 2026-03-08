"""
ADB Bridge — wraps platform ADB binary for additional device management.

Context Flow:
  ADB Available? → Detect Device → Execute Command → Parse Output
"""
import subprocess
import shutil
import os
import platform
from typing import Optional, List, Tuple
from utils.logger import get_logger

log = get_logger("adb")


def _find_adb() -> Optional[str]:
    """Find adb binary on PATH or common locations."""
    if shutil.which("adb"):
        return "adb"
    # Common install locations
    candidates = []
    if platform.system() == "Windows":
        candidates = [
            r"C:\platform-tools\adb.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
        ]
    else:
        candidates = [
            "/usr/bin/adb",
            "/usr/local/bin/adb",
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
            os.path.expanduser("~/platform-tools/adb"),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


class ADBBridge:
    def __init__(self):
        self._adb = _find_adb()
        if self._adb:
            log.info(f"ADB found: {self._adb}")
        else:
            log.warning("ADB not found. Install platform-tools for ADB features.")

    @property
    def available(self) -> bool:
        return self._adb is not None

    def _run(self, *args, timeout=10) -> Tuple[int, str, str]:
        if not self._adb:
            return -1, "", "ADB not available"
        cmd = [self._adb] + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except Exception as e:
            return -1, "", str(e)

    # ── Device Detection ──────────────────────────────────────────────────────
    def get_devices(self) -> List[dict]:
        _, out, _ = self._run("devices", "-l")
        devices = []
        for line in out.splitlines()[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state  = parts[1]
                props  = {}
                for p in parts[2:]:
                    if ":" in p:
                        k, v = p.split(":", 1)
                        props[k] = v
                devices.append({"serial": serial, "state": state, **props})
        return devices

    # ── Device Info via ADB ───────────────────────────────────────────────────
    def get_prop(self, prop: str, serial: str = "") -> str:
        args = []
        if serial:
            args = ["-s", serial]
        args += ["shell", "getprop", prop]
        _, out, _ = self._run(*args)
        return out.strip("[]").strip()

    def get_full_info(self, serial: str = "") -> dict:
        props = {
            "Model":         "ro.product.model",
            "Brand":         "ro.product.brand",
            "Android":       "ro.build.version.release",
            "SDK":           "ro.build.version.sdk",
            "Build":         "ro.build.display.id",
            "Chipset":       "ro.hardware",
            "CPU ABI":       "ro.product.cpu.abi",
            "Fingerprint":   "ro.build.fingerprint",
            "Bootloader":    "ro.bootloader",
            "Baseband":      "gsm.version.baseband",
            "Serial":        "ro.serialno",
            "IMEI":          "persist.radio.imei",
            "Security Patch":"ro.build.version.security_patch",
            "Codename":      "ro.product.device",
            "Manufacturer":  "ro.product.manufacturer",
        }
        result = {}
        for label, prop in props.items():
            result[label] = self.get_prop(prop, serial)
        return result

    # ── Operations ────────────────────────────────────────────────────────────
    def reboot(self, mode: str = "", serial: str = "") -> bool:
        """Reboot device: mode can be '', 'recovery', 'bootloader', 'edl'"""
        args = []
        if serial:
            args += ["-s", serial]
        args.append("reboot")
        if mode:
            args.append(mode)
        code, _, _ = self._run(*args)
        return code == 0

    def reboot_edl(self, serial: str = "") -> bool:
        """Reboot into EDL/BROM mode via ADB."""
        args = []
        if serial:
            args += ["-s", serial]
        args += ["shell", "reboot", "edl"]
        code, _, _ = self._run(*args)
        return code == 0

    def push_file(self, local: str, remote: str, serial: str = "") -> bool:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["push", local, remote]
        code, _, _ = self._run(*args, timeout=60)
        return code == 0

    def pull_file(self, remote: str, local: str, serial: str = "") -> bool:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["pull", remote, local]
        code, _, _ = self._run(*args, timeout=120)
        return code == 0

    def shell(self, command: str, serial: str = "") -> Tuple[int, str]:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["shell"] + command.split()
        code, out, err = self._run(*args, timeout=30)
        return code, out or err

    def sideload(self, zip_path: str, serial: str = "") -> bool:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["sideload", zip_path]
        code, _, _ = self._run(*args, timeout=300)
        return code == 0

    def install_apk(self, apk_path: str, serial: str = "") -> Tuple[bool, str]:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["install", "-r", apk_path]
        code, out, err = self._run(*args, timeout=60)
        return code == 0, out or err

    def get_logcat(self, lines: int = 200, serial: str = "") -> str:
        args = []
        if serial:
            args += ["-s", serial]
        args += ["logcat", "-d", "-t", str(lines)]
        _, out, _ = self._run(*args, timeout=15)
        return out

    def backup_apks(self, out_dir: str, serial: str = "") -> int:
        """Pull all user APKs to out_dir."""
        _, pkgs, _ = self._run(*([] if not serial else ["-s", serial]),
                               "shell", "pm", "list", "packages", "-3", "-f")
        count = 0
        for line in pkgs.splitlines():
            # line: package:/data/app/com.example-1/base.apk=com.example
            if "package:" not in line:
                continue
            apk_path = line.split(":")[1].split("=")[0]
            pkg_name = line.split("=")[-1]
            local    = os.path.join(out_dir, f"{pkg_name}.apk")
            if self.pull_file(apk_path, local, serial):
                count += 1
        return count

    def start_server(self):
        self._run("start-server")

    def kill_server(self):
        self._run("kill-server")
