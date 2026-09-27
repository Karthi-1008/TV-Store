# Project Spec v2: APK → Android TV Converter (Apps Only, Optimized)

## Scope statement

This tool converts **non-game Android apps** (utilities, shopping, social, streaming clients, productivity, readers, hybrid/web apps) into Android TV–installable, D-pad-navigable APKs, with no touch and no mouse required.

**Games are explicitly out of scope for this version.** Not because they can't be attempted with the same architecture, but because mixing them in lowers the tool's reliability and adds an entire manual-calibration subsystem that apps almost never need. Scoping to apps only lets this be a **"must work" tool** — high, predictable success rate — instead of a "might work" tool.

---

## 1. Baseline target device (hard design floor)

From `TCL_TV_Full_Config.md` — every decision below must fit inside this budget, not just work on stronger hardware.

| Subsystem | Spec | Constraint this imposes |
|---|---|---|
| SoC | MediaTek MT5867, 4× Cortex-A55 @ ≤1.5GHz | No continuous polling, no per-frame processing |
| RAM | ~1GB total, ~350MB free | Bridge service must be small and mostly idle |
| Java heap ceiling | **192MB per app** | Injected/companion code must add well under 20-30MB |
| GPU | Mali-G31, GLES 3.2 / Vulkan 1.1 | Cursor overlay must be vector-based, not bitmap-heavy |
| OS | Android 11, API 30 | Use only API-30-safe Accessibility/Input APIs |
| Display | 1280×720 @ 60Hz | UI overlays must be dp-based, resolution-independent |
| Input | D-pad + OK/Back/Home only, no touchscreen, no mouse expected | The entire problem this project solves |
| Root | None, not expected, not required | Solution must work on stock, unrooted consumer TVs |

---

## 2. Compatibility tiers (what "must work" actually covers)

This is the honest map of outcomes. The tool's job is to **push as many real-world apps into Tier 1–2, auto-detect Tier 3–4, and refuse to touch Tier 5 rather than ship a broken result.**

| Tier | App type | Method | Expected success |
|---|---|---|---|
| **1** | Standard Android Views/Compose apps — utilities, calculators, notes, readers, list-detail apps, basic media players | Engine A (manifest/resource patch only) | High — this is the "must work" core |
| **2** | Hybrid/WebView apps, Flutter, React Native, most modern cross-platform apps | Engine A + Engine B (live accessibility tree-walk) | High-moderate |
| **3** | Vertical feeds / swipe-heavy readers (short-video style, manga/comic readers) | Engine A + Engine B + gesture-macro key mapping (D-pad↔synthetic swipe) | Moderate, usable but not seamless |
| **4** | Apps with custom canvas-drawn controls but simple, static screens | Engine A + Engine B hotspot-map (optional, off by default in apps-only mode) | Low-moderate, needs manual calibration |
| **5 — Do Not Attempt** | DRM/anti-tamper apps (banking, Netflix/Disney+-style clients, Play Integrity–gated apps), apps requiring camera/GPS/gyroscope/SIM, apps needing true multi-touch or pinch/drag as core function | None — auto-detected and rejected pre-conversion | N/A by design |

Tier 4 stays in the spec as an optional module but is **off by default** for the apps-only build — most real apps never need it, and leaving it off keeps the tool's default behavior fully automatic (no manual calibration step required for a normal run).

---

## 3. Pre-flight Compatibility Scanner (the key to "must work")

This is the piece that makes the tool trustworthy: **before attempting any conversion, scan the APK and classify it.** If it lands in Tier 5, stop and tell the user why, instead of producing an APK that installs but crashes or fails at runtime. A tool that silently ships broken output is worse than one that says "can't do this one, here's why."

**Scanner checks, in order:**

