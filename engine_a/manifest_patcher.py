"""Manifest patcher for Android TV conversion.
Updates AndroidManifest.xml for Leanback launcher, touchscreen relaxation, and banner.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple
import config

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)

def qname(tag_or_attr: str) -> str:
    """Helper to produce Clark notation for Android namespace."""
    return f"{{{ANDROID_NS}}}{tag_or_attr}"

def patch_manifest(
    decompiled_dir: Path,
    banner_drawable: str = "@drawable/tv_banner",
    mode: str = "auto"
) -> Tuple[bool, List[str]]:
    """Patch AndroidManifest.xml in decompiled_dir for Android TV.
    
    Returns:
        (success: bool, changes_made: List[str])
    """
    manifest_path = Path(decompiled_dir) / "AndroidManifest.xml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"AndroidManifest.xml not found at {manifest_path}")

    # Parse XML preserving namespaces
    tree = ET.parse(manifest_path)
    root = tree.getroot()
    changes: List[str] = []

    # 1. Patch or insert uses-feature touchscreen = false
    touchscreen_features = [
        elem for elem in root.findall("uses-feature")
        if elem.attrib.get(qname("name")) == "android.hardware.touchscreen"
    ]
    if touchscreen_features:
        for elem in touchscreen_features:
            if elem.attrib.get(qname("required")) != "false":
                elem.attrib[qname("required")] = "false"
                changes.append("Updated android.hardware.touchscreen required='false'")
    else:
        feat = ET.Element("uses-feature", {
            qname("name"): "android.hardware.touchscreen",
            qname("required"): "false"
        })
        root.insert(0, feat)
        changes.append("Added android.hardware.touchscreen required='false'")

    # 2. Patch or insert uses-feature leanback = false (false allows compatibility on both phone/TV)
    leanback_features = [
        elem for elem in root.findall("uses-feature")
        if elem.attrib.get(qname("name")) == "android.software.leanback"
    ]
    if not leanback_features:
        feat = ET.Element("uses-feature", {
            qname("name"): "android.software.leanback",
            qname("required"): "false"
        })
        root.insert(0, feat)
        changes.append("Added android.software.leanback required='false'")

    # 3. Add faketouch feature (common requirement for non-touch TV devices)
    faketouch_features = [
        elem for elem in root.findall("uses-feature")
        if elem.attrib.get(qname("name")) == "android.hardware.faketouch"
    ]
    if not faketouch_features:
        feat = ET.Element("uses-feature", {
            qname("name"): "android.hardware.faketouch",
            qname("required"): "false"
        })
        root.insert(0, feat)
        changes.append("Added android.hardware.faketouch required='false'")

    # 4. Relax degradable hardware features to required='false' (camera, telephony, GPS, gyro, biometrics, NFC)
    degradable_feature_names = [
        "android.hardware.camera",
        "android.hardware.camera.autofocus",
        "android.hardware.camera.front",
        "android.hardware.telephony",
        "android.hardware.telephony.gsm",
        "android.hardware.telephony.cdma",
        "android.hardware.sensor.gyroscope",
        "android.hardware.location.gps",
        "android.hardware.nfc",
        "android.hardware.fingerprint",
        "android.hardware.biometrics.fingerprint",
    ]
    for feat_name in degradable_feature_names:
        matching = [e for e in root.findall("uses-feature") if e.attrib.get(qname("name")) == feat_name]
        for elem in matching:
            if elem.attrib.get(qname("required")) != "false":
                elem.attrib[qname("required")] = "false"
                changes.append(f"Relaxed {feat_name} to required='false' (graceful hardware degradation)")

    # 5. Patch Application tag (banner, metadata, hardware acceleration, resizeable)
    app_elem = root.find("application")
    if app_elem is not None:
        if qname("banner") not in app_elem.attrib:
            app_elem.attrib[qname("banner")] = banner_drawable
            changes.append(f"Set application android:banner='{banner_drawable}'")

        # Inject TV-Store self-identification markers
        has_converted_meta = any(
            m.attrib.get(qname("name")) == "org.tvstore.converted"
            for m in app_elem.findall("meta-data")
        )
        if not has_converted_meta:
            meta_conv = ET.Element("meta-data", {
                qname("name"): "org.tvstore.converted",
                qname("value"): "1"
            })
            app_elem.append(meta_conv)
            changes.append("Injected org.tvstore.converted=1 meta-data")

        has_mode_meta = any(
            m.attrib.get(qname("name")) == "org.tvstore.mode"
            for m in app_elem.findall("meta-data")
        )
        if not has_mode_meta:
            meta_mode = ET.Element("meta-data", {
                qname("name"): "org.tvstore.mode",
                qname("value"): mode
            })
            app_elem.append(meta_mode)
            changes.append(f"Injected org.tvstore.mode='{mode}' meta-data")

        # Strip post-API 30 attributes unknown to older framework definitions (baseline TV is API 30)
        unsupported_qnames = {qname(attr) for attr in config.UNSUPPORTED_POST_API30_ATTRS}
        for elem in root.iter():
            matched_attrs = [a for a in elem.attrib if a in unsupported_qnames]
            for a in matched_attrs:
                del elem.attrib[a]
                attr_name = a.split("}")[-1]
                changes.append(f"Removed post-API 30 attribute {attr_name} for TV compatibility")

        # Relax portrait orientation constraint on activities
        for activity in app_elem.findall("activity") + app_elem.findall("activity-alias"):
            screen_orient = activity.attrib.get(qname("screenOrientation"))
            if screen_orient in ("portrait", "reversePortrait", "sensorPortrait", "userPortrait"):
                activity.attrib[qname("screenOrientation")] = "unspecified"
                act_name = activity.attrib.get(qname("name"), "UnknownActivity")
                changes.append(f"Relaxed portrait orientation on {act_name} to 'unspecified'")

    # 5. Patch Launchable Activity with LEANBACK_LAUNCHER intent-filter and explicit banner
    main_activities = []
    leanback_activities = []

    if app_elem is not None:
        effective_banner = app_elem.attrib.get(qname("banner"), banner_drawable)
        app_label = app_elem.attrib.get(qname("label"))
        app_icon = app_elem.attrib.get(qname("icon"))

        activities = app_elem.findall("activity") + app_elem.findall("activity-alias")
        for act in activities:
            for ifilter in act.findall("intent-filter"):
                has_main = any(a.attrib.get(qname("name")) == "android.intent.action.MAIN" for a in ifilter.findall("action"))
                has_launcher = any(c.attrib.get(qname("name")) == "android.intent.category.LAUNCHER" for c in ifilter.findall("category"))
                if any(c.attrib.get(qname("name")) == "android.intent.category.LEANBACK_LAUNCHER" for c in ifilter.findall("category")):
                    leanback_activities.append(act)

                if has_main and has_launcher:
                    main_activities.append((act, ifilter))

        target_act = None
        if leanback_activities:
            target_act = leanback_activities[0]
        elif main_activities:
            target_act, target_filter = main_activities[0]
            cat = ET.Element("category", {qname("name"): "android.intent.category.LEANBACK_LAUNCHER"})
            target_filter.append(cat)
            act_name = target_act.attrib.get(qname("name"), "MainActivity")
            changes.append(f"Added LEANBACK_LAUNCHER category to {act_name}")
        else:
            all_acts = app_elem.findall("activity")
            if all_acts:
                target_act = all_acts[0]
                new_filter = ET.Element("intent-filter")
                new_filter.append(ET.Element("action", {qname("name"): "android.intent.action.MAIN"}))
                new_filter.append(ET.Element("category", {qname("name"): "android.intent.category.LEANBACK_LAUNCHER"}))
                target_act.append(new_filter)
                act_name = target_act.attrib.get(qname("name"), "FirstActivity")
                changes.append(f"Created LEANBACK_LAUNCHER intent-filter on {act_name}")

        if target_act is not None:
            if qname("banner") not in target_act.attrib and effective_banner:
                target_act.attrib[qname("banner")] = effective_banner
                act_name = target_act.attrib.get(qname("name"), "MainActivity")
                changes.append(f"Set android:banner='{effective_banner}' on {act_name}")
            if qname("label") not in target_act.attrib and app_label:
                target_act.attrib[qname("label")] = app_label
            if qname("icon") not in target_act.attrib and app_icon:
                target_act.attrib[qname("icon")] = app_icon

    # Write patched manifest back to file
    tree.write(manifest_path, encoding="utf-8", xml_declaration=True)
    return True, changes
