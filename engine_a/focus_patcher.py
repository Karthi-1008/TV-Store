"""Focus patcher for Android TV.
Scans decompiled XML layout files and injects focusable attributes onto interactive elements.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)

def qname(tag_or_attr: str) -> str:
    return f"{{{ANDROID_NS}}}{tag_or_attr}"

INTERACTIVE_TAGS = {
    "Button", "ImageButton", "EditText", "CheckBox", "RadioButton",
    "ToggleButton", "Switch", "SwitchCompat", "Spinner", "SeekBar",
    "RatingBar", "android.widget.Button", "android.widget.ImageButton",
    "android.widget.EditText", "android.widget.CheckBox", "android.widget.RadioButton",
    "com.google.android.material.button.MaterialButton",
    "com.google.android.material.textfield.TextInputEditText",
    "com.google.android.material.switchmaterial.SwitchMaterial",
}

def patch_layout_xml(xml_path: Path) -> int:
    """Patch a single layout XML file. Returns number of elements modified."""
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return 0

    root = tree.getroot()
    modified_count = 0

    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        is_interactive = False

        if tag_name in INTERACTIVE_TAGS:
            is_interactive = True
        elif elem.attrib.get(qname("clickable")) == "true":
            is_interactive = True
        elif qname("onClick") in elem.attrib:
            is_interactive = True

        if is_interactive:
            changed = False
            if qname("focusable") not in elem.attrib:
                elem.attrib[qname("focusable")] = "true"
                changed = True
            if qname("focusableInTouchMode") not in elem.attrib:
                elem.attrib[qname("focusableInTouchMode")] = "true"
                changed = True
            if changed:
                modified_count += 1

    if modified_count > 0:
        try:
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        except Exception:
            return 0

    return modified_count

def patch_all_layouts(decompiled_dir: Path) -> Tuple[int, int]:
    """Scan all layout files in decompiled res/ and inject focus attributes.
    
    Returns:
        (total_files_patched: int, total_widgets_patched: int)
    """
    decompiled_dir = Path(decompiled_dir)
    res_dir = decompiled_dir / "res"
    if not res_dir.exists():
        return (0, 0)

    total_files = 0
    total_widgets = 0

    for layout_dir in res_dir.glob("layout*"):
        if not layout_dir.is_dir():
            continue
        for xml_file in layout_dir.glob("*.xml"):
            count = patch_layout_xml(xml_file)
            if count > 0:
                total_files += 1
                total_widgets += count

    return (total_files, total_widgets)