1. **Manifest permission/feature scan** — flag hard requirements for `android.hardware.camera`, `android.hardware.telephony`, `android.hardware.sensor.gyroscope`, GPS-only location requirements, `android.hardware.touchscreen required="true"` combined with no fallback.
2. **DRM/integrity signature scan** — detect Widevine usage (`MediaDrm`, Widevine UUID references), Play Integrity API calls, SafetyNet attestation calls, and known anti-tamper SDK signatures (common obfuscators, root-check libraries). If found → flag as **Tier 5, do not convert**, since re-signing will break these regardless of anything else the tool does.
3. **UI framework detection** — inspect decompiled smali/resources for:
   - Standard `android.widget.*` / Jetpack Compose semantics → **Tier 1 candidate**.
   - `WebView`, Flutter engine (`libflutter.so`), React Native (`libreactnativejni.so`) signatures → **Tier 2 candidate**.
   - Heavy custom `SurfaceView`/`TextureView`/raw GL rendering with no standard widget tree → **Tier 4, flag as needing manual calibration, warn user, skip by default**.
4. **Gesture-dependency heuristic** — flag apps whose core navigation pattern (from manifest/UI scan) looks like vertical-feed/swipe-first (common package/class name patterns, `ViewPager2` full-screen paging as the primary nav) → **Tier 3, apply gesture-macro module**.
5. **Report before converting.** Output a short compatibility report per APK: predicted tier, reasons, and what will/won't be attempted. Only proceed automatically for Tiers 1–3. Tier 4 requires an explicit `--allow-manual-calibration` flag. Tier 5 requires no flag — it's a hard stop with an explanation.

This scanner is what turns "might work" into "must work for what it says it'll do" — the tool's promises stay honest because it never attempts the categories it can't actually deliver on.

---

## 4. Engine A — Manifest & Resource Patch (build-time, always run, zero runtime cost)

This is the primary workhorse for apps-only scope and should be built and validated first.

**Pipeline steps:**
1. Decompile with `apktool`.
2. Patch `AndroidManifest.xml`:
   - `<uses-feature android:name="android.hardware.touchscreen" android:required="false"/>`
   - `<uses-feature android:name="android.software.leanback" android:required="false"/>`
   - Add `LEANBACK_LAUNCHER` category to the main launcher activity's intent filter.
   - Add/generate a leanback banner (`<meta-data android:name="android.tv_banner">`) — auto-generate a simple 320×180 banner from the existing app icon if none exists.
   - Fix `android:max_aspect` conflicts if present.
3. **Focus-order pass (important refinement over v1):** scan layout XML resources for interactive widgets missing explicit `focusable`/`focusableInTouchMode`/`nextFocusUp/Down/Left/Right` attributes, and inject sane defaults where the framework's automatic `focusSearch` is likely to guess wrong (e.g., custom `ViewGroup`-based cards with click listeners on the container rather than a true child button). This directly addresses the gap between "should work" and "actually works" for Tier 1 apps that look simple but aren't fully framework-standard.
4. Recompile, zipalign, sign (debug key by default; support custom keystore).
5. Emit the pre-flight scanner's compatibility report alongside the output APK.

**This step alone should fully solve Tier 1 and meaningfully improve Tier 2 apps' out-of-the-box focus behavior.**

---

## 5. Engine B — Runtime Accessibility Bridge (for Tier 2–3, optional Tier 4)

Ship as a **single shared companion app** ("TV Remote Bridge"), not duplicated per converted APK — this keeps every individual converted app small and keeps the shared bridge's footprint the only thing to optimize against the 192MB heap ceiling.

**Core behavior:**
1. `AccessibilityService` listens for D-pad key events system-wide while a converted app is foreground.
2. On key press, walks the current `AccessibilityNodeInfo` tree, finds the nearest clickable/focusable node in the pressed direction (spatial nearest-neighbor, not raw tab order — matches how a user visually predicts navigation).
3. Draws a lightweight vector-outline cursor (`TYPE_ACCESSIBILITY_OVERLAY`) around the focused node. No bitmap scaling, no continuous redraw — only updates on key press.
4. On OK: dispatches a synthetic tap (`dispatchGesture`, zero-duration tap) at the node's center.
5. On Back: forwards to the app's normal back stack.
6. **Gesture-macro module (Tier 3):** for apps flagged as swipe/feed-style by the scanner, map a configurable key (e.g., hold-down or a secondary remote button) to a synthetic vertical swipe gesture via `dispatchGesture` with a short path, instead of trying to force D-pad focus onto a full-screen pager.
7. **Fail-silent rule:** if no focusable/clickable target is found in a direction, do nothing — never crash the host app or itself. This is non-negotiable given the "no crashes" requirement.

