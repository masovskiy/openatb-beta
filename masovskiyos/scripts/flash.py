#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
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


def run_checked(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def normalize_device_name(device: str) -> str:
    if platform.system().lower() == "darwin" and device.startswith("/dev/disk"):
        return "/dev/r" + device.removeprefix("/dev/")
    return device


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write build/openatb.img to a USB device (destructive)."
    )
    parser.add_argument(
        "--device",
        required=True,
        help="Target raw device path (examples: /dev/sdb, /dev/disk4, PhysicalDrive2)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive safety confirmation.",
    )
    return parser.parse_args()


def ensure_confirmation(device: str, *, skip: bool) -> None:
    if skip:
        return
    print("This will overwrite the selected USB device.")
    answer = input(f"Type YES to continue writing to {device}: ").strip()
    if answer != "YES":
        raise SystemExit("Cancelled.")


def flash_unix(image: Path, device: str) -> None:
    dd = resolve_executable(["dd"])
    run_checked(
        [
            dd,
            f"if={image}",
            f"of={device}",
            "bs=4m",
            "conv=fsync",
            "status=progress",
        ]
    )
    run_checked(["sync"])


def flash_windows(image: Path, device: str) -> None:
    raise SystemExit(
        "Direct flashing on Windows is not implemented here. "
        "Use Rufus/balenaEtcher with build/openatb.img."
    )


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    image = root / "build" / "openatb.img"
    if not image.exists():
        build_script = root / "scripts" / "build.py"
        run_checked([sys.executable, str(build_script)])

    device = normalize_device_name(args.device)
    ensure_confirmation(device, skip=args.yes)

    system_name = platform.system().lower()
    if system_name == "darwin":
        if os.geteuid() != 0:
            raise SystemExit("Run as root (sudo) to write block devices.")
        diskutil = resolve_executable(["diskutil"])
        run_checked([diskutil, "unmountDisk", args.device])
        flash_unix(image, device)
        run_checked([diskutil, "eject", args.device])
        print(f"USB ready: {args.device}")
        return 0

    if system_name == "linux":
        if os.geteuid() != 0:
            raise SystemExit("Run as root (sudo) to write block devices.")
        flash_unix(image, device)
        print(f"USB ready: {device}")
        return 0

    if system_name.startswith("win"):
        flash_windows(image, device)
        return 0

    raise SystemExit(f"Unsupported platform: {platform.system()}")


if __name__ == "__main__":
    sys.exit(main())
