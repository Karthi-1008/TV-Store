#!/usr/bin/env python3
"""Unified CLI for APK -> Android TV Remote-Native Converter.
"""
import argparse
from pathlib import Path
import sys
import time

from scanner import scan_apk, format_text_report, Verdict, Tier
from engine_a import convert_apk_engine_a

def cmd_scan(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Error: Target path '{target}' does not exist.", file=sys.stderr)
        return 1

    apks = []
    if target.is_dir():
        apks = sorted(list(target.glob("*.apk")))
        if not apks:
            print(f"No .apk files found in directory: {target}")
            return 0
    else:
        apks = [target]

    print(f"\nScanning {len(apks)} APK file(s)...\n")
    for apk in apks:
        res = scan_apk(apk)
        print(format_text_report(res))
        print("\n")
    return 0

def cmd_convert(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"Error: Target path '{target}' does not exist.", file=sys.stderr)
        return 1

    apks = []
    if target.is_dir():
        apks = sorted(list(target.glob("*.apk")))
        if not apks:
            print(f"No .apk files found in directory: {target}")
            return 0
    else:
        apks = [target]

    print(f"\n==================================================")
    print(f"  TV-Store Converter: Processing {len(apks)} APK(s)")
    print(f"==================================================\n")

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, apk in enumerate(apks, 1):
        print(f"[{idx}/{len(apks)}] Converting: {apk.name}")
        out_path = Path(args.output).resolve() if args.output else None
        if out_path and target.is_dir():
            out_path = out_path / f"{apk.stem}_tv.apk"

        conv_res = convert_apk_engine_a(
            input_apk=apk,
            output_apk=out_path,
            allow_manual_calibration=args.allow_manual_calibration,
            allow_risky=args.allow_risky,
        )

        if not conv_res.success:
            if conv_res.scan_result.verdict == Verdict.REJECT:
                print(f"  -> SKIPPED (Excluded): {conv_res.error_message}")
                skipped_count += 1
            elif conv_res.scan_result.verdict == Verdict.WARN_RISKY:
                print(f"  -> STOPPED (Soft Integrity Protection):")
                print(f"     {conv_res.error_message}")
                if conv_res.log_file:
                    print(f"     Log saved to: {conv_res.log_file}")
                skipped_count += 1
            elif conv_res.scan_result.tier == Tier.TIER_4_CUSTOM_CANVAS:
                print(f"  -> SKIPPED (Tier 4 Manual Calibration Needed): {conv_res.error_message}")
                skipped_count += 1
            else:
                print(f"  -> FAILED: {conv_res.error_message}", file=sys.stderr)
                if conv_res.log_file:
                    print(f"     Detailed stage log saved to: {conv_res.log_file}", file=sys.stderr)
                failed_count += 1
        else:
            print(f"  -> SUCCESS! Created TV-ready APK:")
            print(f"     File:      {conv_res.output_apk}")
            print(f"     Time:      {conv_res.duration_seconds:.1f}s")
            print(f"     Mode:      {conv_res.scan_result.capabilities.ui_framework} (Browser: {conv_res.scan_result.capabilities.is_browser})")
            print(f"     Manifest:  {len(conv_res.manifest_changes)} changes applied")
            for c in conv_res.manifest_changes:
                print(f"       + {c}")
            print(f"     Focus Pass: {conv_res.widgets_patched} widgets across {conv_res.layout_files_patched} layout files")
            if conv_res.log_file:
                print(f"     Stage Log: {conv_res.log_file}")
            print()
            success_count += 1

    print("==================================================")
    print(f"Conversion Summary: {success_count} Succeeded | {skipped_count} Safely Skipped | {failed_count} Failed")
    print("==================================================\n")
    return 0 if failed_count == 0 else 1

def main():
    parser = argparse.ArgumentParser(
        description="Convert touch-only Android APKs to Android TV Remote-Native APKs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Run Phase 0 Pre-flight capability scanner on an APK or directory.")
    scan_parser.add_argument("target", help="Path to .apk file or directory of APKs.")

    # Convert command
    conv_parser = subparsers.add_parser("convert", help="Convert an APK to Android TV format.")
    conv_parser.add_argument("target", help="Path to .apk file or directory of APKs.")
    conv_parser.add_argument("-o", "--output", help="Output .apk path or destination directory.")
    conv_parser.add_argument(
        "--allow-manual-calibration",
        action="store_true",
        help="Allow attempting conversion of Tier 4 (custom canvas) apps.",
    )
    conv_parser.add_argument(
        "--allow-risky",
        action="store_true",
        help="Allow converting apps with soft integrity checks (Play Integrity / SafetyNet / RootBeer).",
    )

    args = parser.parse_args()
    if args.command == "scan":
        sys.exit(cmd_scan(args))
    elif args.command == "convert":
        sys.exit(cmd_convert(args))

if __name__ == "__main__":
    main()
