"""Report generator for Pre-flight Compatibility Scanner.
"""
from typing import Dict, Any
from scanner.apk_inspector import APKScanResult
from scanner.rules import Tier, Verdict

def result_to_dict(res: APKScanResult) -> Dict[str, Any]:
    return {
        "apk_path": str(res.apk_path),
        "app_label": res.metadata.app_label,
        "package_name": res.metadata.package_name,
        "version_name": res.metadata.version_name,
        "version_code": res.metadata.version_code,
        "min_sdk": res.metadata.min_sdk,
        "target_sdk": res.metadata.target_sdk,
        "has_leanback_intent": res.metadata.has_leanback_intent,
        "tier": res.tier.name,
        "verdict": res.verdict.value,
        "blockers": res.blockers,
        "warnings": res.warnings,
        "framework_notes": res.framework_notes,
        "native_libs": res.native_libs_found,
        "dex_signatures": res.dex_signatures_found,
    }

def format_text_report(res: APKScanResult) -> str:
    lines = []
    bar = "=" * 70
    subbar = "-" * 70
    lines.append(bar)
    lines.append(f"  PRE-FLIGHT COMPATIBILITY REPORT: {res.metadata.app_label or res.apk_path.name}")
    lines.append(bar)
    lines.append(f"  Package:      {res.metadata.package_name}")
    lines.append(f"  Version:      {res.metadata.version_name} (Code: {res.metadata.version_code})")
    lines.append(f"  SDK Target:   Min {res.metadata.min_sdk} | Target {res.metadata.target_sdk}")
    lines.append(f"  Launchable:   {res.metadata.launchable_activity}")
    lines.append(f"  Leanback UI:  {'Already present' if res.metadata.has_leanback_intent else 'Missing (Needs patch)'}")
    lines.append(subbar)

    verdict_badge = {
        Verdict.PROCEED: "[ PASS - READY TO CONVERT ]",
        Verdict.WARN_MANUAL: "[ WARN - MANUAL CALIBRATION NEEDED ]",
        Verdict.REJECT: "[ FAIL - DO NOT ATTEMPT CONVERSION ]",
    }[res.verdict]

    tier_desc = {
        Tier.TIER_1_NATIVE_VIEWS: "Tier 1: Standard Android Views (Engine A Manifest Patch)",
        Tier.TIER_2_HYBRID_BRIDGE: "Tier 2: Hybrid / Cross-Platform (Engine A + Engine B Bridge)",
        Tier.TIER_3_GESTURE_MACRO: "Tier 3: Swipe / Feed Navigation (Engine A + Engine B + Gesture Macro)",
        Tier.TIER_4_CUSTOM_CANVAS: "Tier 4: Custom Canvas (Needs Hotspot Calibration, off by default)",
        Tier.TIER_5_HARDWARE_DEGRADED: "Tier 5: Hardware Degraded (Camera/GPS/Telephony absent on TV - Proceeds with warnings)",
        Tier.TIER_6_EXCLUDED: "Tier 6: Excluded / Incompatible (DRM, Anti-tamper, Real Game Engines)",
    }[res.tier]

    lines.append(f"  VERDICT:      {verdict_badge}")
    lines.append(f"  CATEGORY:     {tier_desc}")
    lines.append(subbar)

    if res.framework_notes:
        lines.append("  Detected Framework & UI Notes:")
        for note in res.framework_notes:
            lines.append(f"    * {note}")

    if res.dex_signatures_found:
        lines.append("  DEX / Library Markers:")
        for sig in sorted(set(res.dex_signatures_found))[:6]:
            lines.append(f"    - {sig}")

    if res.warnings:
        lines.append("  Warnings:")
        for w in res.warnings:
            lines.append(f"    ! {w}")

    if res.blockers:
        lines.append("  Hard Blockers (Why conversion is rejected):")
        for b in res.blockers:
            lines.append(f"    X {b}")

    lines.append(bar)
    return "\n".join(lines)
