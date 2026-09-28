"""Engine A conversion pipeline: Decompile -> Banner -> Manifest -> Focus -> Build -> Zipalign -> Sign.
Includes stage-tagged logging, fallback rebuild options, and mode configuration.
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
    log_file: Optional[Path] = None

def convert_apk_engine_a(
    input_apk: Path,
    output_apk: Optional[Path] = None,
    allow_manual_calibration: bool = False,
    allow_risky: bool = False,
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

    stage_logs: List[str] = []

    def log_stage(stage: str, msg: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        stage_logs.append(f"[{timestamp}] [{stage.upper()}] {msg}")

    def write_log(failed_stage: Optional[str] = None, error_details: Optional[str] = None) -> Path:
        log_dir = output_apk.parent if output_apk else Path("output")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{input_apk.stem}.log"
        content = "\n".join(stage_logs)
        if failed_stage:
            content += f"\n\n[FAILED STAGE: {failed_stage.upper()}]\n{error_details or 'Unknown error'}\n"
        log_file.write_text(content, encoding="utf-8")
        return log_file

    # 1. Stage: Scan
    log_stage("scan", f"Starting pre-flight capability scan on {input_apk.name}")
    scan_res = scan_apk(input_apk)

    if scan_res.verdict == Verdict.REJECT:
        log_stage("scan", f"Rejected: {scan_res.capabilities.exact_risk_signatures}")
        log_file = write_log("scan", f"Rejection blockers: {scan_res.blockers}")
        return ConversionResult(
            success=False,
            output_apk=None,
            scan_result=scan_res,
            manifest_changes=[],
            layout_files_patched=0,
            widgets_patched=0,
            duration_seconds=time.time() - start_time,
            error_message="Conversion rejected by pre-flight scanner: App is in Tier 5 (Hard DRM or Real Game Engine).",
            log_file=log_file,
        )

    if scan_res.verdict == Verdict.WARN_RISKY and not allow_risky:
        log_stage("scan", f"Soft integrity protection detected: {scan_res.capabilities.exact_risk_signatures}")
        log_file = write_log("scan", "Aborted due to soft integrity checks without --allow-risky flag.")
        return ConversionResult(
            success=False,
            output_apk=None,
            scan_result=scan_res,
            manifest_changes=[],
            layout_files_patched=0,
            widgets_patched=0,
            duration_seconds=time.time() - start_time,
            error_message=(
                "App contains soft integrity checks (Play Integrity / SafetyNet / RootBeer). "
                "Re-run with --allow-risky to proceed if you accept the risk of account or feature degradation."
            ),
            log_file=log_file,
        )

    if scan_res.tier == Tier.TIER_4_CUSTOM_CANVAS and not allow_manual_calibration:
        log_stage("scan", "App requires manual hotspot calibration (Tier 4)")
        log_file = write_log("scan", "Tier 4 app without --allow-manual-calibration.")
        return ConversionResult(
            success=False,
            output_apk=None,
            scan_result=scan_res,
            manifest_changes=[],
            layout_files_patched=0,
            widgets_patched=0,
            duration_seconds=time.time() - start_time,
            error_message="App requires manual hotspot calibration (Tier 4). Re-run with --allow-manual-calibration to proceed.",
            log_file=log_file,
        )

    log_stage("scan", f"Scan passed: Framework={scan_res.capabilities.ui_framework}, Bridge={scan_res.capabilities.needs_bridge}, Browser={scan_res.capabilities.is_browser}")

    work_dir = Path(tempfile.mkdtemp(prefix="tvstore_conv_"))
    decompiled_dir = work_dir / "decompiled"
    unaligned_apk = work_dir / "unaligned.apk"
    apktool_jar = config.ensure_apktool()

    try:
        # 2. Stage: Decompile
        log_stage("decompile", f"Decompiling APK resources with apktool: {input_apk}")
        cmd_decompile = [
            config.JAVA_CMD, "-jar", str(apktool_jar),
            "d", "-f", "-o", str(decompiled_dir), str(input_apk)
        ]
        proc = subprocess.run(cmd_decompile, capture_output=True, text=True, errors="replace", check=False)
        if proc.returncode != 0:
            log_stage("decompile", f"Decompile error: {proc.stderr}")
            log_file = write_log("decompile", f"{proc.stderr}\n{proc.stdout}")
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=[],
                layout_files_patched=0,
                widgets_patched=0,
                duration_seconds=time.time() - start_time,
                error_message=f"[decompile] apktool decompile failed:\n{proc.stderr}",
                log_file=log_file,
            )

        # 3. Stage: Banner
        log_stage("banner", f"Generating Android TV 320x180 banner for {scan_res.metadata.app_label}")
        generate_tv_banner(
            decompiled_dir=decompiled_dir,
            app_label=scan_res.metadata.app_label,
            icon_ref=scan_res.metadata.icon_path,
        )

        # 4. Stage: Manifest
        bridge_mode = "auto" if scan_res.capabilities.is_browser else ("pointer" if scan_res.capabilities.ui_framework == "canvas" else "navigate")
        log_stage("manifest", f"Patching manifest (LEANBACK_LAUNCHER, hardware relaxation, mode='{bridge_mode}')")
        _, manifest_changes = patch_manifest(decompiled_dir, mode=bridge_mode)
        for ch in manifest_changes:
            log_stage("manifest", f"  + {ch}")

        # 5. Stage: Focus Pass
        log_stage("focus", "Applying spatial D-pad focus tags to XML layouts")
        layouts_patched, widgets_patched = patch_all_layouts(decompiled_dir)
        log_stage("focus", f"Patched {widgets_patched} widgets across {layouts_patched} layout files")

        # 6. Stage: Recompile (with aapt2 fallback)
        log_stage("recompile", "Recompiling APK with apktool")
        cmd_build = [
            config.JAVA_CMD, "-jar", str(config.APKTOOL_JAR),
            "b", "-o", str(unaligned_apk), str(decompiled_dir)
        ]
        proc_build = subprocess.run(cmd_build, capture_output=True, text=True, errors="replace", check=False)
        if proc_build.returncode != 0:
            log_stage("recompile", "Standard apktool build failed, attempting fallback with --use-aapt2")
            cmd_build_aapt2 = [
                config.JAVA_CMD, "-jar", str(config.APKTOOL_JAR),
                "b", "--use-aapt2", "-o", str(unaligned_apk), str(decompiled_dir)
            ]
            proc_build = subprocess.run(cmd_build_aapt2, capture_output=True, text=True, errors="replace", check=False)
            if proc_build.returncode != 0:
                log_stage("recompile", f"Recompile failed: {proc_build.stderr}")
                log_file = write_log("recompile", f"{proc_build.stderr}\n{proc_build.stdout}")
                return ConversionResult(
                    success=False,
                    output_apk=None,
                    scan_result=scan_res,
                    manifest_changes=manifest_changes,
                    layout_files_patched=layouts_patched,
                    widgets_patched=widgets_patched,
                    duration_seconds=time.time() - start_time,
                    error_message=f"[recompile] apktool recompile failed:\n{proc_build.stderr}",
                    log_file=log_file,
                )

        # 7. Stage: Align
        log_stage("align", "Running zipalign 4-byte page alignment")
        if not config.ZIPALIGN_EXE or not config.ZIPALIGN_EXE.exists():
            raise RuntimeError("zipalign binary not found in build-tools.")
        cmd_zipalign = [
            str(config.ZIPALIGN_EXE), "-p", "-f", "4",
            str(unaligned_apk), str(output_apk)
        ]
        proc_align = subprocess.run(cmd_zipalign, capture_output=True, text=True, errors="replace", check=False)
        if proc_align.returncode != 0:
            log_stage("align", f"Zipalign failed: {proc_align.stderr}")
            log_file = write_log("align", proc_align.stderr)
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"[align] zipalign failed:\n{proc_align.stderr}",
                log_file=log_file,
            )

        # 8. Stage: Sign
        log_stage("sign", "Signing converted APK with apksigner")
        if not config.APKSIGNER_CMD or not config.APKSIGNER_CMD.exists():
            raise RuntimeError("apksigner binary not found in build-tools.")

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
            log_stage("sign", f"Signing failed: {proc_sign.stderr}")
            log_file = write_log("sign", proc_sign.stderr)
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"[sign] apksigner sign failed:\n{proc_sign.stderr}",
                log_file=log_file,
            )

        # 9. Stage: Verify
        log_stage("verify", "Verifying APK signature")
        cmd_verify = [str(config.APKSIGNER_CMD), "verify", str(output_apk)]
        proc_verify = subprocess.run(cmd_verify, capture_output=True, text=True, errors="replace", check=False)
        if proc_verify.returncode != 0:
            log_stage("verify", f"Verification failed: {proc_verify.stderr}")
            log_file = write_log("verify", proc_verify.stderr)
            return ConversionResult(
                success=False,
                output_apk=None,
                scan_result=scan_res,
                manifest_changes=manifest_changes,
                layout_files_patched=layouts_patched,
                widgets_patched=widgets_patched,
                duration_seconds=time.time() - start_time,
                error_message=f"[verify] apksigner verification failed:\n{proc_verify.stderr}",
                log_file=log_file,
            )

        log_stage("done", f"Conversion completed successfully in {time.time() - start_time:.2f}s")
        log_file = write_log()

        return ConversionResult(
            success=True,
            output_apk=output_apk,
            scan_result=scan_res,
            manifest_changes=manifest_changes,
            layout_files_patched=layouts_patched,
            widgets_patched=widgets_patched,
            duration_seconds=time.time() - start_time,
            error_message=None,
            log_file=log_file,
        )

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
