"""Engine A conversion pipeline: Decompile -> Banner -> Manifest -> Focus -> Build -> Zipalign -> Sign.
"""
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

import config
from scanner.apk_inspector import scan_apk, APKScanResult
from scanner.rules import Tier, Verdict
from engine_a.banner_gen import generate_tv_banner
from engine_a.manifest_patcher import patch_manifest
from engine_a.focus_patcher import patch_all_layouts

@dataclass
class ConversionResult:
    success: bool
    output_apk: Optional[Path]
    scan_result: APKScanResult
    manifest_changes: List[str]
    layout_files_patched: int
    widgets_patched: int
    duration_seconds: float
    error_message: Optional[str] = None

def convert_apk_engine_a(
    input_apk: Path,
    output_apk: Optional[Path] = None,
    allow_manual_calibration: bool = False,
    keystore_path: Optional[Path] = None,
    keystore_pass: str = config.KEYSTORE_PASS,
    key_alias: str = config.KEY_ALIAS,
    key_pass: str = config.KEY_PASS,
) -> ConversionResult:
    """Execute full Engine A conversion pipeline on input APK."""
    start_time = time.time()
    input_apk = Path(input_apk).resolve()
    if not input_apk.exists():
        raise FileNotFoundError(f"Input APK not found: {input_apk}")

    if output_apk is None:
        output_dir = input_apk.parent / "tv_converted"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_apk = output_dir / f"{input_apk.stem}_tv.apk"
    else:
        output_apk = Path(output_apk).resolve()
        output_apk.parent.mkdir(parents=True, exist_ok=True)

    # 1. Pre-flight Compatibility Scan
    scan_res = scan_apk(input_apk)
    if scan_res.verdict == Verdict.REJECT:
        return ConversionResult(
            success=False,
            output_apk=None,
            scan_result=scan_res,
            manifest_changes=[],
            layout_files_patched=0,
            widgets_patched=0,
            duration_seconds=time.time() - start_time,
            error_message="Conversion rejected by pre-flight scanner: App is in Tier 5 (Games, DRM, or Missing Hardware).",
        )

    if scan_res.tier == Tier.TIER_4_CUSTOM_CANVAS and not allow_manual_calibration:
        return ConversionResult(
            success=False,
            output_apk=None,
            scan_result=scan_res,
            manifest_changes=[],
            layout_files_patched=0,
            widgets_patched=0,
            duration_seconds=time.time() - start_time,
            error_message="App requires manual hotspot calibration (Tier 4). Re-run with --allow-manual-calibration to proceed.",
        )

    work_dir = Path(tempfile.mkdtemp(prefix="tvstore_conv_"))
    decompiled_dir = work_dir / "decompiled"
    unaligned_apk = work_dir / "unaligned.apk"
    apktool_jar = config.ensure_apktool()

    try:
        # 2. Decompile with apktool
        cmd_decompile = [
            config.JAVA_CMD, "-jar", str(apktool_jar),
            "d", "-f", "-o", str(decompiled_dir), str(input_apk)
        ]
        proc = subprocess.run(cmd_decompile, capture_output=True, text=True, errors="replace", check=False)
        if proc.returncode != 0:
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=[],
                layout_files_patched=0,
                widgets_patched=0,
                duration_seconds=time.time() - start_time,
                error_message=f"apktool decompile failed:\n{proc.stderr}\n{proc.stdout}",
            )

        # 3. Generate Android TV Banner
        generate_tv_banner(
            decompiled_dir=decompiled_dir,
            app_label=scan_res.metadata.app_label,
            icon_ref=scan_res.metadata.icon_path,
        )

        # 4. Patch Manifest
        _, manifest_changes = patch_manifest(decompiled_dir)

        # 5. Focus-order Pass on Layouts
        layouts_patched, widgets_patched = patch_all_layouts(decompiled_dir)

        # 6. Recompile with apktool
        cmd_build = [
            config.JAVA_CMD, "-jar", str(config.APKTOOL_JAR),
            "b", "-o", str(unaligned_apk), str(decompiled_dir)
        ]
        proc_build = subprocess.run(cmd_build, capture_output=True, text=True, errors="replace", check=False)
        if proc_build.returncode != 0:
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"apktool recompile failed:\n{proc_build.stderr}\n{proc_build.stdout}",
            )

        # 7. Zipalign
        if not config.ZIPALIGN_EXE or not config.ZIPALIGN_EXE.exists():
            raise RuntimeError("zipalign binary not found.")
        cmd_zipalign = [
            str(config.ZIPALIGN_EXE), "-p", "-f", "4",
            str(unaligned_apk), str(output_apk)
        ]
        proc_align = subprocess.run(cmd_zipalign, capture_output=True, text=True, errors="replace", check=False)
        if proc_align.returncode != 0:
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"zipalign failed:\n{proc_align.stderr}",
            )

        # 8. Sign with apksigner
        if not config.APKSIGNER_CMD or not config.APKSIGNER_CMD.exists():
            raise RuntimeError("apksigner binary not found.")

        ks = keystore_path or config.DEFAULT_KEYSTORE
        cmd_sign = [
            str(config.APKSIGNER_CMD), "sign",
            "--ks", str(ks),
            "--ks-pass", f"pass:{keystore_pass}",
            "--ks-key-alias", key_alias,
            "--key-pass", f"pass:{key_pass}",
            str(output_apk)
        ]
        proc_sign = subprocess.run(cmd_sign, capture_output=True, text=True, errors="replace", check=False)
        if proc_sign.returncode != 0:
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"apksigner sign failed:\n{proc_sign.stderr}",
            )

        # 9. Verify Signature
        cmd_verify = [str(config.APKSIGNER_CMD), "verify", str(output_apk)]
        proc_verify = subprocess.run(cmd_verify, capture_output=True, text=True, errors="replace", check=False)
        if proc_verify.returncode != 0:
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"apksigner verification failed:\n{proc_verify.stderr}",
            )

        return ConversionResult(
            success=True,
            output_apk=output_apk,
            scan_result=scan_res,
            manifest_changes=manifest_changes,
            layout_files_patched=layouts_patched,
            widgets_patched=widgets_patched,
            duration_seconds=time.time() - start_time,
            error_message=None,
        )

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
