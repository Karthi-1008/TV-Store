# Project Spec: APK → Android TV Remote-Native Converter

## 1. One-line goal

Take a normal (touch-only) Android APK — phone or tablet app, game, or anything else — and produce a modified APK that runs on Android TV with **full D-pad/remote navigation**, no mouse, no touch, no crashes, and no loss of the original app's functionality.

The **baseline hardware/software target** for all compatibility decisions is the TCL Android TV profile below. Every design decision (memory budget, rendering technique, service footprint) must fit this device first. Anything that works here should scale up cleanly to stronger TV boxes; we are not designing for high-end silicon.

---

## 2. Baseline target device (design floor — do not exceed its budget)

Extracted from `TCL_TV_Full_Config.md`. Treat this as the minimum-spec device the converter must run smoothly on.

| Subsystem | Spec | Implication for this project |
|---|---|---|
| SoC | MediaTek MT5867, 4× Cortex-A55 @ up to 1.5GHz | No heavy background processing, no per-frame image analysis, no OCR/ML-based UI detection at runtime |
| RAM | ~1GB total, ~350MB free, **192MB Java heap ceiling per app** | Our injected/overlay code must be extremely lightweight; can't run a second full app process alongside a heavy game |
| GPU | Mali-G31, OpenGL ES 3.2, Vulkan 1.1.131 | Fine for a simple vector cursor/highlight overlay; not for pixel-diffing the whole screen every frame |
| OS | Android 11, API 30, ART | Must use Accessibility Service + standard input APIs available at API 30, nothing newer-only |
| Display | 1280×720, 60Hz | UI overlays should be resolution-independent (dp-based), never assume 1080p/4K |
| Input | No touchscreen, no mouse expected, remote = D-pad + OK/Back/Home only (+ optionally a few colored/media keys) | This is the entire problem statement — see Section 4 |
| Network | Wi-Fi only, no telephony | No cellular-specific permission handling needed |

**Rule of thumb for the whole project:** if a technique needs noticeably more than ~20–30MB of extra heap or continuous CPU polling, it's disqualified for the baseline device, even if it's the "better" solution architecturally.

---

## 3. Problem statement (why apps break on TV)

A stock Android app built only for touch fails on TV for one or more of these reasons:

1. **No focusable views** — buttons/lists never had `focusable="true"` or D-pad focus-order set, so nothing highlights and OK does nothing.
2. **No key event handling** — the app listens for `onClick`/`onTouch`/gesture events only; it never listens for `KEYCODE_DPAD_*` or `KEYCODE_ENTER`.
3. **Manifest gates it out entirely** — `<uses-feature android:name="android.hardware.touchscreen" android:required="true">` (the default) makes the Play Store / Android TV launcher refuse to even show or install the app, and some devices block install outright.
4. **No leanback banner/intent filter** — Android TV home screen won't list the app as launchable even if it would technically run.
5. **Custom/game-engine UI (Unity, Cocos, raw OpenGL/Canvas)** — has no Android View hierarchy at all, so there's nothing for the OS focus system to attach to; the app is drawing its own buttons as pixels.
6. **Gesture-dependent UX** — swipe-to-dismiss, pinch-zoom, drag-and-drop, long-press context menus — has no 1:1 D-pad equivalent and needs an explicit mapping decision, not just "pass the key through."

The converter has to solve categories 1–4 generically and provide a best-effort, configurable fallback for 5–6.

---

## 4. Core approach: two complementary engines, not one

Do not try to solve this with a single trick. Build two engines and let the tool pick (or combine) per-app.

### Engine A — Manifest & Resource Patch (static, always applied)
Cheap, safe, always run first on every APK.

- Decompile with `apktool`.
- Force `AndroidManifest.xml`:
  - `<uses-feature android:name="android.hardware.touchscreen" android:required="false"/>`
  - `<uses-feature android:name="android.software.leanback" android:required="false"/>`
  - Add a `LEANBACK_LAUNCHER` category intent-filter on the main activity so it shows up on the TV home screen.
  - Add a `<meta-data android:name="android.max_aspect" ...>` fix and a leanback banner drawable (auto-generate from the app icon if none exists).
  - Strip/relax any hard touchscreen requirement flags.
- Recompile + zipalign + re-sign (with a debug key by default; support user-supplied keystore).
- **This alone is enough for a large fraction of simple, standard-Android-Views apps** (anything using normal Buttons/RecyclerViews already gets free D-pad focus traversal from the framework once the manifest stops blocking install).

