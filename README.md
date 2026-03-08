# MTK Client 2.0
### MediaTek Flash & Repair Utility — Cross-Platform

> A feature-complete, cross-platform MediaTek device management tool with a premium GUI. Built beyond the original MTK Client with BROM/Preloader/DA support, ADB integration, and one-click Fedora setup.

---

## Features

| Feature | Description |
|---|---|
| **Scatter Flash** | Full firmware flash via MT scatter files (new + legacy format) |
| **Partition Backup** | Backup any/all partitions to .bin files |
| **FRP Bypass** | Erase frp partition to remove Google account lock |
| **BROM Payload** | Send custom exploit payloads for auth bypass |
| **V6 Protocol** | Dimensity / new Helio G series support with loader |
| **NVRAM Backup** | Read/write NVRAM (IMEI, WiFi/BT MAC, calibration) |
| **Bootloader Unlock** | MTK method + fastboot assist |
| **ADB Shell** | Built-in ADB shell with quick actions |
| **Memory Test** | RAM + NAND flash health check |
| **Format / Wipe** | Per-partition or full device format |
| **Device Info** | Full hardware + Android info via BROM and ADB |
| **Boot Patching** | Magisk root workflow assistant |
| **Auto-Detect** | USB polling for hot-plug device detection |
| **One-Click Setup** | Fedora/Ubuntu/Arch udev, groups, ModemManager |

## Supported Chipsets

**Legacy (MT65xx):** MT6580, MT6735, MT6737, MT6739, MT6750, MT6752, MT6753, MT6755, MT6757

**Modern (MT67xx):** MT6761, MT6762, MT6763, MT6765, MT6768, MT6771, MT6779, MT6785, MT6789

**Dimensity (V6 protocol):** MT6853, MT6873, MT6877, MT6883, MT6885, MT6893, MT6895, MT6983, MT6985

**Tablets:** MT8127, MT8163, MT8173, MT8183, MT8192, MT8195

---

## Installation

### Fedora / Linux (Recommended)
```bash
git clone <repo> mtkclient2
cd mtkclient2
chmod +x install.sh
./install.sh
./run.sh
```

### Manual (Any Linux)
```bash
# Fedora
sudo dnf install python3-pyqt5 python3-pip libusb1 android-tools
pip3 install pyusb pyserial requests cryptography

# Ubuntu/Debian
sudo apt install python3-pyqt5 python3-usb python3-serial android-tools-adb

# Install udev rules
sudo cp udev/51-mtk-devices.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo usermod -aG plugdev,dialout $USER

python3 main.py
```

### Windows
1. Install [Python 3.10+](https://python.org)
2. Run `install.bat`
3. Install [UsbDk](https://github.com/daynix/UsbDk/releases)
4. Install MediaTek VCOM USB drivers
5. Run `python main.py`

---

## How to Enter BROM Mode

### Standard Method
1. Power off device completely
2. Hold **Vol-** (or **Vol+** on some devices)
3. Connect USB cable while holding the button
4. Release when device is detected

### Via ADB (Android already running)
```bash
adb reboot edl
```

### V6 Devices (Dimensity / new SOC)
- BROM is patched on V6 devices
- You **must** use a compatible loader from `Loaders/V6/`
- Load the loader in the Payload tab before connecting

---

## Context Flow Architecture

```
USB Event
    │
    ▼
MTKProtocol.connect()
    ├── BROM Mode    → _brom_handshake() → read_hw_code()
    ├── Preloader    → _preloader_handshake()
    └── DA Mode      → direct_access
    │
    ▼
ConnState change → MainWindow._on_state_change()
    │
    ▼
DeviceInfo populated → UI tabs updated
    │
    ▼
User Operation → FlashEngine.run(OpType, params)
    │
    ▼
FlashWorker (QThread)
    ├── progress → ProgressBar
    ├── status   → StatusLabel
    └── finished → Result Dialog
```

---

## Payload / Exploit Notes

| Exploit | Chipsets | Protocol |
|---|---|---|
| kamakiri | MT6580, MT6735, MT6737, MT6739 | Hardware (short pins 1+6 on USB) |
| amonet | MT6771 (Helio P60) | Software |
| carbonara | MT6762, MT6765 | Software |
| V6 Bypass | MT6853+ (Dimensity) | Loader required |

Payload .bin files are **not included** — source from [bkerler/mtkclient](https://github.com/bkerler/mtkclient).

---

## File Structure

```
mtkclient2/
├── main.py                 Entry point
├── requirements.txt
├── install.sh              Fedora/Linux installer
├── install.bat             Windows installer
├── core/
│   ├── mtk_protocol.py     BROM/Preloader USB protocol
│   ├── partition_manager.py Scatter parser + partition ops
│   ├── flash_engine.py     Operation orchestrator (QThread)
│   └── adb_bridge.py       ADB integration
├── ui/
│   ├── main_window.py      Top-level window
│   ├── tabs/
│   │   ├── info_tab.py     Device hardware info
│   │   ├── flash_tab.py    Scatter flash UI
│   │   ├── tools_tab.py    FRP, payload, ADB, repair
│   │   ├── log_tab.py      Live log viewer
│   │   └── setup_tab.py    OS setup wizard
│   └── styles/
│       └── dark_theme.qss  Industrial dark theme
└── utils/
    ├── logger.py           Qt-signal-aware logger
    └── platform_setup.py   udev/driver prerequisites
```

---

## Disclaimer

This tool is for **device repair, development, and educational purposes only**. 
Flashing incorrect firmware can permanently damage your device. Always backup before modifying. 
You are solely responsible for how you use this tool.
