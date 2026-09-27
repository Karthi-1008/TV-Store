"""Compatibility rules, signatures, and tier definitions for the Pre-flight Scanner.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set

class Tier(Enum):
    TIER_1_NATIVE_VIEWS = 1      # Standard Android Views / Compose (Manifest patch only)
    TIER_2_HYBRID_BRIDGE = 2     # Flutter / React Native / WebView (Manifest + Bridge Tree-walk)
    TIER_3_GESTURE_MACRO = 3     # Vertical feed / swipe-heavy / Pager (Manifest + Bridge + Swipe Macro)
    TIER_4_CUSTOM_CANVAS = 4     # Non-accessible Canvas / SurfaceView (Needs manual calibration, off by default)
    TIER_5_EXCLUDED = 5          # Hard blocker: Games, DRM/Integrity, Hardware missing (REJECT)

class Verdict(Enum):
    PROCEED = "PROCEED"                      # Safe to convert automatically (Tiers 1, 2, 3)
    WARN_MANUAL = "WARN_MANUAL"              # Requires manual calibration (Tier 4, needs --allow-manual)
    REJECT = "REJECT"                        # Hard stop, do not convert (Tier 5)

# Hardware features that Android TV (baseline MT5867) lacks
BLOCKED_HARDWARE_FEATURES = {
    "android.hardware.camera": "Requires camera hardware which Android TV lacks.",
    "android.hardware.camera.autofocus": "Requires autofocus camera.",
    "android.hardware.camera.front": "Requires front camera.",
    "android.hardware.telephony": "Requires cellular telephony hardware.",
    "android.hardware.telephony.gsm": "Requires GSM telephony.",
    "android.hardware.telephony.cdma": "Requires CDMA telephony.",
    "android.hardware.sensor.gyroscope": "Requires physical gyroscope.",
    "android.hardware.location.gps": "Requires GPS hardware (TV only has network location).",
    "android.hardware.nfc": "Requires NFC hardware.",
    "android.hardware.fingerprint": "Requires biometric fingerprint scanner.",
    "android.hardware.biometrics.fingerprint": "Requires biometric hardware.",
}

# Signatures for DRM, integrity verification, and anti-tamper SDKs that fail when re-signed
DRM_AND_INTEGRITY_SIGNATURES = {
    b"com/google/android/play/core/integrity": "Google Play Integrity API (breaks on re-signed APKs)",
    b"com/google/android/gms/safetynet": "Google SafetyNet Attestation (breaks on re-signed APKs)",
    b"com/scottyab/rootbeer": "RootBeer root / tamper detection library",
    b"com/nagravision": "Nagravision anti-tamper protection",
    b"com/securespaces": "SecureSpaces container protection",
    b"com/arxan": "Arxan / Digital.ai application protection",
    b"com/guardsquare/dexguard": "DexGuard integrity protection",
    b"com/verimatrix": "Verimatrix DRM protection",
    b"com/irdeto": "Irdeto Cloakware / DRM protection",
    b"com/widevine/client": "Widevine Proprietary DRM Client",
}

# Signatures identifying game engines (Games are excluded in v2)
GAME_ENGINE_NATIVE_LIBS = {
    "libunity.so": "Unity 3D Engine",
    "libil2cpp.so": "Unity IL2CPP Runtime",
    "libmain.so": "Unity / Game Native Main",
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

# Signatures for Tier 2: Hybrid / Cross-platform UI
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

# Signatures for Tier 3: Swipe / Feed / Pager UI
SWIPE_FEED_SIGNATURES = {
    b"androidx/viewpager2/widget/ViewPager2": "ViewPager2 Full-screen Paging",
    b"androidx/viewpager/widget/ViewPager": "ViewPager Paging",
    b"com/google/android/material/tabs/TabLayoutMediator": "Tab-based ViewPager",
}

# Signatures for Tier 1: Modern Native Views / Jetpack Compose
NATIVE_VIEW_SIGNATURES = {
    b"androidx/compose/ui": "Jetpack Compose UI",
    b"androidx/recyclerview/widget/RecyclerView": "AndroidX RecyclerView",
    b"android/widget/ListView": "Android ListView",
}
