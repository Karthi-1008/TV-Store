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
    Tier, Verdict,
    BLOCKED_HARDWARE_FEATURES,
    DRM_AND_INTEGRITY_SIGNATURES,
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
    tier: Tier
    verdict: Verdict
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    framework_notes: List[str] = field(default_factory=list)
    native_libs_found: List[str] = field(default_factory=list)
    dex_signatures_found: List[str] = field(default_factory=list)

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
            # package: name='com.example' versionCode='1' versionName='1.0'
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
            # native-code: 'arm64-v8a' 'armeabi-v7a'
            abis = re.findall(r"'([^']+)'", line)
            meta.native_abis.extend(abis)

    return meta

def scan_apk(apk_path: Path) -> APKScanResult:
    """Run full Phase 0 pre-flight scan on the provided APK file."""
    apk_path = Path(apk_path).resolve()
    if not apk_path.exists():
        raise FileNotFoundError(f"APK file not found: {apk_path}")

    metadata = extract_badging_metadata(apk_path)
    blockers: List[str] = []
    warnings: List[str] = []
    framework_notes: List[str] = []
    native_libs_found: List[str] = []
    dex_signatures_found: List[str] = []

    # 1. Check Required Hardware Features in Manifest
    for feat in metadata.required_features:
        if feat in BLOCKED_HARDWARE_FEATURES:
            blockers.append(f"Blocked Hardware: {feat} ({BLOCKED_HARDWARE_FEATURES[feat]})")

    # 2. Inspect ZIP contents (native libs & DEX strings)
    is_game = False
    is_hybrid = False
    is_swipe_feed = False
    has_native_views = False
    has_drm = False

    with zipfile.ZipFile(apk_path, 'r') as zf:
        namelist = zf.namelist()
        
        # Check native libraries in lib/
        so_files = {Path(p).name for p in namelist if p.startswith("lib/") and p.endswith(".so")}
        native_libs_found = sorted(list(so_files))

        for lib_name in so_files:
            if lib_name in GAME_ENGINE_NATIVE_LIBS:
                is_game = True
                blockers.append(f"Game Engine Library: {lib_name} ({GAME_ENGINE_NATIVE_LIBS[lib_name]})")
            if lib_name in HYBRID_NATIVE_LIBS:
                is_hybrid = True
                framework_notes.append(f"Hybrid Engine Library: {lib_name} ({HYBRID_NATIVE_LIBS[lib_name]})")

        # Scan DEX files for signatures
        dex_files = [p for p in namelist if p.startswith("classes") and p.endswith(".dex")]
        for dex_name in dex_files:
            try:
                dex_bytes = zf.read(dex_name)
            except Exception as e:
                warnings.append(f"Failed to read {dex_name}: {e}")
                continue

            # Check DRM / Integrity
            for sig, desc in DRM_AND_INTEGRITY_SIGNATURES.items():
                if sig in dex_bytes:
                    has_drm = True
                    blockers.append(f"DRM / Integrity Protection: {desc} [{sig.decode('ascii', errors='ignore')}]")

            # Check Game DEX signatures
            for sig, desc in GAME_ENGINE_DEX_SIGNATURES.items():
                if sig in dex_bytes:
                    is_game = True
                    blockers.append(f"Game Framework Detected: {desc}")

            # Check Hybrid DEX signatures
            for sig, desc in HYBRID_DEX_SIGNATURES.items():
                if sig in dex_bytes:
                    is_hybrid = True
                    dex_signatures_found.append(f"Hybrid: {desc}")

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

    # OpenGL ES check for Games
    if metadata.uses_gl_es and not has_native_views and not is_hybrid:
        # App declares OpenGL ES without standard UI widgets or hybrid engines -> Likely custom OpenGL game/app
        warnings.append(f"App declares OpenGL ES version {metadata.uses_gl_es} without standard widgets.")
        if "game" in metadata.package_name.lower() or not is_hybrid:
            is_game = True
            blockers.append("App relies directly on OpenGL ES rendering without accessibility widget tree.")

    # Determine Tier and Verdict
    if blockers or has_drm or is_game:
        tier = Tier.TIER_5_EXCLUDED
        verdict = Verdict.REJECT
    elif is_swipe_feed:
        tier = Tier.TIER_3_GESTURE_MACRO
        verdict = Verdict.PROCEED
        framework_notes.append("Requires Engine A + Engine B with Gesture Macro mapping.")
    elif is_hybrid:
        tier = Tier.TIER_2_HYBRID_BRIDGE
        verdict = Verdict.PROCEED
        framework_notes.append("Requires Engine A + Engine B Accessibility Bridge (Tree-Walk).")
    elif has_native_views or True:
        # Default for non-blocked apps is Tier 1
        tier = Tier.TIER_1_NATIVE_VIEWS
        verdict = Verdict.PROCEED
        framework_notes.append("Standard Android Views detected. Can run with Engine A (Manifest patch).")

    return APKScanResult(
        apk_path=apk_path,
        metadata=metadata,
        tier=tier,
        verdict=verdict,
        blockers=blockers,
        warnings=warnings,
        framework_notes=framework_notes,
        native_libs_found=native_libs_found,
        dex_signatures_found=dex_signatures_found,
    )
