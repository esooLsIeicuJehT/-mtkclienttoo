"""
MTK Chipset Database — single source of truth for all MediaTek SoCs.

Context Flow:
  HW Code (from BROM) → lookup() → ChipInfo
  ChipInfo → Protocol decisions, UI display, Kaeru compat, Payload URL

Coverage: MT62xx (2012) through MT6991 / Dimensity 9400+ (2025)
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChipInfo:
    hw_code:    int          # 16-bit BROM HW code (e.g. 0x6761)
    name:       str          # Canonical name e.g. "MT6761"
    marketing:  str          # e.g. "Helio A22"
    series:     str          # "Helio A/G/P/X", "Dimensity", "Tablet", "Legacy"
    arch:       str          # "ARMv7" | "AArch64" | "ARMv7+AArch64"
    process:    str          # fab node e.g. "28nm"
    cores:      str          # e.g. "4×A53"
    v6_protocol:    bool = False   # Uses V6 BROM auth protocol
    kaeru_compat:   bool = False   # ARMv7 LK → kaeru applicable
    lk_base:    int  = 0x48000000  # Typical LK load address
    brom_base:  int  = 0x00000000  # BROM memory base
    storage:    str  = "eMMC"      # "eMMC" | "UFS" | "NAND"
    payload_url: str = ""          # mtkclient payload for this chip
    notes:      str = ""

    @property
    def display_name(self) -> str:
        if self.marketing and self.marketing != self.name:
            return f"{self.name}  ({self.marketing})"
        return self.name


# ── Payload base URL ──────────────────────────────────────────────────────────
_PL = "https://raw.githubusercontent.com/bkerler/mtkclient/main/mtkclient/payloads/"

# ─────────────────────────────────────────────────────────────────────────────
# CHIPSET DATABASE
# Ordered by hw_code (hex value)
# ─────────────────────────────────────────────────────────────────────────────
_CHIPS_RAW = [

    # ── Legacy 2G/3G feature phone SoCs (pre-2013) ───────────────────────────
    ChipInfo(0x6252, "MT6252", "MT6252", "Legacy", "ARMv7", "90nm", "1×ARM7",
             lk_base=0x40000000, brom_base=0x00000000, storage="NAND",
             notes="Feature phone, very old"),
    ChipInfo(0x6260, "MT6260", "MT6260", "Legacy", "ARMv7", "90nm", "1×ARM7",
             kaeru_compat=False, lk_base=0x40000000, storage="NAND"),
    ChipInfo(0x6261, "MT6261", "MT6261", "Legacy", "ARMv7", "90nm", "1×ARM7",
             kaeru_compat=False, lk_base=0x40000000, storage="NAND"),
    ChipInfo(0x6268, "MT6268", "MT6268", "Legacy", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000),

    # ── MT627x / MT628x series (2013-2015 budget) ────────────────────────────
    ChipInfo(0x6572, "MT6572", "MT6572", "Legacy", "ARMv7", "28nm", "2×A7",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt6572_payload.bin"),
    ChipInfo(0x6573, "MT6573", "MT6573", "Legacy", "ARMv7", "40nm", "1×ARM11",
             kaeru_compat=False, lk_base=0x40000000),
    ChipInfo(0x6575, "MT6575", "MT6575", "Legacy", "ARMv7", "40nm", "1×A9",
             kaeru_compat=False, lk_base=0x40000000),
    ChipInfo(0x6577, "MT6577", "MT6577", "Legacy", "ARMv7", "40nm", "2×A9",
             kaeru_compat=False, lk_base=0x40000000),
    ChipInfo(0x6580, "MT6580", "MT6580", "Legacy", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6580_payload.bin"),
    ChipInfo(0x6582, "MT6582", "MT6582", "Legacy", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt6582_payload.bin"),
    ChipInfo(0x6585, "MT6585", "MT6585", "Legacy", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000),
    ChipInfo(0x6589, "MT6589", "MT6589", "Legacy", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt6589_payload.bin"),
    ChipInfo(0x6592, "MT6592", "MT6592", "Legacy", "ARMv7", "28nm", "8×A7",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt6592_payload.bin"),
    ChipInfo(0x6595, "MT6595", "MT6595", "Legacy", "ARMv7+AArch64", "20nm", "4×A17+4×A7",
             kaeru_compat=True, lk_base=0x40000000),

    # ── MT673x / Helio X series (2015-2016 mid-range) ────────────────────────
    ChipInfo(0x6732, "MT6732", "MT6732", "Helio", "ARMv7+AArch64", "28nm", "4×A53",
             kaeru_compat=True, lk_base=0x41000000),
    ChipInfo(0x6735, "MT6735", "MT6735", "Helio", "ARMv7+AArch64", "28nm", "4×A53",
             kaeru_compat=True, lk_base=0x41000000,
             payload_url=_PL + "mt6735_payload.bin"),
    ChipInfo(0x6737, "MT6737", "Helio P10/P15", "Helio P", "ARMv7+AArch64", "28nm", "4×A53",
             kaeru_compat=True, lk_base=0x41000000,
             payload_url=_PL + "mt6737_payload.bin"),
    ChipInfo(0x6738, "MT6738", "Helio P22", "Helio P", "ARMv7+AArch64", "12nm", "8×A53",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x6739, "MT6739", "Helio A22 (entry)", "Helio A", "ARMv7+AArch64", "28nm", "4×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6739_payload.bin"),

    # ── MT675x / Helio P series (2016-2018) ──────────────────────────────────
    ChipInfo(0x6750, "MT6750", "Helio P10/P15", "Helio P", "AArch64", "28nm", "4×A53+4×A53",
             kaeru_compat=True, lk_base=0x41000000,
             payload_url=_PL + "mt6750_payload.bin"),
    ChipInfo(0x6752, "MT6752", "Helio (MT6752)", "Helio", "AArch64", "28nm", "8×A53",
             kaeru_compat=True, lk_base=0x40000000),
    ChipInfo(0x6753, "MT6753", "Helio (MT6753)", "Helio", "AArch64", "28nm", "8×A53",
             kaeru_compat=True, lk_base=0x41000000,
             payload_url=_PL + "mt6753_payload.bin"),
    ChipInfo(0x6755, "MT6755", "Helio P10", "Helio P", "AArch64", "28nm", "8×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6755_payload.bin"),
    ChipInfo(0x6757, "MT6757", "Helio P25", "Helio P", "AArch64", "16nm", "4×A53+4×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6757_payload.bin"),
    ChipInfo(0x6758, "MT6758", "Helio P30", "Helio P", "AArch64", "16nm", "4×A53+4×A53",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x6759, "MT6759", "Helio P23", "Helio P", "AArch64", "16nm", "4×A53+4×A53",
             kaeru_compat=True, lk_base=0x48000000),

    # ── MT676x / Helio A/G series (2019-2021) ────────────────────────────────
    ChipInfo(0x6761, "MT6761", "Helio A22", "Helio A", "AArch64", "12nm", "4×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6761_payload.bin"),
    ChipInfo(0x6762, "MT6762", "Helio P22", "Helio P", "AArch64", "12nm", "8×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6762_payload.bin"),
    ChipInfo(0x6763, "MT6763", "Helio P23", "Helio P", "AArch64", "16nm", "8×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6763_payload.bin"),
    ChipInfo(0x6765, "MT6765", "Helio G35/P35", "Helio G", "AArch64", "12nm", "8×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6765_payload.bin"),
    ChipInfo(0x6768, "MT6768", "Helio G85/P65", "Helio G", "AArch64", "12nm", "2×A75+6×A55",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6768_payload.bin"),
    ChipInfo(0x6769, "MT6769", "Helio G85 (v2)", "Helio G", "AArch64", "12nm", "2×A75+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x6771, "MT6771", "Helio P60/P70", "Helio P", "AArch64", "12nm", "4×A73+4×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6771_payload.bin"),
    ChipInfo(0x6779, "MT6779", "Helio P90", "Helio P", "AArch64", "12nm", "4×A75+4×A55",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6779_payload.bin"),
    ChipInfo(0x6781, "MT6781", "Helio G90T", "Helio G", "AArch64", "12nm", "2×A75+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x6785, "MT6785", "Helio G90T/G95", "Helio G", "AArch64", "12nm", "2×A76+6×A55",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6785_payload.bin"),
    ChipInfo(0x6789, "MT6789", "Helio G99 / G100", "Helio G", "AArch64", "6nm", "2×A78+6×A55",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6789_payload.bin"),

    # ── MT678x / Helio G99 Ultra / G100 ──────────────────────────────────────
    ChipInfo(0x6797, "MT6797", "Helio X20", "Helio X", "AArch64", "20nm", "2×A72+4×A53+4×A35",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt6797_payload.bin"),
    ChipInfo(0x6799, "MT6799", "Helio X30", "Helio X", "AArch64", "10nm", "2×A73+4×A53+4×A35",
             kaeru_compat=True, lk_base=0x48000000),

    # ── MT6833 / Dimensity 6xx series ────────────────────────────────────────
    ChipInfo(0x6833, "MT6833", "Dimensity 700", "Dimensity", "AArch64", "7nm", "2×A76+6×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6833_payload.bin",
             notes="V6 auth protocol; kaeru requires patched BROM"),
    ChipInfo(0x6835, "MT6835", "Dimensity 6100+", "Dimensity", "AArch64", "6nm", "2×A76+6×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6855, "MT6855", "Dimensity 7050", "Dimensity", "AArch64", "6nm", "2×A78+6×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),

    # ── MT685x / Dimensity 7xx (2021-2023) ───────────────────────────────────
    ChipInfo(0x6853, "MT6853", "Dimensity 720 / 800U", "Dimensity", "AArch64", "7nm", "2×A76+6×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6853_payload.bin"),
    ChipInfo(0x6873, "MT6873", "Dimensity 800", "Dimensity", "AArch64", "7nm", "4×A76+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6873_payload.bin"),
    ChipInfo(0x6875, "MT6875", "Dimensity 800U", "Dimensity", "AArch64", "7nm", "4×A76+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6877, "MT6877", "Dimensity 900", "Dimensity", "AArch64", "6nm", "2×A78+6×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6877_payload.bin"),
    ChipInfo(0x6879, "MT6879", "Dimensity 1080", "Dimensity", "AArch64", "6nm", "2×A78+6×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6880, "MT6880", "Dimensity 800", "Dimensity", "AArch64", "7nm", "4×A76+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),

    # ── MT688x / Dimensity 1000 series ───────────────────────────────────────
    ChipInfo(0x6883, "MT6883", "Dimensity 1000L", "Dimensity", "AArch64", "7nm", "4×A77+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6883_payload.bin"),
    ChipInfo(0x6885, "MT6885", "Dimensity 1000+", "Dimensity", "AArch64", "7nm", "4×A77+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6885_payload.bin"),
    ChipInfo(0x6889, "MT6889", "Dimensity 1000", "Dimensity", "AArch64", "7nm", "4×A77+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),

    # ── MT689x / Dimensity 1200 series ───────────────────────────────────────
    ChipInfo(0x6891, "MT6891", "Dimensity 1100", "Dimensity", "AArch64", "6nm", "4×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6893, "MT6893", "Dimensity 1200", "Dimensity", "AArch64", "6nm", "1×A78+3×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6893_payload.bin"),
    ChipInfo(0x6895, "MT6895", "Dimensity 8100", "Dimensity", "AArch64", "5nm", "4×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6895_payload.bin"),
    ChipInfo(0x6896, "MT6896", "Dimensity 1300", "Dimensity", "AArch64", "6nm", "1×A78+3×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6897, "MT6897", "Dimensity 8200", "Dimensity", "AArch64", "4nm", "1×A78+3×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6899, "MT6899", "Dimensity 8300", "Dimensity", "AArch64", "4nm", "1×A715+3×A715+4×A510",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),

    # ── MT698x / Dimensity 9000 series ───────────────────────────────────────
    ChipInfo(0x6983, "MT6983", "Dimensity 9000", "Dimensity", "AArch64", "4nm", "1×X2+3×A710+4×A510",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt6983_payload.bin"),
    ChipInfo(0x6985, "MT6985", "Dimensity 9200", "Dimensity", "AArch64", "4nm", "1×X3+3×A715+4×A510",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS"),
    ChipInfo(0x6986, "MT6986", "Dimensity 9300", "Dimensity", "AArch64", "4nm", "4×X4+4×A720",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6989, "MT6989", "Dimensity 9300+", "Dimensity", "AArch64", "4nm", "1×X4+3×X4+4×A720",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x6991, "MT6991", "Dimensity 9400", "Dimensity", "AArch64", "3nm", "1×X925+3×X925+4×A725",
             v6_protocol=True, kaeru_compat=False, storage="UFS",
             notes="Newest 2025 flagship"),

    # ── Tablet SoCs ───────────────────────────────────────────────────────────
    ChipInfo(0x8127, "MT8127", "MT8127 (Tablet)", "Tablet", "ARMv7", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt8127_payload.bin"),
    ChipInfo(0x8135, "MT8135", "MT8135 (Tablet)", "Tablet", "ARMv7+AArch64", "28nm", "4×A15+4×A7",
             kaeru_compat=True, lk_base=0x40000000),
    ChipInfo(0x8163, "MT8163", "MT8163 (Tablet)", "Tablet", "AArch64", "28nm", "4×A53",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt8163_payload.bin"),
    ChipInfo(0x8167, "MT8167", "MT8167 (Tablet)", "Tablet", "AArch64", "28nm", "4×A35",
             kaeru_compat=True, lk_base=0x40000000),
    ChipInfo(0x8173, "MT8173", "MT8173 (Tablet)", "Tablet", "AArch64", "28nm", "2×A72+2×A53",
             kaeru_compat=True, lk_base=0x40000000,
             payload_url=_PL + "mt8173_payload.bin"),
    ChipInfo(0x8183, "MT8183", "Helio P60T (Tablet)", "Tablet", "AArch64", "12nm", "4×A73+4×A53",
             kaeru_compat=True, lk_base=0x48000000,
             payload_url=_PL + "mt8183_payload.bin"),
    ChipInfo(0x8185, "MT8185", "MT8185 (Tablet)", "Tablet", "AArch64", "12nm", "2×A72+6×A53",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8192, "MT8192", "Kompanio 820 (Tablet)", "Tablet", "AArch64", "6nm", "4×A76+4×A55",
             v6_protocol=True, kaeru_compat=False, lk_base=0x48000000, storage="UFS",
             payload_url=_PL + "mt8192_payload.bin"),
    ChipInfo(0x8195, "MT8195", "Kompanio 1200 (Tablet)", "Tablet", "AArch64", "6nm", "4×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS",
             payload_url=_PL + "mt8195_payload.bin"),
    ChipInfo(0x8321, "MT8321", "MT8321 (Budget Tablet)", "Tablet", "AArch64", "28nm", "4×A7",
             kaeru_compat=True, lk_base=0x40000000),
    ChipInfo(0x8765, "MT8765", "MT8765 (Tablet)", "Tablet", "AArch64", "12nm", "4×A53",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8768, "MT8768", "Helio G85 (Tablet)", "Tablet", "AArch64", "12nm", "2×A75+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8781, "MT8781", "Helio G99 (Tablet)", "Tablet", "AArch64", "6nm", "2×A76+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8786, "MT8786", "Helio G85 Tablet", "Tablet", "AArch64", "12nm", "2×A75+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8788, "MT8788", "Helio G90T (Tablet)", "Tablet", "AArch64", "12nm", "2×A76+6×A55",
             kaeru_compat=True, lk_base=0x48000000),
    ChipInfo(0x8791, "MT8791", "Dimensity 900 (Tablet)", "Tablet", "AArch64", "6nm", "2×A78+6×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
    ChipInfo(0x8797, "MT8797", "Dimensity 1300 (Tablet)", "Tablet", "AArch64", "6nm", "1×A78+3×A78+4×A55",
             v6_protocol=True, kaeru_compat=False, storage="UFS"),
]

# ── Primary lookup index: hw_code → ChipInfo ─────────────────────────────────
CHIPSET_DB: dict[int, ChipInfo] = {c.hw_code: c for c in _CHIPS_RAW}

# ── Name index: "MT6761" / "mt6761" → ChipInfo ───────────────────────────────
_NAME_INDEX: dict[str, ChipInfo] = {}
for _c in _CHIPS_RAW:
    _NAME_INDEX[_c.name.lower()] = _c
    _NAME_INDEX[_c.name.upper()] = _c

# ── V6 threshold: HW codes at or above this need V6 BROM auth protocol ───────
V6_THRESHOLD = 0x6853


def lookup(hw_code: int) -> Optional[ChipInfo]:
    """Return ChipInfo for a given HW code, or None."""
    return CHIPSET_DB.get(hw_code)


def lookup_by_name(name: str) -> Optional[ChipInfo]:
    """Return ChipInfo by SoC name string (case-insensitive)."""
    return _NAME_INDEX.get(name.strip().lower()) or _NAME_INDEX.get(name.strip().upper())


def is_v6(hw_code: int) -> bool:
    """True if this chipset requires V6 BROM auth protocol."""
    chip = CHIPSET_DB.get(hw_code)
    if chip:
        return chip.v6_protocol
    return hw_code >= V6_THRESHOLD


def is_kaeru_compatible(hw_code: int) -> bool:
    """True if kaeru (ARMv7 LK payload) can theoretically run on this chip."""
    chip = CHIPSET_DB.get(hw_code)
    if chip:
        return chip.kaeru_compat
    # Unknown chip: assume old = compatible if below V6 threshold
    return hw_code < V6_THRESHOLD


def get_lk_base(hw_code: int) -> int:
    """Return typical LK base address for this chipset."""
    chip = CHIPSET_DB.get(hw_code)
    return chip.lk_base if chip else 0x48000000


def get_payload_url(hw_code: int) -> str:
    """Return payload download URL, or empty string if unknown."""
    chip = CHIPSET_DB.get(hw_code)
    return chip.payload_url if chip else ""


def all_chips() -> list[ChipInfo]:
    """Return all chips sorted by HW code."""
    return sorted(_CHIPS_RAW, key=lambda c: c.hw_code)


def kaeru_compatible_chips() -> list[ChipInfo]:
    """Return chips that are potentially kaeru-compatible (ARMv7 LK)."""
    return [c for c in _CHIPS_RAW if c.kaeru_compat]


# ── Chipset family → LK base address table ───────────────────────────────────
# Used by kaeru defconfig generator when exact chip is unknown
LK_BASE_BY_FAMILY = {
    "Legacy":    0x40000000,
    "Helio A":   0x48000000,
    "Helio G":   0x48000000,
    "Helio P":   0x48000000,
    "Helio X":   0x48000000,
    "Dimensity": 0x48000000,
    "Tablet":    0x40000000,
}

# ── Standard MTK partition names (most devices have these) ───────────────────
STANDARD_PARTITIONS = [
    "preloader", "pgpt", "sgpt", "proinfo",
    "nvram", "protect1", "protect2",
    "seccfg", "lk", "lk2",
    "boot", "recovery", "frp",
    "para", "logo", "expdb",
    "tee1", "tee2",
    "system", "vendor", "product",
    "userdata", "cache", "metadata",
    "md1img", "md3img",
    "spmfw", "sspm_1", "sspm_2",
    "mcupm_1", "mcupm_2",
    "gz1", "gz2",
    "persist", "misc", "odm",
    "super", "dtbo", "vbmeta", "vbmeta_system",
]

# ── Kaeru defconfig templates by chipset family ───────────────────────────────
# Filled with best-known defaults; user must verify with Ghidra/hexdump
KAERU_DEFCONFIG_TEMPLATES = {
    0x6580: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0xA0000,
                 APP_ADDRESS=0x4800F000, FASTBOOT_CONTINUE=0x48010000,
                 BOOTMODE_ADDRESS=0x480A0000),
    0x6735: dict(BOOTLOADER_BASE=0x41000000, BOOTLOADER_SIZE=0xB0000,
                 APP_ADDRESS=0x4100F000, FASTBOOT_CONTINUE=0x41010000,
                 BOOTMODE_ADDRESS=0x410A0000),
    0x6737: dict(BOOTLOADER_BASE=0x41000000, BOOTLOADER_SIZE=0xB0000,
                 APP_ADDRESS=0x4100F000, FASTBOOT_CONTINUE=0x41010000,
                 BOOTMODE_ADDRESS=0x410A0000),
    0x6761: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0xD5000,
                 APP_ADDRESS=0x4801F000, FASTBOOT_CONTINUE=0x48021000,
                 BOOTMODE_ADDRESS=0x480D7000),
    0x6765: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0xE0000,
                 APP_ADDRESS=0x48020000, FASTBOOT_CONTINUE=0x48022000,
                 BOOTMODE_ADDRESS=0x480D8000),
    0x6768: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0xF0000,
                 APP_ADDRESS=0x48022000, FASTBOOT_CONTINUE=0x48024000,
                 BOOTMODE_ADDRESS=0x480DC000),
    0x6785: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0x100000,
                 APP_ADDRESS=0x48025000, FASTBOOT_CONTINUE=0x48027000,
                 BOOTMODE_ADDRESS=0x480E0000),
    0x6789: dict(BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0x110000,
                 APP_ADDRESS=0x48028000, FASTBOOT_CONTINUE=0x4802A000,
                 BOOTMODE_ADDRESS=0x480E5000),
}

# Default fallback for unknown chips
KAERU_DEFAULT_DEFCONFIG = dict(
    BOOTLOADER_BASE=0x48000000, BOOTLOADER_SIZE=0x100000,
    APP_ADDRESS=0x48020000, FASTBOOT_CONTINUE=0x48022000,
    BOOTMODE_ADDRESS=0x480D0000
)
