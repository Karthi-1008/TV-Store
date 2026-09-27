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
   | 4. Post-API30 Attribute Clean |
   | 5. Focus-Order Injection Pass |
   | 6. apktool recompile          |
   | 7. zipalign 4-byte            |
   | 8. apksigner (v1/v2/v3)       |
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
| **Tier 4** | Custom Canvas (Ambiguous GLES) | Manual Hotspot Calibration | Off by default (`--allow-manual-calibration`) |
| **Tier 5** | Hardware Degraded (Camera/GPS/Telephony/Gyro/NFC) | Engine A Hardware Relaxation + Bridge | **PROCEED with Warnings (Graceful Degradation)** |
| **Tier 6** | Hard Blockers (DRM/Anti-tamper, Real Game Engines) | *Hard Blocked by Pre-flight Scanner* | **Safely Skipped (No broken builds)** |

---

## Graceful Hardware Degradation (Tier 5)

Rather than treating the absence of mobile hardware (camera, GPS, telephony, gyroscope, biometrics, NFC) as an automatic rejection, the converter treats them as **gracefully degradable** (analogous to runtime permission denial on phones):
* **Manifest Relaxation:** Features declared with `android:required="true"` are relaxed to `android:required="false"`, allowing the APK to install on non-touch, TV-spec devices.
* **Degradation Warnings:** The scanner reports specific functional limitations (e.g. *"QR scanning / story creation disabled; remainder of app functions normally"*).
* **Crash Risk & Validation:** Because some apps fail to include null-checks when hardware services return null, Tier 5 apps should be verified on target hardware to confirm unhandled exceptions are not thrown when interacting with missing hardware screens.
* **Integrity/DRM Boundary:** Apps utilizing server-side cryptographic tamper attestation (SafetyNet, Play Integrity, DexGuard, etc.) remain in **Tier 6 (Hard Reject)** since hardware relaxation cannot resolve cryptographic signature verification.

---

## Per-App Scoping & TV Launcher Safety

The companion `TV Remote Bridge` app is strictly **scoped per-app**:
* **Never intercepts native TV apps or system launcher:** `RemoteBridgeService` immediately passes through key events to the OS (`super.onKeyEvent`) unless the active foreground app matches an entry in `ConvertedAppsRegistry`.
* **Dynamic Registration:** When an app is converted by `convert.py`, its package name is recorded in `output/converted_packages.json`.
* **Broadcast Registration:** Packages can be dynamically registered on the TV via ADB:
  ```bash
  adb shell am broadcast -a org.tvstore.remotebridge.ACTION_REGISTER_PACKAGE --es package_name com.example.app
  ```
* **Visual UI:** The `MainActivity` of TV Remote Bridge lists all currently registered packages in a dedicated dashboard.

---

## Manifest Attribute Sanitization (API 31-36 Compatibility)

Modern APKs compiled against Android 14–16 (API 34–36) often declare preview attributes in their manifests (e.g. `android:allowCrossUidActivitySwitchFromBelow`, `android:knownActivityEmbeddingCerts`, `android:enableOnBackInvokedCallback`). When recompiling with standard AAPT2 on Android 11 / API 30 targets, these unknown attributes cause fatal build linking errors.

Engine A includes an automated attribute sanitization pass (`config.UNSUPPORTED_POST_API30_ATTRS`) that strips non-standard post-API 30 attributes before resource linking, preserving full app functionality while preventing build failures.

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

* `TVRemoteBridge.apk`: The shared, scoped accessibility companion service for spatial navigation on Tier 2 & 3 apps (Flutter, React Native, WebViews, and swipe pagers).
* `Musify_tv.apk`: Converted Flutter audio player (Leanback launcher + TV banner + focus attributes + touchscreen disabled).
* `PrismGallery_tv.apk`: Converted media viewer with 18 interactive widgets across 7 layouts patched for D-pad focus.