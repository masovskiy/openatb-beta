#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_executable(candidates: list[str]) -> str:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    raise SystemExit(f"Missing executable. Tried: {', '.join(candidates)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run OpenATB image in QEMU without wiping persisted OpenASM-FS state."
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild image before run (default: keep existing image).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    build_script = root / "scripts" / "build.py"
    image = root / "build" / "openatb.img"
    if args.rebuild or not image.exists():
        subprocess.run([sys.executable, str(build_script)], check=True)

    qemu = resolve_executable(
        [
            "qemu-system-i386",
            "qemu-system-x86_64",
            "qemu-system-i386.exe",
            "qemu-system-x86_64.exe",
        ]
    )
    subprocess.run(
        [
            qemu,
            "-fda",
            str(image),
            "-device",
            "isa-debug-exit,iobase=0xf4,iosize=0x04",
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
