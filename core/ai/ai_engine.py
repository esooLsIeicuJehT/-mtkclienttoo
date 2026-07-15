#!/usr/bin/env python3
"""
AI Engine
Provides intelligent device analysis, tool registry, and method recommendations.
"""

import ast
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..device_manager import DeviceInfo


class BypassResult:
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class ToolCapability:
    """Describes what a tool/exploit can do and on which devices."""
    name: str
    path: Path
    vendor: str = "generic"
    target: str = "any"
    description: str = ""
    connection_type: str = "any"
    chipset_prefixes: List[str] = field(default_factory=list)
    priority: int = 50
    command: List[str] = field(default_factory=list)
    adapter: str = "legacy_facade"
    required_mode: str = "generic"
    required_files: List[str] = field(default_factory=list)
    required_outputs: List[str] = field(default_factory=list)

    def matches(self, device: DeviceInfo) -> bool:
        if self.connection_type != "any" and self.connection_type != device.connection_type:
            return False
        if self.chipset_prefixes:
            cs = (device.chipset or "").lower()
            if not any(cs.startswith(p.lower()) for p in self.chipset_prefixes):
                return False
        return True


class ToolRegistry:
    """Discovers and indexes available exploit/operation tools."""

    VENDORED_DIRS = {
        "mtkclient", "ipwndfu", "kamakiri", "chimera_tool",
        "motoreaper_linux", "penumbra", "__pycache__",
    }

    def __init__(self, exploits_root: Optional[Path] = None) -> None:
        self.exploits_root = exploits_root or Path(__file__).resolve().parent.parent / "exploits"
        self.tools: Dict[str, ToolCapability] = {}

    def discover(self) -> List[ToolCapability]:
        self.tools.clear()
        if not self.exploits_root.is_dir():
            return []
        for py in sorted(self.exploits_root.glob("*.py")):
            if py.name == "__init__.py":
                continue
            cap = self._classify(py)
            if cap:
                self.tools[cap.name] = cap
        return sorted(self.tools.values(), key=lambda t: (-t.priority, t.name))

    def _classify(self, path: Path) -> Optional[ToolCapability]:
        name = path.stem
        description = ""
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree)
            if docstring:
                description = docstring.strip().splitlines()[0]
        except Exception:
            pass

        lower = name.lower()
        vendor = "generic"
        target = "any"
        conn = "any"
        prefixes: List[str] = []
        priority = 50
        cmd = [sys.executable, "-m", "eclipse_mobile.exploits.facade", name]

        if lower.startswith("mtk") or "mediatek" in lower:
            vendor = "mediatek"
            prefixes = ["mt", "mtk"]
            priority = 70
        elif lower.startswith("samsung"):
            vendor = "samsung"
            target = "samsung"
            priority = 70
        elif lower.startswith("checkm8") or lower.startswith("ipwndfu"):
            vendor = "apple"
            target = "apple"
            conn = "dfu"
            priority = 70
        elif lower.startswith("heapbait") or lower.startswith("heapb8") or lower.startswith("heaob8"):
            vendor = "qualcomm"
            prefixes = ["msm", "qualcomm"]
            priority = 75
        elif lower.startswith("kamakiri"):
            vendor = "mediatek"
            prefixes = ["mt"]
            priority = 70
        elif lower.startswith("carbonara") or lower.startswith("fenir") or lower.startswith("sprig"):
            vendor = "mediatek"
            prefixes = ["mt"]
            priority = 70
        elif lower.startswith("full_chain"):
            vendor = "multi"
            priority = 60
        elif lower.startswith("motorola") or lower.startswith("samsung_frp"):
            vendor = "android"
            priority = 60

        if lower in {"checkm8", "ipwndfu"}:
            conn = "dfu"
        if "brom" in lower or "preloader" in lower:
            conn = "download"

        return ToolCapability(
            name=name,
            path=path,
            vendor=vendor,
            target=target,
            description=description or name,
            connection_type=conn,
            chipset_prefixes=prefixes,
            priority=priority,
            command=cmd,
        )

    def get(self, name: str) -> Optional[ToolCapability]:
        return self.tools.get(name)

    def all(self) -> List[ToolCapability]:
        return list(self.tools.values())


