# APK to Android TV Remote-Native Converter

A deterministic, high-reliability pipeline to convert standard touch-only Android APKs into Android TV–installable, D-pad–navigable packages with zero touch and no mouse required.

Engineered specifically around the **TCL Android TV profile (MediaTek MT5867, 1GB RAM, 192MB Java heap ceiling, Android 11 / API 30, D-pad remote only)**.

---

## Architecture Overview

```
                                  +-------------------+
                                  |    Target APK     |
                                  +---------+---------+
                                            |
                                            v
                              [ Phase 0: Pre-flight Scanner ]
                                            |
                   +------------------------+------------------------+
                   |                                                 |
         [ Tiers 1, 2, 3 ]                                      [ Tier 5 ]
         Pass Pre-flight                                     Hard Blockers
                   |                                        (Games, DRM, Hardware)
                   v                                                 |
       [ Engine A Build Pipeline ]                                   v
   +-------------------------------+                         Conversion REJECTED
   | 1. apktool decompile          |                          (No broken builds)
   | 2. 16:9 Banner Auto-Gen       |
   | 3. Manifest TV & Leanback     |
   | 4. Focus-Order Injection Pass |
   | 5. apktool recompile          |
   | 6. zipalign 4-byte            |
   | 7. apksigner (v1/v2/v3)       |
   +---------------+---------------+
                   |
                   v
          [ Output Converted APK ]
                   +
       [ Companion Bridge APK ]
   (Installed once: Spatial Tree-Walk &
    Synthetic Gestures for Tier 2/3 Apps)
```

---

## Compatibility Tiers

| Tier | Category | Conversion Path | Status |
|---|---|---|---|
| **Tier 1** | Standard Views / Jetpack Compose | Engine A Manifest & Focus Patch | **100% Native D-pad** |
| **Tier 2** | Hybrid / Flutter / React Native / WebView | Engine A + TV Remote Bridge | **Spatial Tree-Walk Navigation** |
| **Tier 3** | Swipe Feeds / Vertical Pagers | Engine A + TV Remote Bridge | **Directional Swipe Macros** |
| **Tier 4** | Custom Canvas (Static) | Manual Hotspot Calibration | Off by default (`--allow-manual-calibration`) |
| **Tier 5** | Games, Anti-tamper/DRM, Camera/GPS required | *Hard Blocked by Pre-flight Scanner* | **Safely Skipped** |

---

## Quick Start

### 1. Scan APK Compatibility
Analyze any APK to inspect permissions, native engines, DRM/tamper flags, and predicted tier:
```bash
python convert.py scan path/to/app.apk
```

Or scan an entire folder of APKs:
```bash
python convert.py scan path/to/apks_folder/
```

### 2. Convert APK for Android TV
Convert an APK into a signed, TV-ready package:
```bash
python convert.py convert path/to/app.apk -o output/app_tv.apk
```

---

## Included Artifacts in `output/`

* `TVRemoteBridge.apk`: The shared, lightweight accessibility companion service for spatial navigation on Tier 2 & 3 apps (Flutter, React Native, WebViews, and swipe pagers).
* `Musify_tv.apk`: Converted Flutter audio player (Leanback launcher + TV banner + focus attributes + touchscreen disabled).
* `PrismGallery_tv.apk`: Converted media viewer with 18 interactive widgets across 7 layouts patched for D-pad focus.