---

## 6. Build phases (apps-only, optimized order)

1. **Phase 0 — Scanner spike:** Build the pre-flight compatibility scanner first, standalone, against a test set of ~15-20 real apps spanning Tiers 1, 2, 3, and 5. Confirm it correctly separates "safe to convert" from "will fail regardless."
2. **Phase 1 — Engine A pipeline:** Full apktool decompile → manifest patch → focus-order pass → resign → output. Validate against Tier 1 test apps on the baseline device profile.
3. **Phase 2 — Engine B core (Tier 2 tree-walk):** Build the shared companion bridge app, cursor overlay, and spatial navigation. Validate against WebView/Flutter/React Native test apps.
4. **Phase 3 — Gesture-macro module (Tier 3):** Add swipe emulation for feed-style apps, gated behind the scanner's detection.
5. **Phase 4 — Hardening on baseline hardware:** Real or emulator-matched testing (API 30, 1GB RAM profile, no touchscreen, D-pad-only input) for heap usage, input latency, and fail-silent behavior under edge cases (rapid presses, backgrounding mid-navigation, orientation-locked apps).
6. **Phase 5 (optional, off by default) — Tier 4 hotspot-map calibration module:** Only build this if real-world testing shows a meaningful number of apps landing in Tier 4 that are worth the manual-calibration cost. Not required for the apps-only "must work" core.

---

## 7. Success criteria (what "must work" means concretely)

- The pre-flight scanner correctly flags 100% of a defined Tier-5 test set (DRM/banking/hardware-dependent apps) and refuses conversion with a clear reason — **zero silently-broken outputs.**
- 100% of a defined Tier-1 test set (5-10 standard native apps) installs, appears on the TV home screen, and is fully navigable with D-pad only, no crashes.
- ≥80% of a defined Tier-2 test set (WebView/Flutter/React Native apps) is navigable via the bridge with no crashes, even if some targeting is imprecise.
- Bridge companion app adds no more than ~20-30MB effective memory overhead and introduces no more than ~150ms input-to-highlight-move latency on the baseline device profile.
- No conversion or bridge failure ever crashes the host app — worst case is "nothing happens" on a given key press, never a force-close.

---

## 8. Hard exclusions (never attempted, by design — not a future TODO)

| Category | Examples | Why it's excluded permanently |
|---|---|---|
| DRM/anti-tamper apps | Banking apps, Netflix/Disney+-style clients, Play Integrity–gated apps | Re-signing breaks cryptographic validation — unfixable at this layer |
| Hardware-dependent apps | Camera/QR scanning, GPS-only nav, gyroscope-tilt controls, SIM/SMS verification | TV has none of this hardware |
| True multi-touch / drag-core apps | Photo/video editors, CAD viewers, drag-and-drop-heavy apps | No 1:1 D-pad equivalent exists |
| All games | Any `.apk` detected as a game engine (Unity/Cocos/Godot/etc.) or requiring real-time multi-touch | Out of scope for this version by design, not a technical dead-end — revisit separately if desired |

---

## 9. What changed from v1 (for context when handing to Antigravity)

- Scope narrowed to apps only — games and their hotspot-calibration system are now optional/deferred, not core.
- Added the **pre-flight compatibility scanner** as a first-class component, not an afterthought — this is what lets the tool make a "must work" promise instead of a "try it and see" one.
- Added the **focus-order injection pass** to Engine A to close the gap between "looks like a standard app" and "actually has correct D-pad focus order."
- Added the **gesture-macro module** as its own tier/phase instead of lumping swipe-handling in with the general bridge.
- Reordered build phases so the scanner is built and validated *before* the conversion pipeline, since it defines what the pipeline should even attempt.
