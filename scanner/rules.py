"""Compatibility rules, signatures, and capabilities for the Pre-flight Scanner.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set, Dict

class Tier(Enum):
    TIER_1_NATIVE_VIEWS = 1      # Standard Android Views / Compose (Manifest patch only)
    TIER_2_HYBRID_BRIDGE = 2     # Flutter / React Native / WebView (Manifest + Bridge Tree-walk)
    TIER_3_GESTURE_MACRO = 3     # Vertical feed / swipe-heavy / Pager (Manifest + Bridge + Swipe Macro)
    TIER_4_CUSTOM_CANVAS = 4     # Non-accessible Canvas / SurfaceView (Needs manual calibration, off by default)
    TIER_5_EXCLUDED = 5          # Hard blocker: Hard DRM, Real Game engines (REJECT)

class Verdict(Enum):
    PROCEED = "PROCEED"                      # Safe to convert automatically
    WARN_RISKY = "WARN_RISKY"                # Soft integrity check detected (needs --allow-risky)
    WARN_MANUAL = "WARN_MANUAL"              # Custom canvas (needs --allow-manual-calibration)
    REJECT = "REJECT"                        # Hard stop, do not convert (Hard DRM or Real Games)

@dataclass
class Capabilities:
    ui_framework: str = "native"          # "native" | "hybrid_webview" | "flutter" | "react_native" | "canvas"
    needs_bridge: bool = False           # True for anything except pure native
    has_pager: bool = False              # ViewPager/ViewPager2 present -> swipe macro available
    is_browser: bool = False             # Browser app -> pointer mode by default for web content
    degraded_hardware: List[str] = field(default_factory=list) # camera, gps, telephony ...
    risk: str = "none"                   # "none" | "soft_integrity" | "hard_drm" | "game"
    exact_risk_signatures: List[str] = field(default_factory=list)
    summary_tier: str = "Tier 1"

# Hardware features that Android TV (baseline MT5867) lacks, but which apps can gracefully degrade on
DEGRADABLE_HARDWARE_FEATURES = {
    "android.hardware.camera": "Camera-dependent features (QR scan, photo/video capture, Stories/Reels creation) will not work. App should otherwise function.",
    "android.hardware.camera.autofocus": "Autofocus-dependent camera features will not work.",
    "android.hardware.camera.front": "Front-camera features (selfie mode, video calls) will not work.",
    "android.hardware.telephony": "SMS/cellular telephony features will not work on TV. Use a reachable phone number elsewhere or existing session.",
    "android.hardware.telephony.gsm": "GSM telephony hardware not available on TV.",
    "android.hardware.telephony.cdma": "CDMA telephony hardware not available on TV.",
    "android.hardware.sensor.gyroscope": "Tilt/motion-based controls or sensor effects will not work.",
    "android.hardware.location.gps": "Precise GPS hardware will not work; network location may still function if supported.",
    "android.hardware.nfc": "NFC features (tap-to-pay/share) will not work.",
    "android.hardware.fingerprint": "Biometric fingerprint login will not work; app should fall back to password/PIN.",
    "android.hardware.biometrics.fingerprint": "Biometric scanner not available on TV.",
}

# Hard DRM: Unrecoverable when re-signed (breaks media decryption or hard anti-tamper SDKs) -> REJECT
HARD_DRM_SIGNATURES = {
    b"com/widevine/client": "Widevine Proprietary DRM Client",
    b"com/nagravision": "Nagravision anti-tamper protection",
    b"com/securespaces": "SecureSpaces container protection",
    b"com/arxan": "Arxan / Digital.ai application protection",
    b"com/guardsquare/dexguard": "DexGuard integrity protection",
    b"com/verimatrix": "Verimatrix DRM protection",
    b"com/irdeto": "Irdeto Cloakware / DRM protection",
}

# Soft integrity: App may refuse login or check attestation at runtime -> WARN_RISKY (convertible with --allow-risky)
SOFT_INTEGRITY_SIGNATURES = {
    b"com/google/android/play/core/integrity": "Google Play Integrity API (may block login or features after re-signing)",
    b"com/google/android/gms/safetynet": "Google SafetyNet Attestation (may block login or features after re-signing)",
    b"com/scottyab/rootbeer": "RootBeer root / tamper detection library",
}

# Signatures identifying confirmed game engines (Games are excluded in v2)
GAME_ENGINE_NATIVE_LIBS = {
    "libunity.so": "Unity 3D Engine",
    "libil2cpp.so": "Unity IL2CPP Runtime",
    "libcocos2djs.so": "Cocos2d-JS Engine",
    "libcocos2dcpp.so": "Cocos2d-x Engine",
    "libgodot_android.so": "Godot Engine",
    "libdefold.so": "Defold Engine",
    "libunreal.so": "Unreal Engine",
    "libUE4.so": "Unreal Engine 4",
    "libmonosgen-2.0.so": "Mono Runtime (Unity/Game)",
    "libcorona.so": "Solar2D / Corona Engine",
    "libgamemaker.so": "GameMaker Studio",
}

GAME_ENGINE_DEX_SIGNATURES = {
    b"com/unity3d/player": "Unity Player Framework",
    b"org/cocos2dx/lib": "Cocos2d-x Framework",
    b"org/godotengine/godot": "Godot Framework",
    b"com/epicgames/ue4": "Unreal Engine Framework",
    b"com/ansca/corona": "Corona/Solar2D Framework",
    b"com/yoyogames": "GameMaker Framework",
}

# Signatures for Hybrid / Cross-platform UI
HYBRID_NATIVE_LIBS = {
    "libflutter.so": "Flutter Framework Engine",
    "libapp.so": "Flutter Application AOT Code",
    "libreactnativejni.so": "React Native Engine",
    "libhermes.so": "Hermes JavaScript Engine (React Native)",
}

HYBRID_DEX_SIGNATURES = {
    b"io/flutter/embedding": "Flutter Engine Embedding",
    b"com/facebook/react": "React Native Framework",
    b"org/apache/cordova": "Apache Cordova Hybrid",
    b"com/getcapacitor": "Capacitor Hybrid",
    b"android/webkit/WebView": "Android WebView",
}

# Signatures for Swipe / Feed / Pager UI
SWIPE_FEED_SIGNATURES = {
    b"androidx/viewpager2/widget/ViewPager2": "ViewPager2 Full-screen Paging",
    b"androidx/viewpager/widget/ViewPager": "ViewPager Paging",
    b"com/google/android/material/tabs/TabLayoutMediator": "Tab-based ViewPager",
}

# Signatures for Modern Native Views / Jetpack Compose
NATIVE_VIEW_SIGNATURES = {
    b"androidx/compose/ui": "Jetpack Compose UI",
    b"androidx/recyclerview/widget/RecyclerView": "AndroidX RecyclerView",
    b"android/widget/ListView": "Android ListView",
}
