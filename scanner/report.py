"""Report generator for Pre-flight Compatibility Scanner.
Renders honest, multi-dimensional capability reports.
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
        "capabilities": {
            "ui_framework": res.capabilities.ui_framework,
            "needs_bridge": res.capabilities.needs_bridge,
            "has_pager": res.capabilities.has_pager,
            "is_browser": res.capabilities.is_browser,
            "degraded_hardware": res.capabilities.degraded_hardware,
            "risk": res.capabilities.risk,
            "exact_risk_signatures": res.capabilities.exact_risk_signatures,
            "summary_tier": res.capabilities.summary_tier,
        },
        "tier": res.tier.name,
        "verdict": res.verdict.value,
        "blockers": res.blockers,
        "warnings": res.warnings,
        "framework_notes": res.framework_notes,
        "native_libs": res.native_libs_found,
        "dex_signatures": res.dex_signatures_found,
        "has_hardware_degradation": res.has_hardware_degradation,
        "degraded_hardware": res.degraded_hardware,
    }

def format_text_report(res: APKScanResult) -> str:
    lines = []
    bar = "=" * 70
    subbar = "-" * 70
    cap = res.capabilities

    lines.append(bar)
    lines.append(f"  PRE-FLIGHT CAPABILITY REPORT: {res.metadata.app_label or res.apk_path.name}")
    lines.append(bar)
    lines.append(f"  Package   : {res.metadata.package_name}")
    lines.append(f"  Version   : {res.metadata.version_name} (Code: {res.metadata.version_code})")
    lines.append(f"  SDK Target: Min {res.metadata.min_sdk} | Target {res.metadata.target_sdk}")
    lines.append(f"  Launchable: {res.metadata.launchable_activity}")
    lines.append(f"  Leanback  : {'Already present' if res.metadata.has_leanback_intent else 'Missing (Needs patch)'}")
    lines.append(subbar)

    # Multi-dimensional Capability Display
    framework_str = {
        "native": "Native Views / Jetpack Compose",
        "hybrid_webview": "Hybrid (WebView)",
        "flutter": "Flutter Engine",
        "react_native": "React Native",
        "canvas": "Custom Canvas / SurfaceView",
    }.get(cap.ui_framework, cap.ui_framework)

    if cap.has_pager:
        framework_str += " + Pager (swipe macro available)"

    type_str = "Browser -> pointer/auto mode for web content" if cap.is_browser else "Standard Application"
    bridge_str = "REQUIRED" if cap.needs_bridge else "NOT NEEDED (Pure Native)"
    
    if cap.degraded_hardware:
        hardware_str = ", ".join(cap.degraded_hardware) + " (optional features, will degrade)"
    else:
        hardware_str = "None (Full hardware compatibility)"

    lines.append(f"  Framework : {framework_str}")
    lines.append(f"  Type      : {type_str}")
    lines.append(f"  Bridge    : {bridge_str}")
    lines.append(f"  Hardware  : {hardware_str}")
    lines.append(f"  Risk      : {cap.risk}")
    lines.append(f"  Summary   : {cap.summary_tier}")
    lines.append(subbar)

    verdict_badge = {
        Verdict.PROCEED: "[ PASS - READY TO CONVERT ]",
        Verdict.WARN_RISKY: "[ WARN - RISKY (Requires --allow-risky) ]",
        Verdict.WARN_MANUAL: "[ WARN - MANUAL CALIBRATION NEEDED ]",
        Verdict.REJECT: "[ FAIL - DO NOT ATTEMPT CONVERSION ]",
    }[res.verdict]

    lines.append(f"  VERDICT   : {verdict_badge}")
    lines.append(subbar)

    if cap.risk == "soft_integrity":
        lines.append("  Soft Integrity Warning:")
        lines.append("    ! App contains integrity verification (Play Integrity / SafetyNet / RootBeer).")
        lines.append("    ! App may refuse login or some features after re-signing.")
        lines.append("    ! Risk to your account is possible. Proceed only if you accept it.")
        lines.append("    ! Pass --allow-risky to proceed with conversion.")
        lines.append("  Detected Risk Signatures:")
        for sig in cap.exact_risk_signatures:
            lines.append(f"    * {sig}")
        lines.append(subbar)
    elif cap.risk in ("hard_drm", "game"):
        lines.append("  Hard Blockers (Why conversion is rejected):")
        for sig in cap.exact_risk_signatures:
            lines.append(f"    X {sig}")
        lines.append(subbar)

    if res.framework_notes:
        lines.append("  Notes & Enhancements:")
        for note in res.framework_notes:
            lines.append(f"    * {note}")

    if res.dex_signatures_found:
        lines.append("  DEX / Library Markers:")
        for sig in sorted(set(res.dex_signatures_found))[:8]:
            lines.append(f"    - {sig}")

    lines.append(bar)
    return "\n".join(lines)
