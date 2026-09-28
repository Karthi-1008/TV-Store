"""Rapid APK inspection using aapt2 and DEX/ZIP binary inspection.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import zipfile
from typing import List, Dict, Set, Optional

import config
from scanner.rules import (
    Tier, Verdict, Capabilities,
    DEGRADABLE_HARDWARE_FEATURES,
    HARD_DRM_SIGNATURES,
    SOFT_INTEGRITY_SIGNATURES,
    GAME_ENGINE_NATIVE_LIBS,
    GAME_ENGINE_DEX_SIGNATURES,
    HYBRID_NATIVE_LIBS,
    HYBRID_DEX_SIGNATURES,
    SWIPE_FEED_SIGNATURES,
    NATIVE_VIEW_SIGNATURES,
)

@dataclass
class APKMetadata:
    package_name: str = ""
    version_code: str = ""
    version_name: str = ""
    min_sdk: str = ""
    target_sdk: str = ""
    app_label: str = ""
    icon_path: str = ""
    banner_path: str = ""
    launchable_activity: str = ""
    has_leanback_intent: bool = False
    permissions: List[str] = field(default_factory=list)
    required_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)
    native_abis: List[str] = field(default_factory=list)
    uses_gl_es: str = ""

@dataclass
class APKScanResult:
    apk_path: Path
    metadata: APKMetadata
    capabilities: Capabilities
    tier: Tier
    verdict: Verdict
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    framework_notes: List[str] = field(default_factory=list)
    native_libs_found: List[str] = field(default_factory=list)
    dex_signatures_found: List[str] = field(default_factory=list)
    has_hardware_degradation: bool = False
    degraded_hardware: List[tuple[str, str]] = field(default_factory=list)

def extract_badging_metadata(apk_path: Path) -> APKMetadata:
    """Use aapt2 dump badging to extract manifest info quickly."""
    meta = APKMetadata()
    if not config.AAPT2_EXE or not config.AAPT2_EXE.exists():
        raise RuntimeError("aapt2 binary not found in build-tools.")

    cmd = [str(config.AAPT2_EXE), "dump", "badging", str(apk_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"aapt2 failed on {apk_path.name}: {result.stderr}")

    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            m_pkg = re.search(r"name='([^']+)'", line)
            m_vcode = re.search(r"versionCode='([^']+)'", line)
            m_vname = re.search(r"versionName='([^']+)'", line)
            if m_pkg: meta.package_name = m_pkg.group(1)
            if m_vcode: meta.version_code = m_vcode.group(1)
            if m_vname: meta.version_name = m_vname.group(1)
        elif line.startswith("minSdkVersion:"):
            m = re.search(r"'([^']+)'", line)
            if m: meta.min_sdk = m.group(1)
        elif line.startswith("targetSdkVersion:"):
            m = re.search(r"'([^']+)'", line)
            if m: meta.target_sdk = m.group(1)
        elif line.startswith("application-label:"):
            m = re.search(r"'([^']+)'", line)
            if m and not meta.app_label: meta.app_label = m.group(1)
        elif line.startswith("application:") and not meta.app_label:
            m = re.search(r"label='([^']+)'", line)
            if m: meta.app_label = m.group(1)
        elif line.startswith("application-icon-") or line.startswith("application:"):
            m_icon = re.search(r"icon='([^']+)'", line)
            if m_icon and not meta.icon_path:
                meta.icon_path = m_icon.group(1)
            m_banner = re.search(r"banner='([^']+)'", line)
            if m_banner and not meta.banner_path:
                meta.banner_path = m_banner.group(1)
        elif line.startswith("launchable-activity:"):
            m = re.search(r"name='([^']+)'", line)
            if m and not meta.launchable_activity:
                meta.launchable_activity = m.group(1)
        elif line.startswith("leanback-launchable-activity:"):
            meta.has_leanback_intent = True
        elif line.startswith("uses-permission:"):
            m = re.search(r"name='([^']+)'", line)
            if m: meta.permissions.append(m.group(1))
        elif line.startswith("uses-feature:"):
            m = re.search(r"name='([^']+)'", line)
            if m: meta.required_features.append(m.group(1))
        elif line.startswith("uses-feature-not-required:"):
            m = re.search(r"name='([^']+)'", line)
            if m: meta.optional_features.append(m.group(1))
        elif line.startswith("uses-gl-es:"):
            m = re.search(r"'([^']+)'", line)
            if m: meta.uses_gl_es = m.group(1)
        elif line.startswith("native-code:"):
            abis = re.findall(r"'([^']+)'", line)
            meta.native_abis.extend(abis)

    return meta

def check_is_browser(apk_path: Path) -> bool:
    """Detect if APK registers as a web browser via APP_BROWSER or VIEW+BROWSABLE with http(s)."""
    if not config.AAPT2_EXE or not config.AAPT2_EXE.exists():
        return False
    try:
        cmd = [str(config.AAPT2_EXE), "dump", "xmltree", str(apk_path), "--file", "AndroidManifest.xml"]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
        if result.returncode != 0:
            return False
        tree = result.stdout
        if "android.intent.category.APP_BROWSER" in tree:
            return True
        # Split on intent/intent-filter tags
        filters = re.split(r"E:\s+intent(?:-filter)?", tree)
        for f in filters[1:]:
            if "android.intent.action.VIEW" in f and "android.intent.category.BROWSABLE" in f:
                if ('"http"' in f or '"https"' in f or 'scheme(0x01010027)="http"' in f or 'scheme(0x01010027)="https"' in f):
                    return True
    except Exception:
        pass
    return False

def scan_apk(apk_path: Path) -> APKScanResult:
    """Run full Phase 0 pre-flight capability scan on the provided APK file."""
    apk_path = Path(apk_path).resolve()
    if not apk_path.exists():
        raise FileNotFoundError(f"APK file not found: {apk_path}")

    metadata = extract_badging_metadata(apk_path)
    is_browser = check_is_browser(apk_path)

    blockers: List[str] = []
    warnings: List[str] = []
    framework_notes: List[str] = []
    native_libs_found: List[str] = []
    dex_signatures_found: List[str] = []
    exact_risk_signatures: List[str] = []

    # 1. Check Hardware Features in Manifest for Graceful Degradation
    degraded_features: List[tuple[str, str]] = []
    for feat in metadata.required_features:
        if feat in DEGRADABLE_HARDWARE_FEATURES:
            degraded_features.append((feat, DEGRADABLE_HARDWARE_FEATURES[feat]))

    # 2. Inspect ZIP contents (native libs & DEX strings)
    is_game = False
    is_flutter = False
    is_react_native = False
    is_webview = False
    is_swipe_feed = False
    has_native_views = False
    has_hard_drm = False
    has_soft_integrity = False

    with zipfile.ZipFile(apk_path, 'r') as zf:
        namelist = zf.namelist()
        
        # Check native libraries in lib/
        so_files = {Path(p).name for p in namelist if p.startswith("lib/") and p.endswith(".so")}
        native_libs_found = sorted(list(so_files))

        for lib_name in so_files:
            if lib_name in GAME_ENGINE_NATIVE_LIBS:
                is_game = True
                desc = GAME_ENGINE_NATIVE_LIBS[lib_name]
                exact_risk_signatures.append(f"{lib_name} ({desc})")
                blockers.append(f"Game Engine Library: {lib_name} ({desc})")
            if lib_name in HYBRID_NATIVE_LIBS:
                desc = HYBRID_NATIVE_LIBS[lib_name]
                framework_notes.append(f"Hybrid Engine Library: {lib_name} ({desc})")
                if "flutter" in lib_name:
                    is_flutter = True
                elif "react" in lib_name or "hermes" in lib_name:
                    is_react_native = True

        # Scan DEX files for signatures
        dex_files = [p for p in namelist if p.startswith("classes") and p.endswith(".dex")]
        for dex_name in dex_files:
            try:
                dex_bytes = zf.read(dex_name)
            except Exception as e:
                warnings.append(f"Failed to read {dex_name}: {e}")
                continue

            # Check Hard DRM
            for sig, desc in HARD_DRM_SIGNATURES.items():
                if sig in dex_bytes:
                    has_hard_drm = True
                    sig_str = sig.decode('ascii', errors='ignore')
                    exact_risk_signatures.append(f"Hard DRM: {desc} [{sig_str}]")
                    blockers.append(f"Hard DRM / Anti-Tamper: {desc} [{sig_str}]")

            # Check Soft Integrity
            for sig, desc in SOFT_INTEGRITY_SIGNATURES.items():
                if sig in dex_bytes:
                    has_soft_integrity = True
                    sig_str = sig.decode('ascii', errors='ignore')
                    if sig_str not in [s.split('[')[-1].rstrip(']') for s in exact_risk_signatures]:
                        exact_risk_signatures.append(f"Soft Integrity: {desc} [{sig_str}]")
                        warnings.append(f"Soft Integrity Library: {desc} [{sig_str}]")

            # Check Game DEX signatures
            for sig, desc in GAME_ENGINE_DEX_SIGNATURES.items():
                if sig in dex_bytes:
                    is_game = True
                    exact_risk_signatures.append(f"Game Framework: {desc}")
                    blockers.append(f"Game Framework Detected: {desc}")

            # Check Hybrid DEX signatures
            for sig, desc in HYBRID_DEX_SIGNATURES.items():
                if sig in dex_bytes:
                    dex_signatures_found.append(f"Hybrid: {desc}")
                    if sig == b"io/flutter/embedding":
                        is_flutter = True
                    elif sig == b"com/facebook/react":
                        is_react_native = True
                    elif sig == b"android/webkit/WebView" or sig == b"org/apache/cordova" or sig == b"com/getcapacitor":
                        is_webview = True

            # Check Swipe / ViewPager2
            for sig, desc in SWIPE_FEED_SIGNATURES.items():
                if sig in dex_bytes:
                    is_swipe_feed = True
                    dex_signatures_found.append(f"Swipe/Pager: {desc}")

            # Check Native Views / Compose
            for sig, desc in NATIVE_VIEW_SIGNATURES.items():
                if sig in dex_bytes:
                    has_native_views = True
                    dex_signatures_found.append(f"Native Views: {desc}")

    # OpenGL ES check for Games vs Custom Canvas
    is_ambiguous_canvas = False
    if metadata.uses_gl_es and not has_native_views and not (is_flutter or is_react_native or is_webview):
        warnings.append(f"App declares OpenGL ES version {metadata.uses_gl_es} without standard widgets.")
        if "game" in metadata.package_name.lower():
            is_game = True
            blockers.append("Package name and OpenGL-only rendering suggest a game engine.")
            exact_risk_signatures.append("Game: OpenGL-only rendering with 'game' in package name")
        else:
            is_ambiguous_canvas = True
            warnings.append("Could not confirm standard UI framework; app may need manual hotspot calibration (Tier 4).")

    # Determine UI Framework string
    if is_flutter:
        ui_framework = "flutter"
    elif is_react_native:
        ui_framework = "react_native"
    elif is_webview:
        ui_framework = "hybrid_webview"
    elif is_ambiguous_canvas:
        ui_framework = "canvas"
    else:
        ui_framework = "native"

    # Evaluate Risk Level and Verdict
    # Verdict comes ONLY from risk. Framework/pager/browser/hardware never cause rejection.
    if has_hard_drm:
        risk = "hard_drm"
        verdict = Verdict.REJECT
        tier = Tier.TIER_5_EXCLUDED
        summary_tier = "Tier 5 (Excluded: Hard DRM)"
    elif is_game:
        risk = "game"
        verdict = Verdict.REJECT
        tier = Tier.TIER_5_EXCLUDED
        summary_tier = "Tier 5 (Excluded: Game Engine)"
    elif has_soft_integrity:
        risk = "soft_integrity"
        verdict = Verdict.WARN_RISKY
        # summary tier determined by UI features
        if ui_framework != "native" and is_swipe_feed:
            summary_tier = "Tier 2 + Tier 3 features"
            tier = Tier.TIER_2_HYBRID_BRIDGE
        elif is_swipe_feed:
            summary_tier = "Tier 1 + Tier 3 features"
            tier = Tier.TIER_3_GESTURE_MACRO
        elif ui_framework != "native":
            summary_tier = f"Tier 2 ({ui_framework.replace('_', ' ').title()})"
            tier = Tier.TIER_2_HYBRID_BRIDGE
        else:
            summary_tier = "Tier 1 (Native Views)"
            tier = Tier.TIER_1_NATIVE_VIEWS
    elif is_ambiguous_canvas:
        risk = "ambiguous_canvas"
        verdict = Verdict.WARN_MANUAL
        tier = Tier.TIER_4_CUSTOM_CANVAS
        summary_tier = "Tier 4 (Custom Canvas)"
    else:
        risk = "none"
        verdict = Verdict.PROCEED
        if ui_framework != "native" and is_swipe_feed:
            summary_tier = "Tier 2 + Tier 3 features"
            tier = Tier.TIER_2_HYBRID_BRIDGE
        elif is_swipe_feed:
            summary_tier = "Tier 1 + Tier 3 features"
            tier = Tier.TIER_3_GESTURE_MACRO
        elif ui_framework != "native":
            summary_tier = f"Tier 2 ({ui_framework.replace('_', ' ').title()})"
            tier = Tier.TIER_2_HYBRID_BRIDGE
        else:
            summary_tier = "Tier 1 (Native Views)"
            tier = Tier.TIER_1_NATIVE_VIEWS

    # Needs bridge for anything except pure native
    needs_bridge = (ui_framework != "native" or is_swipe_feed or is_browser)

    degraded_names = [feat.split(".")[-1] for feat, _ in degraded_features]
    has_hardware_degradation = len(degraded_features) > 0

    capabilities = Capabilities(
        ui_framework=ui_framework,
        needs_bridge=needs_bridge,
        has_pager=is_swipe_feed,
        is_browser=is_browser,
        degraded_hardware=degraded_names,
        risk=risk,
        exact_risk_signatures=exact_risk_signatures,
        summary_tier=summary_tier,
    )

    if is_browser:
        framework_notes.append("Browser Application: Virtual mouse pointer mode enabled by default for web content.")
    if is_swipe_feed:
        framework_notes.append("Pager / Feed detected: Gesture swipe macros available for vertical/horizontal paging.")
    if ui_framework == "hybrid_webview":
        framework_notes.append("Hybrid WebView detected: Accessibility bridge tree-walk / pointer navigation active.")

    if has_hardware_degradation:
        for feat, note in degraded_features:
            warnings.append(f"Hardware not available on TV: {feat} — {note}")
        hardware_list_str = ", ".join(degraded_names)
        framework_notes.append(
            f"Hardware Degradation Note: App requires unavailable hardware ({hardware_list_str}). "
            "Manifest will be relaxed so app installs; features requiring this hardware will be disabled."
        )

    return APKScanResult(
        apk_path=apk_path,
        metadata=metadata,
        capabilities=capabilities,
        tier=tier,
        verdict=verdict,
        blockers=blockers,
        warnings=warnings,
        framework_notes=framework_notes,
        native_libs_found=native_libs_found,
        dex_signatures_found=dex_signatures_found,
        has_hardware_degradation=has_hardware_degradation,
        degraded_hardware=degraded_features,
    )