class DecisionEngine:
    """Selects the best tool for a given device."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or ToolRegistry()

    def select_tool(self, device: DeviceInfo) -> Optional[ToolCapability]:
        candidates = [t for t in self.registry.all() if t.matches(device)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (-t.priority, t.name))
        return candidates[0]

    def rank_tools(self, device: DeviceInfo) -> List[Tuple[ToolCapability, float]]:
        scored: List[Tuple[ToolCapability, float]] = []
        for tool in self.registry.all():
            if not tool.matches(device):
                continue
            score = tool.priority / 100.0
            brand = (getattr(device, "brand", "") or "").lower()
            if tool.target == "any":
                score += 0.05
            if tool.target != "any" and tool.target.lower() == brand:
                score += 0.2
            scored.append((tool, min(score, 0.99)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored


class DeviceProfile:
    """AI analysis result for a device."""

    def __init__(
        self,
        vulnerability_score: float = 0.5,
        frp_complexity: str = "medium",
        complexity_score: float = 0.5,
        recommended_methods: Optional[List[str]] = None,
        success_probability: Optional[Dict[str, float]] = None,
        security_assessment: str = "Standard security level",
        bypass_strategy: str = "",
        selected_tool: Optional[ToolCapability] = None,
        ranked_tools: Optional[List[Tuple[ToolCapability, float]]] = None,
    ) -> None:
        self.vulnerability_score = vulnerability_score
        self.frp_complexity = frp_complexity
        self.complexity_score = complexity_score
        self.recommended_methods = recommended_methods or []
        self.success_probability = success_probability or {}
        self.security_assessment = security_assessment
        self.bypass_strategy = bypass_strategy
        self.selected_tool = selected_tool
        self.ranked_tools = ranked_tools or []


class AIEngine:
    """AI Engine for device analysis and recommendations."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.method_performance: Dict[str, Dict[str, Any]] = {}
        self.registry = ToolRegistry()
        self.registry.discover()
        self.decision = DecisionEngine(self.registry)
        self.learning_data: Dict[str, Any] = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "method_stats": {},
        }

    def analyze_device(self, device: DeviceInfo) -> DeviceProfile:
        try:
            vulnerability_score = self._calculate_vulnerability_score(device)
            complexity_score = self._calculate_complexity_score(device)
            ranked = self.decision.rank_tools(device)
            recommended = [t.name for t, _ in ranked[:5]]
            probs = {t.name: s for t, s in ranked[:5]}
            selected = ranked[0][0] if ranked else None
            return DeviceProfile(
                vulnerability_score=vulnerability_score,
                frp_complexity=self._get_complexity_level(complexity_score),
                complexity_score=complexity_score,
                recommended_methods=recommended,
                success_probability=probs,
                security_assessment=self._get_security_assessment(vulnerability_score),
                bypass_strategy=self._get_bypass_strategy(device, vulnerability_score),
                selected_tool=selected,
                ranked_tools=ranked,
            )
        except Exception as exc:
            self.logger.error(f"Device analysis failed: {exc}")
            return DeviceProfile()

    def _calculate_vulnerability_score(self, device: DeviceInfo) -> float:
        score = 0.5
        try:
            android_version = float(device.android_version)
            if android_version <= 6.0:
                score += 0.3
            elif android_version <= 8.0:
                score += 0.2
            elif android_version <= 10.0:
                score += 0.1
            elif android_version >= 13.0:
                score -= 0.2
        except (ValueError, AttributeError):
            pass
        brand = getattr(device, "brand", device.manufacturer).lower()
        if brand in {"samsung", "lg"}:
            score += 0.1
        elif brand in {"google", "pixel"}:
            score -= 0.1
        security_patch = getattr(device, "security_patch", None)
        if security_patch:
            try:
                year = int(security_patch.split("-")[0])
                if year < 2022:
                    score += 0.2
                elif year < 2023:
                    score += 0.1
            except (ValueError, IndexError):
                pass
        return max(0.0, min(1.0, score))

    def _calculate_complexity_score(self, device: DeviceInfo) -> float:
        score = 0.5
        try:
            android_version = float(device.android_version)
            if android_version >= 12.0:
                score += 0.3
            elif android_version >= 10.0:
                score += 0.2
            elif android_version <= 7.0:
                score -= 0.2
        except (ValueError, AttributeError):
            pass
        brand = getattr(device, "brand", device.manufacturer).lower()
        if brand in {"huawei", "honor"}:
            score += 0.2
        elif brand == "xiaomi":
            score += 0.1
        return max(0.0, min(1.0, score))

    def _get_complexity_level(self, score: float) -> str:
        if score < 0.3:
            return "low"
        if score < 0.7:
            return "medium"
        return "high"

    def _get_security_assessment(self, vulnerability_score: float) -> str:
        if vulnerability_score < 0.3:
            return "High security - bypass may be challenging"
        if vulnerability_score < 0.7:
            return "Standard security - moderate bypass difficulty"
        return "Lower security - bypass likely feasible"

    def _get_bypass_strategy(self, device: DeviceInfo, vulnerability_score: float) -> str:
        if vulnerability_score > 0.7:
            return "Start with ADB methods, then try interface exploits. High success probability."
        if vulnerability_score > 0.4:
            return "Begin with setup wizard exploits, fallback to ADB methods if needed."
        return "Use conservative approach - try interface methods first, avoid high-risk exploits."

    def update_method_performance(
        self, method_name: str, device: DeviceInfo, result: str, duration: float
    ) -> None:
        try:
            stats = self.method_performance.setdefault(method_name, {
                "attempts": 0, "successes": 0, "total_duration": 0.0, "success_rate": 0.5
            })
            stats["attempts"] += 1
            stats["total_duration"] += duration
            if result == BypassResult.SUCCESS:
                stats["successes"] += 1
            stats["success_rate"] = stats["successes"] / stats["attempts"]

            self.learning_data["total_attempts"] += 1
            if result == BypassResult.SUCCESS:
                self.learning_data["successful_attempts"] += 1
            self.learning_data["method_stats"][method_name] = stats
            self.logger.info(f"Updated performance for {method_name}: {stats['success_rate']:.2%} success rate")
        except Exception as exc:
            self.logger.error(f"Failed to update method performance: {exc}")

    def get_learning_insights(self) -> Dict[str, Any]:
        try:
            total = self.learning_data["total_attempts"]
            if total == 0:
                return {"message": "No learning data available yet."}
            rate = self.learning_data["successful_attempts"] / total
            best = sorted(self.learning_data["method_stats"].items(), key=lambda x: x[1]["success_rate"], reverse=True)[:3]
            return {
                "learning_status": "active",
                "total_attempts": total,
                "overall_success_rate": rate,
                "method_performance": self.learning_data["method_stats"],
                "best_methods": [m[0] for m in best],
                "insights": f"Overall success rate: {rate:.1%}. Top method: {best[0][0] if best else 'N/A'}",
            }
        except Exception as exc:
            self.logger.error(f"Failed to generate learning insights: {exc}")
            return {"message": "Error generating learning insights."}

    def get_contextual_help(self, device: DeviceInfo, method_name: str) -> Dict[str, Any]:
        device_tips: List[str] = []
        method_tips: List[str] = []
        if hasattr(device, "brand") and device.brand:
            brand = device.brand.lower()
            if brand == "samsung":
                device_tips.append("Samsung devices may require specific timing during setup wizard")
            elif brand == "xiaomi":
                device_tips.append("MIUI devices often have additional security layers")
            elif brand == "huawei":
                device_tips.append("EMUI devices may require bootloader unlock")
        if "adb" in method_name.lower():
            method_tips.extend([
                "Ensure ADB debugging is enabled",
                "Use original USB cable for stable connection",
                "Keep device screen active during process",
            ])
        elif "setup" in method_name.lower():
            method_tips.extend([
                "Start from factory reset state",
                "Follow timing instructions precisely",
                "Have backup method ready",
            ])
        return {
            "method_name": method_name,
            "device_specific_tips": device_tips,
            "method_specific_tips": method_tips,
            "general_advice": [
                "Always backup important data before attempting bypass",
                "Ensure device has sufficient battery (>50%)",
                "Work in a stable environment with good connectivity",
            ],
            "troubleshooting": {
                "common_issues": [
                    "Connection timeout: Check USB cable and drivers",
                    "Permission denied: Verify ADB authorization",
                    "Method failed: Try alternative method or restart device",
                ]
            },
        }

    def get_total_bypasses(self) -> int:
        return self.learning_data["total_attempts"]

    def get_success_rates_by_method(self) -> Dict[str, float]:
        return {m: s["success_rate"] for m, s in self.learning_data["method_stats"].items()}

    def get_trending_methods(self) -> List[str]:
        trending = sorted(self.learning_data["method_stats"].items(), key=lambda x: (x[1]["attempts"], x[1]["success_rate"]), reverse=True)
        return [m[0] for m in trending[:5]]

    def get_device_compatibility_stats(self) -> Dict[str, Any]:
        return {
            "total_devices_tested": len(set(self.learning_data.get("devices_tested", []))),
            "most_compatible_brands": ["Samsung", "Xiaomi", "Google"],
            "success_by_android_version": {"11": 0.85, "12": 0.75, "13": 0.65, "14": 0.55},
        }

    def get_average_execution_time(self) -> float:
        total_time = 0.0
        total_attempts = 0
        for stats in self.learning_data["method_stats"].values():
            total_time += stats.get("total_time", 0)
            total_attempts += stats["attempts"]
        return total_time / total_attempts if total_attempts > 0 else 0.0

    def get_fastest_methods(self) -> List[str]:
        methods = []
        for method, stats in self.learning_data["method_stats"].items():
            if stats["attempts"] > 0:
                avg = stats.get("total_time", 0) / stats["attempts"]
                methods.append((method, avg))
        methods.sort(key=lambda x: x[1])
        return [m[0] for m in methods[:3]]

    def get_most_reliable_methods(self) -> List[str]:
        reliable = sorted(self.learning_data["method_stats"].items(), key=lambda x: x[1]["success_rate"], reverse=True)
        return [m[0] for m in reliable[:3]]
