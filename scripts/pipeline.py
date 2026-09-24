#!/usr/bin/env python3
"""Build and audit one prepared reconstruction scene with compact output."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("economy", "standard", "strict"),
        default="economy",
    )
    parser.add_argument("--fontconfig-file", type=Path)
    parser.add_argument("--crop-failures", action="store_true")
    args = parser.parse_args()

    scripts = Path(__file__).resolve().parent
    run_dir = args.run_dir.resolve()
    build_dir = run_dir / "build"
    qa_dir = run_dir / "qa"
    run_dir.mkdir(parents=True, exist_ok=True)

    font_args = (
        ["--fontconfig-file", str(args.fontconfig_file.resolve())]
        if args.fontconfig_file
        else []
    )
    build = subprocess.run(
        [
            sys.executable,
            str(scripts / "build_deck.py"),
            "--scene",
            str(args.scene.resolve()),
            "--output",
            str(args.output.resolve()),
            "--run-dir",
            str(build_dir),
            *font_args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode:
        payload = {
            "status": "failed",
            "stage": "build",
            "message": (build.stdout + "\n" + build.stderr).strip()[-2000:],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return build.returncode

    qa = subprocess.run(
        [
            sys.executable,
            str(scripts / "run_qa.py"),
            "--scene",
            str(args.scene.resolve()),
            "--pptx",
            str(args.output.resolve()),
            "--qa-dir",
            str(qa_dir),
            "--mode",
            args.mode,
            *(["--crop-failures"] if args.crop_failures else []),
            *font_args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    summary_path = qa_dir / "qa-summary.json"
    if summary_path.exists():
        print(summary_path.read_text(encoding="utf-8"))
    else:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "stage": "qa",
                    "message": (qa.stdout + "\n" + qa.stderr).strip()[-2000:],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return qa.returncode


if __name__ == "__main__":
    raise SystemExit(main())