### Engine B — Runtime Remote-to-Touch Bridge (dynamic, injected, used when Engine A isn't enough)
For apps whose UI doesn't naturally expose D-pad focus (custom game UI, WebViews, canvas-drawn menus, Unity/Cocos games, etc.):

- Inject a lightweight **Accessibility Service** (packaged either as (a) a small companion APK installed alongside the converted app, or (b) code merged directly into the target APK via smali patch — pick per-project, see Section 6).
- The service:
  1. Draws a single lightweight **on-screen focus cursor/highlight** (a thin outline or dot — cheap vector drawable, GPU cost near-zero).
  2. Listens for D-pad key events system-wide while the converted app is foreground.
  3. Walks the app's live `AccessibilityNodeInfo` tree to find clickable/focusable nodes' screen coordinates (this works even for many canvas-drawn UIs if they expose accessibility nodes; for pure raw-OpenGL/Unity apps with zero accessibility tree, fall back to the grid/manual-mapping mode below).
  4. Moves the highlight to the nearest clickable node in the direction pressed (up/down/left/right = nearest-neighbor spatial search, not raw tab order — this matches how a user visually predicts navigation).
  5. On OK/Enter, dispatches a synthetic tap (`dispatchGesture` with a zero-duration tap path) at the highlighted node's center coordinates.
  6. On Back, forwards to the app's normal back stack.
- **Manual mapping fallback (for apps with no accessibility tree at all, e.g. Unity/Cocos/raw GL games):** ship a lightweight per-app "hotspot map" — a small JSON/XML file the tool generates during a one-time interactive calibration pass (developer/tester runs the app once with a mouse or touch emulator, taps each important button, tool records the coordinates + a label). At runtime the bridge overlays a cursor that snaps between those recorded hotspots in D-pad-navigable order instead of doing live tree walking. This is the practical answer to "as in the phone we can predict where the clickable areas are" — we make that prediction a one-time authored asset instead of trying to infer it live on weak hardware.

