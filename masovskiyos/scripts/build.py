#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

KERNEL_SECTORS = 127
IMAGE_SECTORS = 2880
SECTOR_SIZE = 512


def resolve_executable(candidates: list[str]) -> str:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    raise SystemExit(f"Missing executable. Tried: {', '.join(candidates)}")


def run_checked(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    build_dir = root / "build"
    build_dir.mkdir(exist_ok=True)

    nasm = resolve_executable(["nasm", "nasm.exe"])
    boot_src = root / "src" / "boot" / "boot.asm"
    kernel_src = root / "src" / "kernel" / "kernel.asm"
    boot_bin = build_dir / "boot.bin"
    kernel_bin = build_dir / "kernel.bin"

    run_checked([nasm, "-f", "bin", str(boot_src), "-o", str(boot_bin)])
    run_checked([nasm, "-f", "bin", str(kernel_src), "-o", str(kernel_bin)])

    kernel_size = kernel_bin.stat().st_size
    max_size = KERNEL_SECTORS * SECTOR_SIZE
    if kernel_size > max_size:
        raise SystemExit(
            f"Kernel is {kernel_size} bytes, max is {max_size} bytes. "
            "Reduce size or increase KERNEL_SECTORS."
        )

    boot_bytes = boot_bin.read_bytes()
    kernel_bytes = kernel_bin.read_bytes()
    image_size = IMAGE_SECTORS * SECTOR_SIZE
    image = bytearray(image_size)
    image[0 : len(boot_bytes)] = boot_bytes
    kernel_offset = SECTOR_SIZE
    image[kernel_offset : kernel_offset + len(kernel_bytes)] = kernel_bytes

    image_path = build_dir / "openatb.img"
    image_path.write_bytes(image)
    print(f"Image ready: {image_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
