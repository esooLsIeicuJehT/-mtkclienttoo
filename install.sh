#!/usr/bin/env bash
# MTK Client 2.0 — Linux Installer
# Supports: Fedora, RHEL, CentOS, Ubuntu, Debian, Arch, openSUSE

set -e
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║    MTK CLIENT 2.0 — Linux Installer      ║"
echo "║         Enhanced Detection v2.1          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Detect distro
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${ID:-unknown}"
    DISTRO_LIKE="${ID_LIKE:-}"
else
    DISTRO="unknown"
fi

echo -e "${CYAN}Detected: ${DISTRO} ${VERSION_ID:-}${NC}"

install_fedora() {
    echo -e "${YELLOW}Installing dependencies (Fedora/RHEL)...${NC}"
    sudo dnf install -y \
        python3 python3-pip python3-pyqt5 python3-devel \
        libusb1 libusb1-devel \
        python3-pyserial python3-sqlalchemy \
        android-tools \
        usbutils
    pip3 install --user pyusb requests cryptography Pillow colorlog sqlmodel
}

install_debian() {
    echo -e "${YELLOW}Installing dependencies (Debian/Ubuntu)...${NC}"
    sudo apt update
    sudo apt install -y \
        python3 python3-pip python3-pyqt5 python3-dev \
        libusb-1.0-0 libusb-1.0-0-dev \
        python3-serial python3-usb python3-sqlalchemy \
        android-tools-adb \
        usbutils
    pip3 install --user requests cryptography Pillow colorlog sqlmodel
}

install_arch() {
    echo -e "${YELLOW}Installing dependencies (Arch)...${NC}"
    sudo pacman -Sy --noconfirm \
        python python-pip python-pyqt5 python-pyserial \
        libusb android-tools
    pip3 install --user pyusb requests cryptography Pillow colorlog sqlmodel
}

case "$DISTRO" in
    fedora|rhel|centos|rocky|almalinux)
        install_fedora ;;
    ubuntu|debian|linuxmint|pop|mint)
        install_debian ;;
    arch|manjaro|endeavouros|artix)
        install_arch ;;
    opensuse*)
        echo -e "${YELLOW}openSUSE detected. Installing via zypper...${NC}"
        sudo zypper install -y python3-qt5 python3-pyusb python3-pip libusb-1_0-devel
        pip3 install --user requests cryptography Pillow colorlog sqlmodel ;;
    *)
        if echo "$DISTRO_LIKE" | grep -q "fedora\|rhel"; then
            install_fedora
        elif echo "$DISTRO_LIKE" | grep -q "debian\|ubuntu"; then
            install_debian
        else
            echo -e "${YELLOW}Unknown distro. Installing via pip only...${NC}"
            pip3 install --user pyusb pyserial PyQt5 requests cryptography Pillow colorlog sqlmodel
        fi
        ;;
esac

# ── udev Rules ────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Installing udev rules...${NC}"
cat > /tmp/51-mtk-devices.rules << 'EOF'
# MTK Client 2.0 — MediaTek Device Rules
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"
EOF

sudo mv /tmp/51-mtk-devices.rules /etc/udev/rules.d/
echo 'SUBSYSTEM=="usb", ACTION=="add", ATTR{idVendor}=="0e8d", ENV{ID_MM_DEVICE_IGNORE}="1"' \
    | sudo tee /etc/udev/rules.d/20-mm-blacklist-mtk.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger
echo -e "${GREEN}✓ udev rules installed${NC}"

# ── Groups ────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Adding $USER to plugdev and dialout groups...${NC}"
sudo usermod -aG plugdev "$USER" 2>/dev/null || true
sudo usermod -aG dialout "$USER" 2>/dev/null || true
echo -e "${GREEN}✓ Groups updated (re-login required)${NC}"

# ── ModemManager ──────────────────────────────────────────────────────────────
if command -v systemctl &>/dev/null; then
    if systemctl is-active ModemManager &>/dev/null; then
        echo -e "${YELLOW}Stopping ModemManager for this session...${NC}"
        sudo systemctl stop ModemManager
    fi
fi

# ── Desktop Entry ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p ~/.local/share/applications 2>/dev/null || true
cat > ~/.local/share/applications/mtkclient2.desktop << EOF
[Desktop Entry]
Name=MTK Client 2.0
Comment=MediaTek Flash & Repair Utility
Exec=python3 ${SCRIPT_DIR}/main.py
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;System;
EOF
echo -e "${GREEN}✓ Desktop entry created${NC}"

# ── Launch script ─────────────────────────────────────────────────────────────
cat > "${SCRIPT_DIR}/run.sh" << 'RUNEOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 main.py "$@"
RUNEOF
chmod +x "${SCRIPT_DIR}/run.sh"

echo -e "\n${GREEN}══════════════════════════════════════════"
echo "  MTK Client 2.0 installation complete!"
echo "══════════════════════════════════════════${NC}"
echo ""
echo -e "Launch with: ${CYAN}./run.sh${NC}"
echo -e "Or:          ${CYAN}python3 main.py${NC}"
echo ""
echo -e "${YELLOW}⚠  Log out and back in for group changes to take effect.${NC}"
echo -e "${YELLOW}⚠  On Fedora, disable Secure Boot or sign the kernel module if using"
echo "   hardware-level exploits (kamakiri, etc).${NC}"