This two-tier design is exactly why it fits the baseline device: Engine A costs nothing at runtime (it's a build-time patch), and Engine B's live tree-walk mode only activates on key-press events (not continuous polling), keeping CPU/heap usage near idle between button presses.

---

## 5. Feature requirements

### Must-have (v1)
- [ ] Batch or single-APK input; output a signed, installable `.apk`.
- [ ] Engine A manifest/resource patch applied to every input automatically.
- [ ] Auto-detection heuristic: scan the decompiled app for standard Android View usage vs. Unity/Cocos/native-GL/WebView signatures, to decide whether Engine B is needed and which of its sub-modes (live tree-walk vs. hotspot-map) to use.
- [ ] Engine B accessibility-bridge cursor: D-pad move, OK = tap, Back = back, Home = passthrough to system.
- [ ] Configurable long-press mapping (hold OK = long-press touch) and basic swipe emulation (e.g., map a rewind/fast-forward remote key or long-direction-hold to a swipe gesture) for apps that need it.
- [ ] Calibration/authoring mode to build the hotspot map for non-accessible UIs, without needing a mouse permanently connected (calibration itself can use a temporary mouse/touch source, but the shipped output never requires one).
- [ ] Never modify app logic/assets/game code — only manifest, resources, and the added navigation-bridge layer. The original app binary and behavior must be untouched aside from what's needed for input.
- [ ] Crash-safety: if the accessibility bridge can't find any focusable/mapped target, it must fail silently (do nothing) rather than crash the host app or itself.
- [ ] Works fully offline after conversion — no server dependency for input handling at runtime.
- [ ] Stay within baseline device memory/CPU budget (Section 2) — test on the baseline profile before calling anything "done."

### Nice-to-have (v2+)
- [ ] GUI/desktop or web front-end to drop in an APK and get the converted one back, with a preview of detected UI type.
- [ ] Auto-generated leanback banner/icon if missing.
- [ ] Per-app config file the user can hand-edit (key remaps, cursor speed/style, whether hotspot-map or live-tree mode is forced).
- [ ] Support batch-processing a folder of APKs with a shared default profile.
- [ ] Optional gamepad-classic-button mapping profile for apps that support Bluetooth controllers already (skip the bridge entirely for those, since they already handle non-touch input).

### Explicit non-goals
- Not attempting to fix apps that are fundamentally incompatible at the CPU/GPU level (e.g., won't try to make a heavy 3D mobile game *performant* on this SoC — only navigable).
- Not cracking DRM/signature verification schemes to enable modification of protected apps.
- Not guaranteeing 100% success on every APK — some will remain touch-only; the tool should report this clearly rather than ship a broken build.

---

## 6. Technical architecture / tech stack

**Build-time converter (the tool itself):**
- Language: Kotlin or Python for the orchestration layer (Python is easier for quick iteration/CLI; Kotlin/JVM is easier for tight integration with `apktool`/`smali`/`baksmali`/Android build tooling — pick one, don't mix).
- Decompile/recompile: `apktool`.
- Manifest patching: direct XML manipulation (Android binary XML via apktool's decoded form) or `androguard` for inspection/heuristics.
- Signing: `apksigner` + a generated debug keystore by default, user keystore optional.
- UI-type detection heuristics: scan decompiled `smali`/resources for markers — Unity (`libunity.so`, `il2cpp`), Cocos2d, `WebView`-heavy layouts, or standard `android.widget.*` usage — to choose Engine B mode automatically.

**Runtime bridge (what ships inside/alongside the converted APK):**
- Android `AccessibilityService` (`BIND_ACCESSIBILITY_SERVICE`) — this is the only officially-supported, non-root way to intercept system-wide key events and dispatch synthetic touch on stock Android TV without requiring root.
- A minimal always-on-top overlay (`TYPE_ACCESSIBILITY_OVERLAY`) for the cursor/highlight graphic — vector drawable, no bitmap scaling cost.
- JSON-based hotspot-map format for the calibration fallback mode.
- No root required anywhere in the design — this matters because most consumer Android TVs, including budget sets like the baseline device, are not rooted and users won't root them.

**Packaging decision to make early:** ship the bridge as (a) a single companion "TV Remote Bridge" app the user installs once, which then works for *every* converted app (simpler, reusable, smaller per-APK size), vs. (b) inject the bridge code directly into each converted APK (more self-contained but bloats every output and duplicates the accessibility-service boilerplate). **Recommendation: build (a) first** — one shared bridge app + N thin converted APKs that just carry Engine A's manifest patch plus a small manifest flag telling the bridge "I need hotspot-map mode, here's my map asset." This is far lighter on the 192MB heap ceiling since the bridge only loads while needed and isn't duplicated per app.

---

## 7. Development phases

1. **Phase 0 — Feasibility spike:** Take 3 known-simple standard-Android-Views apps, run Engine A only (manifest patch), confirm they install and are D-pad navigable on the baseline TV profile (or an emulator configured to match it: API 30, 1GB RAM, no touchscreen, Mali-class GPU skin doesn't matter for emulator testing, D-pad-only input).
2. **Phase 1 — Engine A automation:** Fully automate the manifest/resource patch pipeline as a CLI tool, batch-capable.
3. **Phase 2 — Companion bridge app (Engine B, live tree-walk mode):** Build the standalone accessibility-service app; test against apps with accessible-but-non-focusable UI (common in hybrid/WebView apps).
4. **Phase 3 — Hotspot-map calibration mode:** Build the one-time calibration recorder + the runtime consumer of that map, for Unity/Cocos/raw-canvas apps.
5. **Phase 4 — Auto-detection heuristic:** Tie Phases 1–3 together so the tool picks the right mode without manual intervention for most apps, only asking the user to run calibration when it genuinely can't detect an accessibility tree.
6. **Phase 5 — Hardening on baseline device:** Real-device testing on the TCL TV profile (or exact hardware if available) for memory ceiling, cursor responsiveness at 60Hz, and crash-safety edge cases (rapid key presses, app backgrounding mid-navigation, etc.).
7. **Phase 6 — UX polish:** Front-end/GUI, batch mode, per-app config editing, banner/icon auto-generation.

---

## 8. Known limitations (be upfront with users of the tool)

- Apps with server-side anti-tamper/signature checks may refuse to run once repackaged and re-signed.
- Heavy 3D games will still be CPU/GPU-limited by the SoC regardless of input fixes — the converter fixes *navigability*, not *performance*.
- Highly gesture-dependent UX (multi-touch pinch/zoom, drag-and-drop inventories, etc.) will get a degraded but functional D-pad approximation, not a pixel-perfect touch replacement.
- Apps that draw 100% custom UI with zero accessibility exposure require the one-time manual calibration step; this cannot be fully automatic for those.

---

## 9. Success criteria for v1

- A standard Views-based app (e.g., a simple utility or list-based app) installs via Engine A alone and is 100% navigable with only a D-pad remote.
- A WebView-based app is navigable via Engine B live tree-walk mode.
- A Unity-based simple game's main menu (not gameplay) is navigable via the hotspot-map fallback.
- None of the above exceed a measured ~20-30MB additional heap footprint or introduce visible input lag (>150ms) on the baseline TCL MT5867 / 1GB RAM / API 30 profile.
- Zero crashes attributable to the bridge across a defined smoke-test app set.
