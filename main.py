#!/usr/bin/env python3
from __future__ import annotations

## (c) Roman Masovskiy 2026. All rights reserved.

import sys


def _sanitize_bootstrap_sys_path() -> None:
    # Running as `python3 ../main.py` may leave relative entries like `..` in sys.path.
    # On some systems/import states this can raise FileNotFoundError before argparse import.
    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in sys.path:
        if entry in ("", ".", ".."):
            continue
        if entry.startswith("./") or entry.startswith("../"):
            continue
        if entry not in seen:
            cleaned.append(entry)
            seen.add(entry)
    if cleaned:
        sys.path[:] = cleaned


_sanitize_bootstrap_sys_path()

import argparse
import re
import shlex
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

TOOL_NAME = "Open Assembly ToolBox"
TOOL_VERSION = "0.2.0"
PROJECT_SENTINEL = ".oatb_project"
# Keep <=127 sectors so bootloader's 16-bit offset does not wrap and corrupt kernel start.
KERNEL_SECTORS = 127
KNOWN_PACKAGE_MANAGERS = (
    "brew",
    "apt-get",
    "dnf",
    "pacman",
    "zypper",
    "apk",
    "winget",
    "choco",
    "scoop",
)

HOST_APP_CATALOG: dict[str, dict[str, object]] = {
    "python": {
        "description": "Python runtime for tooling and scripts.",
        "check_bins": ("python3", "python"),
        "packages": {
            "brew": "python",
            "apt-get": "python3",
            "dnf": "python3",
            "pacman": "python",
            "zypper": "python3",
            "apk": "python3",
            "winget": "Python.Python.3",
            "choco": "python",
            "scoop": "python",
        },
    },
    "neofetch": {
        "description": "Terminal system-info banner utility.",
        "check_bins": ("neofetch",),
        "packages": {
            "brew": "neofetch",
            "apt-get": "neofetch",
            "dnf": "neofetch",
            "pacman": "neofetch",
            "zypper": "neofetch",
            "apk": "neofetch",
            "choco": "neofetch",
            "scoop": "neofetch",
        },
    },
    "screenfetch": {
        "description": "Alternative terminal system-info banner utility.",
        "check_bins": ("screenfetch",),
        "packages": {
            "apt-get": "screenfetch",
            "dnf": "screenfetch",
            "pacman": "screenfetch",
            "zypper": "screenfetch",
            "apk": "screenfetch",
            "choco": "screenfetch",
            "scoop": "screenfetch",
        },
    },
    "nasm": {
        "description": "Assembler required for OpenATB image builds.",
        "check_bins": ("nasm",),
        "packages": {
            "brew": "nasm",
            "apt-get": "nasm",
            "dnf": "nasm",
            "pacman": "nasm",
            "zypper": "nasm",
            "apk": "nasm",
            "choco": "nasm",
            "scoop": "nasm",
        },
    },
    "qemu": {
        "description": "VM runtime for booting OpenATB images.",
        "check_bins": ("qemu-system-i386", "qemu-system-x86_64"),
        "packages": {
            "brew": "qemu",
            "apt-get": "qemu-system-x86",
            "dnf": "qemu-system-x86",
            "pacman": "qemu-full",
            "zypper": "qemu-x86",
            "apk": "qemu-system-x86_64",
            "choco": "qemu",
            "scoop": "qemu",
        },
    },
}


@dataclass(frozen=True)
class PatchAction:
    file: str
    marker: str
    snippet: str


@dataclass(frozen=True)
class PatchDefinition:
    description: str
    actions: tuple[PatchAction, ...]
    created_files: tuple[tuple[str, str], ...] = ()


def _block(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n").rstrip() + "\n"


def safe_identifier(raw_name: str) -> str:
    cleaned = raw_name.strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        raise ValueError("Name must contain at least one letter or number.")
    if cleaned[0].isdigit():
        cleaned = f"cmd_{cleaned}"
    return cleaned


def write_text(path: Path, content: str, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"File already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_project(project_root: Path) -> None:
    sentinel = project_root / PROJECT_SENTINEL
    if not sentinel.exists():
        raise FileNotFoundError(
            f"Not an OpenATB project: {project_root} (missing {PROJECT_SENTINEL})"
        )


def append_unique_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    content = path.read_text(encoding="utf-8")
    existing_lines = {item.strip() for item in content.splitlines()}
    if line.strip() in existing_lines:
        return
    if content and not content.endswith("\n"):
        content += "\n"
    content += line + "\n"
    path.write_text(content, encoding="utf-8")


def package_manager_priority() -> tuple[str, ...]:
    if sys.platform == "darwin":
        return ("brew", "apt-get", "dnf", "pacman", "zypper", "apk")
    if sys.platform.startswith("win"):
        return ("winget", "choco", "scoop")
    return ("apt-get", "dnf", "pacman", "zypper", "apk", "brew")


def detect_package_managers() -> list[str]:
    detected: list[str] = []
    for manager in package_manager_priority():
        if shutil.which(manager):
            detected.append(manager)
    return detected


def first_installed_path(binaries: tuple[str, ...]) -> str | None:
    for binary in binaries:
        resolved = shutil.which(binary)
        if resolved:
            return resolved
    return None


def resolve_app_record(app_name: str) -> tuple[str, dict[str, object], bool]:
    normalized = app_name.strip().lower()
    record = HOST_APP_CATALOG.get(normalized)
    if record is not None:
        return normalized, record, True

    return (
        normalized,
        {
            "description": f"Custom package '{normalized}'",
            "check_bins": (normalized,),
            "packages": {manager: normalized for manager in KNOWN_PACKAGE_MANAGERS},
        },
        False,
    )


def resolve_package_manager(manager: str) -> str:
    if manager != "auto":
        if manager not in KNOWN_PACKAGE_MANAGERS:
            raise ValueError(
                f"Unsupported package manager '{manager}'. "
                f"Use one of: {', '.join(KNOWN_PACKAGE_MANAGERS)}"
            )
        if shutil.which(manager) is None:
            raise FileNotFoundError(f"Package manager is not installed: {manager}")
        return manager

    detected = detect_package_managers()
    if not detected:
        raise RuntimeError(
            "No supported package manager detected. "
            "Install one of: brew, apt-get, dnf, pacman, zypper, apk, winget, choco, scoop."
        )
    return detected[0]


def build_install_commands(
    manager: str,
    package_name: str,
    *,
    use_sudo: bool,
    yes: bool,
    update_index: bool,
) -> list[list[str]]:
    def maybe_sudo(cmd: list[str]) -> list[str]:
        if use_sudo and manager in {"apt-get", "dnf", "pacman", "zypper", "apk"}:
            return ["sudo", *cmd]
        return cmd

    commands: list[list[str]] = []

    if manager == "brew":
        commands.append(["brew", "install", package_name])
    elif manager == "apt-get":
        if update_index:
            commands.append(maybe_sudo(["apt-get", "update"]))
        cmd = ["apt-get", "install"]
        if yes:
            cmd.append("-y")
        cmd.append(package_name)
        commands.append(maybe_sudo(cmd))
    elif manager == "dnf":
        cmd = ["dnf", "install"]
        if yes:
            cmd.append("-y")
        cmd.append(package_name)
        commands.append(maybe_sudo(cmd))
    elif manager == "pacman":
        if update_index:
            sync_cmd = ["pacman", "-Sy"]
            if yes:
                sync_cmd.append("--noconfirm")
            commands.append(maybe_sudo(sync_cmd))
        cmd = ["pacman", "-S"]
        if yes:
            cmd.append("--noconfirm")
        cmd.append(package_name)
        commands.append(maybe_sudo(cmd))
    elif manager == "zypper":
        cmd = ["zypper", "install"]
        if yes:
            cmd.insert(1, "--non-interactive")
        cmd.append(package_name)
        commands.append(maybe_sudo(cmd))
    elif manager == "apk":
        cmd = ["apk", "add"]
        cmd.append(package_name)
        commands.append(maybe_sudo(cmd))
    elif manager == "winget":
        cmd = ["winget", "install", "--exact", package_name]
        if yes:
            cmd.extend(["--accept-package-agreements", "--accept-source-agreements"])
        commands.append(cmd)
    elif manager == "choco":
        cmd = ["choco", "install"]
        if yes:
            cmd.append("-y")
        cmd.append(package_name)
        commands.append(cmd)
    elif manager == "scoop":
        commands.append(["scoop", "install", package_name])
    else:
        raise ValueError(f"Unsupported package manager implementation: {manager}")

    return commands


def run_install_commands(commands: list[list[str]], *, dry_run: bool) -> None:
    for command in commands:
        print("[run] " + " ".join(shlex.quote(part) for part in command))
        if dry_run:
            continue
        subprocess.run(command, check=True)


def boot_asm_template(project_name: str) -> str:
    return _block(
        f"""
        ; ==================================================================
        ; OpenAssemblyToolBox -- The OpenATB bootloader
        ; Copyright (C) 2026 Roman Mas0vsk1yy
        ;
        ; Loads the kernel (KERNEL.BIN) for execution.
        ; Uses OpenASM file system.
        ; ==================================================================

        [org 0x7C00]
        [bits 16]

        KERNEL_SEGMENT equ 0x1000
        KERNEL_OFFSET  equ 0x0000
        KERNEL_SECTORS equ {KERNEL_SECTORS}

        start:
            mov [BOOT_DRIVE], dl
            cli
            xor ax, ax
            mov ds, ax
            mov es, ax
            mov ss, ax
            mov sp, 0x7C00
            sti

            mov ax, 0x0003
            int 0x10

            mov si, log_boot
            call print_string
            ; OATB_PATCH_BOOT_CODE

            mov ax, KERNEL_SEGMENT
            mov es, ax
            mov bx, KERNEL_OFFSET
            mov dh, KERNEL_SECTORS
            mov dl, [BOOT_DRIVE]
            call disk_load
            mov si, log_step_jump
            call print_string
            mov dl, [BOOT_DRIVE]
            jmp KERNEL_SEGMENT:KERNEL_OFFSET

        hang:
            jmp hang

        disk_load:
            pusha
            mov di, bx
            mov si, 1
            mov [KERNEL_LEFT], dh
        .load_next:
            cmp byte [KERNEL_LEFT], 0
            je .done

            mov ax, si
            xor dx, dx
            mov bp, 36
            div bp
            mov ch, al

            mov ax, dx
            xor dx, dx
            mov bp, 18
            div bp
            mov dh, al
            mov cl, dl
            inc cl

            mov bx, di
            mov dl, [BOOT_DRIVE]
            mov ah, 0x02
            mov al, 1
            int 0x13
            jc disk_error

            inc si
            add di, 512
            dec byte [KERNEL_LEFT]
            jmp .load_next
        .done:
            popa
            ret

        disk_error:
            mov si, disk_error_msg
            call print_string
            jmp hang

        print_string:
            mov ah, 0x0E
        .loop:
            lodsb
            cmp al, 0
            je .done
            int 0x10
            jmp .loop
        .done:
            ret

        BOOT_DRIVE db 0
        KERNEL_LEFT db 0

        log_boot db 13,10, "[BOOT] Open Assembly ToolBox (OpenATB)", 13,10, "[BOOT] 1/4 BIOS ready, 16-bit real mode.", 13,10, "[BOOT] 2/4 Disk I/O ready.", 13,10, "[BOOT] 3/4 Loading KERNEL.BIN sectors...", 13,10, 0
        log_step_jump db "[ OK ] 4/4 Kernel loaded. Jump 1000:0000.", 13,10, 0
        disk_error_msg db "[FAIL] Disk read error. System halted.", 13,10, 0
        ; OATB_PATCH_BOOT_DATA

        times 510-($-$$) db 0
        dw 0xAA55
        """
    )


def kernel_asm_template() -> str:
    return _block(
        """
        ; ==================================================================
        ; OpenAssemblyToolBox -- OpenATB kernel
        ; Copyright (C) 2026 Roman Mas0vsk1yy
        ;
        ; Core shell runtime, Open Assembly FS, and OATB DevKit support.
        ; ==================================================================

        [org 0x0000]
        [bits 16]

        MAX_INPUT equ 255
        USER_MAX  equ 32
        PASS_MAX equ 32
        REGION_MAX equ 23
        FS_NAME_MAX equ 31
        FS_TEXT_MAX equ 3072
        NANO_MAX_LINES equ 1000
        FS_STORE_LBA equ 256
        FS_STORE_SECTORS equ 64
        FS_STORE_SEG equ 0x2000
        FS_STORE_BUFFER equ 0x0000

        COLOR_DEFAULT equ 0x07
        COLOR_INFO    equ 0x0B
        COLOR_WARN    equ 0x0E
        COLOR_ERROR   equ 0x0C
        COLOR_PROMPT  equ 0x0A
        COLOR_ASCII   equ 0x0D
        COLOR_FRAME   equ 0x09
        COLOR_ACCENT  equ 0x03
        COLOR_TITLE   equ 0x0F
        COLOR_BANNER_1 equ 0x09
        COLOR_BANNER_2 equ 0x0B
        COLOR_BANNER_3 equ 0x0D
        COLOR_BANNER_4 equ 0x0E
        COLOR_BANNER_5 equ 0x0A
        COLOR_BANNER_6 equ 0x03

        start:
            cli
            mov ax, cs
            mov ds, ax
            mov es, ax
            mov [boot_drive], dl
            mov ax, 0x7000
            mov ss, ax
            mov sp, 0xFFF0
            sti
            call clear_screen
            call show_banner
            mov bl, COLOR_TITLE
            mov si, boot_msg
            call print_color_string
            call init_boot_ticks
            call init_openasm_fs
            call init_runtime_strings
            call fs_store_load
            call sanitize_runtime_state
            call first_boot_setup
            call show_boot_notice
            ; OATB_PATCH_KERNEL_BOOT

        shell_loop:
            call show_prompt
            mov di, input_buffer
            call read_line
            mov si, input_buffer
            call dispatch_command
            jmp shell_loop

        dispatch_command:
            cmp byte [si], 0
            je .done

            mov di, cmd_help
            call strcmp
            cmp ax, 1
            je .help

            mov di, cmd_about
            call strcmp
            cmp ax, 1
            je .about

            mov di, cmd_clear
            call strcmp
            cmp ax, 1
            je .clear

            mov di, cmd_cls
            call strcmp
            cmp ax, 1
            je .clear

            mov di, cmd_banner
            call strcmd
            cmp ax, 1
            je .banner

            mov di, cmd_patches
            call strcmd
            cmp ax, 1
            je .patches

            mov di, cmd_sys
            call strcmd
            cmp ax, 1
            je .sys

            mov di, cmd_uptime
            call strcmd
            cmp ax, 1
            je .uptime

            mov di, cmd_time
            call strcmd
            cmp ax, 1
            je .time

            mov di, cmd_date
            call strcmd
            cmp ax, 1
            je .date

            mov di, cmd_version
            call strcmd
            cmp ax, 1
            je .version

            mov di, cmd_fetch
            call strcmp
            cmp ax, 1
            je .fetch

            mov di, cmd_exit
            call strcmp
            cmp ax, 1
            je .exit

            mov di, cmd_echo
            call strcmd
            cmp ax, 1
            je .echo

            mov di, cmd_setname
            call strcmd
            cmp ax, 1
            je .setname

            mov di, cmd_region
            call strcmd
            cmp ax, 1
            je .region

            mov di, cmd_passwd
            call strcmd
            cmp ax, 1
            je .passwd

            mov di, cmd_cd
            call strcmd
            cmp ax, 1
            je .cd

            mov di, cmd_reboot
            call strcmp
            cmp ax, 1
            je .reboot

            mov di, cmd_ls
            call strcmp
            cmp ax, 1
            je .fsls

            mov di, cmd_fsls
            call strcmp
            cmp ax, 1
            je .fsls

            mov di, cmd_fsinfo
            call strcmp
            cmp ax, 1
            je .fsinfo

            mov di, cmd_fswrite
            call strcmd
            cmp ax, 1
            je .fswrite

            mov di, cmd_write
            call strcmd
            cmp ax, 1
            je .fswrite

            mov di, cmd_append
            call strcmd
            cmp ax, 1
            je .append

            mov di, cmd_rm
            call strcmd
            cmp ax, 1
            je .rmfile

            mov di, cmd_touch
            call strcmd
            cmp ax, 1
            je .touch

            mov di, cmd_mk
            call strcmd
            cmp ax, 1
            je .touch

            mov di, cmd_mkdir
            call strcmd
            cmp ax, 1
            je .mkdir

            mov di, cmd_rmdir
            call strcmd
            cmp ax, 1
            je .rmdir

            mov di, cmd_cat
            call strcmd
            cmp ax, 1
            je .cat

            mov di, cmd_nano
            call strcmd
            cmp ax, 1
            je .nano

            ; OATB_PATCH_KERNEL_COMMANDS

            cmp byte [msg_unknown], 0
            jne .unknown_ready
            mov si, msg_unknown_default
            mov di, msg_unknown
            mov cx, 63
            call copy_string_limited
        .unknown_ready:

            mov bl, COLOR_ERROR
            mov si, msg_unknown
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .help:
            call show_help
            jmp .done

        .about:
            call show_about
            jmp .done

        .clear:
            call clear_screen
            call show_banner
            jmp .done

        .banner:
            add si, 6
            call skip_spaces
            cmp byte [si], 0
            je .banner_show
            mov di, cmd_clear
            call strcmp
            cmp ax, 1
            je .banner_clear_only
            mov di, arg_full
            call strcmp
            cmp ax, 1
            je .clear
            mov bl, COLOR_WARN
            mov si, msg_banner_usage
            call print_color_string
            jmp .done

        .banner_show:
            call show_banner
            jmp .done

        .banner_clear_only:
            call clear_screen
            jmp .done

        .patches:
            add si, 7
            call skip_spaces
            cmp byte [si], 0
            je .patches_show
            mov di, arg_raw
            call strcmp
            cmp ax, 1
            je .patches_raw
            mov bl, COLOR_WARN
            mov si, msg_patches_usage
            call print_color_string
            jmp .done

        .patches_show:
            call show_patches
            jmp .done

        .patches_raw:
            call show_patches_raw
            jmp .done

        .sys:
            add si, 3
            call skip_spaces
            cmp byte [si], 0
            je .sys_usage
            mov di, arg_info
            call strcmp
            cmp ax, 1
            je .about
            mov di, cmd_time
            call strcmp
            cmp ax, 1
            je .time
            mov di, cmd_date
            call strcmp
            cmp ax, 1
            je .date
            mov di, cmd_uptime
            call strcmp
            cmp ax, 1
            je .uptime
            mov di, cmd_version
            call strcmp
            cmp ax, 1
            je .version
            mov di, cmd_fetch
            call strcmp
            cmp ax, 1
            je .fetch
            mov di, cmd_patches
            call strcmp
            cmp ax, 1
            je .patches_show
            mov di, cmd_banner
            call strcmp
            cmp ax, 1
            je .banner_show

        .sys_usage:
            mov bl, COLOR_WARN
            mov si, msg_sys_usage
            call print_color_string
            jmp .done

        .uptime:
            call show_uptime
            jmp .done

        .time:
            call show_time
            jmp .done

        .date:
            call show_date
            jmp .done

        .version:
            call show_version
            jmp .done

        .fetch:
            call show_fetch
            jmp .done

        .exit:
            call fs_store_save
            call exit_cmd
            jmp .done

        .echo:
            add si, 4
            call skip_spaces
            cmp byte [si], 0
            je .echo_usage

            cmp byte [si], '-'
            jne .echo_plain
            cmp byte [si + 2], ' '
            jne .echo_plain
            mov al, [si + 1]
            cmp al, 'n'
            je .echo_no_newline
            cmp al, 'u'
            je .echo_upper
            cmp al, 'l'
            je .echo_lower
            cmp al, 'h'
            je .echo_usage
            jmp .echo_plain

        .echo_no_newline:
            add si, 2
            call skip_spaces
            cmp byte [si], 0
            je .done
            mov bl, COLOR_INFO
            call print_color_string
            jmp .done

        .echo_upper:
            add si, 2
            call skip_spaces
            cmp byte [si], 0
            je .echo_usage
            mov bl, COLOR_INFO
            call print_upper_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .echo_lower:
            add si, 2
            call skip_spaces
            cmp byte [si], 0
            je .echo_usage
            mov bl, COLOR_INFO
            call print_lower_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .echo_plain:
            mov bl, COLOR_INFO
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .echo_usage:
            mov bl, COLOR_WARN
            mov si, msg_echo_usage
            call print_color_string
            jmp .done

        .setname:
            add si, 7
            call skip_spaces
            cmp byte [si], 0
            je .setname_show

            mov di, arg_reset
            call strcmp
            cmp ax, 1
            je .setname_reset

            mov di, arg_dash_h
            call strcmp
            cmp ax, 1
            je .setname_usage

            mov di, arg_dash_dash_help
            call strcmp
            cmp ax, 1
            je .setname_usage

            mov di, username
            mov cx, USER_MAX
            call copy_string_limited
            mov byte [user_initialized], 1
            mov bl, COLOR_INFO
            mov si, msg_setname_ok_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, username
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            call fs_store_save
            jmp .done

        .setname_show:
            mov bl, COLOR_ACCENT
            mov si, msg_current_user_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            cmp byte [username], 0
            jne .setname_show_name
            mov si, default_user
            call print_color_string
            jmp .setname_show_tail
        .setname_show_name:
            mov si, username
            call print_color_string
        .setname_show_tail:
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .setname_reset:
            mov si, default_user
            mov di, username
            call copy_string
            mov byte [user_initialized], 1
            mov bl, COLOR_INFO
            mov si, msg_setname_reset
            call print_color_string
            call fs_store_save
            jmp .done

        .setname_usage:
            mov bl, COLOR_WARN
            mov si, msg_setname_usage
            call print_color_string
            jmp .done

        .region:
            add si, 6
            call skip_spaces
            cmp byte [si], 0
            je .region_show
            mov di, arg_set
            call strcmp
            cmp ax, 1
            je .region_set
            mov di, arg_dash_h
            call strcmp
            cmp ax, 1
            je .region_usage
            mov di, arg_dash_dash_help
            call strcmp
            cmp ax, 1
            je .region_usage
            jmp .region_usage

        .region_set:
            call region_setup_interactive
            call fs_store_save
            jmp .done

        .region_show:
            call show_region
            jmp .done

        .region_usage:
            mov bl, COLOR_WARN
            mov si, msg_region_usage
            call print_color_string
            jmp .done

        .passwd:
            add si, 6
            call skip_spaces
            cmp byte [si], 0
            je .passwd_set
            mov di, arg_dash_h
            call strcmp
            cmp ax, 1
            je .passwd_usage
            mov di, arg_dash_dash_help
            call strcmp
            cmp ax, 1
            je .passwd_usage
            jmp .passwd_usage

        .passwd_set:
            call password_setup_interactive
            call fs_store_save
            jmp .done

        .passwd_usage:
            mov bl, COLOR_WARN
            mov si, msg_passwd_usage
            call print_color_string
            jmp .done

        .cd:
            add si, 2
            call skip_spaces
            cmp byte [si], 0
            je .cd_show
            mov di, fs_token
            mov cx, FS_NAME_MAX - 1
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            jne .cd_usage

            mov si, fs_token
            mov di, arg_root
            call strcmp
            cmp ax, 1
            je .cd_root
            mov di, arg_dotdot
            call strcmp
            cmp ax, 1
            je .cd_root

            mov si, fs_token
            call fs_dir_exists
            cmp ax, 1
            jne .cd_not_found

            mov si, fs_token
            mov di, current_dir
            mov cx, FS_NAME_MAX - 1
            call copy_string_limited
            call fs_store_save
            jmp .cd_show

        .cd_root:
            mov byte [current_dir], 0
            call fs_store_save
            jmp .cd_show

        .cd_show:
            mov bl, COLOR_ACCENT
            mov si, msg_cd_now
            call print_color_string
            mov bl, COLOR_PROMPT
            cmp byte [current_dir], 0
            jne .cd_show_named
            mov si, arg_root
            call print_color_string
            jmp .cd_show_tail
        .cd_show_named:
            mov al, '/'
            call putc_color
            mov si, current_dir
            call print_color_string
        .cd_show_tail:
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .cd_not_found:
            mov bl, COLOR_ERROR
            mov si, msg_cd_not_found
            call print_color_string
            jmp .done

        .cd_usage:
            mov bl, COLOR_WARN
            mov si, msg_cd_usage
            call print_color_string
            jmp .done

        .reboot:
            call fs_store_save
            call clear_screen
            call show_banner
            call show_boot_notice
            jmp .done

        .fsls:
            call fs_list
            jmp .done

        .fsinfo:
            call fs_info
            jmp .done

        .fswrite:
            add si, 7
            call skip_spaces
            cmp byte [si], 0
            je .fswrite_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            je .fswrite_usage

            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_validate_file_path
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_parent_ready_for_file
            cmp ax, 1
            jne .dir_missing

            mov di, fs_token
            call fs_write_by_name
            cmp ax, 1
            je .done
            cmp ax, 2
            je .fs_full

            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .done

        .append:
            add si, 6
            call skip_spaces
            cmp byte [si], 0
            je .append_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            je .append_usage

            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_validate_file_path
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_parent_ready_for_file
            cmp ax, 1
            jne .dir_missing

            mov di, fs_token
            call fs_append_by_name
            cmp ax, 1
            je .done
            cmp ax, 2
            je .fs_full

            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .done

        .rmfile:
            add si, 2
            call skip_spaces
            cmp byte [si], 0
            je .rm_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited
            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_is_directory_marker
            cmp ax, 1
            je .rm_dir_hint
            mov di, fs_token
            call fs_remove_by_name
            cmp ax, 1
            je .done

            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .done

        .mkdir:
            add si, 5
            call skip_spaces
            cmp byte [si], 0
            je .mkdir_usage
            mov di, dir_token
            mov cx, FS_NAME_MAX - 1
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            jne .mkdir_usage
            mov si, dir_token
            call fs_dir_create
            cmp ax, 1
            je .mkdir_ok
            cmp ax, 2
            je .mkdir_exists
            cmp ax, 3
            je .mkdir_invalid
            mov bl, COLOR_ERROR
            mov si, msg_fs_full
            call print_color_string
            jmp .done

        .mkdir_ok:
            mov bl, COLOR_INFO
            mov si, msg_mkdir_ok_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, dir_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            call fs_store_save
            jmp .done

        .mkdir_exists:
            mov bl, COLOR_WARN
            mov si, msg_mkdir_exists_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, dir_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .mkdir_invalid:
            mov bl, COLOR_WARN
            mov si, msg_mkdir_invalid
            call print_color_string
            jmp .done

        .rmdir:
            add si, 5
            call skip_spaces
            cmp byte [si], 0
            je .rmdir_usage
            mov di, dir_token
            mov cx, FS_NAME_MAX - 1
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            jne .rmdir_usage
            mov si, dir_token
            call fs_dir_remove
            cmp ax, 1
            je .rmdir_ok
            cmp ax, 2
            je .rmdir_not_found
            cmp ax, 3
            je .rmdir_not_empty
            mov bl, COLOR_WARN
            mov si, msg_mkdir_invalid
            call print_color_string
            jmp .done

        .rmdir_ok:
            mov bl, COLOR_INFO
            mov si, msg_rmdir_ok_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, dir_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            call fs_store_save
            jmp .done

        .rmdir_not_found:
            mov bl, COLOR_ERROR
            mov si, msg_rmdir_not_found_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, dir_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .rmdir_not_empty:
            mov bl, COLOR_WARN
            mov si, msg_rmdir_not_empty_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, dir_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .touch:
            cmp byte [si + 1], 'k'
            je .touch_short
            add si, 5
            jmp .touch_parse
        .touch_short:
            add si, 2
        .touch_parse:
            call skip_spaces
            cmp byte [si], 0
            je .touch_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited

            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_validate_file_path
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_parent_ready_for_file
            cmp ax, 1
            jne .dir_missing

            mov si, fs_token
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .touch_exists
            mov si, fs_token
            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .touch_exists
            mov si, fs_token
            mov di, fs_name_user
            call strcmp
            cmp ax, 1
            je .touch_exists
            mov si, fs_token
            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .touch_exists
            mov si, fs_token
            mov di, fs_name_cscript
            call strcmp
            cmp ax, 1
            je .touch_exists
            mov si, fs_token
            mov di, fs_name_custom_yaml
            call strcmp
            cmp ax, 1
            je .touch_exists

            mov si, fs_token
            call fs_user_create
            cmp ax, 1
            je .touch_ok
            cmp ax, 2
            je .touch_exists

            mov bl, COLOR_ERROR
            mov si, msg_fs_full
            call print_color_string
            jmp .done

        .touch_ok:
            mov bl, COLOR_INFO
            mov si, msg_touch_ok_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, fs_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            call fs_store_save
            jmp .done

        .touch_exists:
            mov bl, COLOR_WARN
            mov si, msg_touch_exists_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, fs_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            jmp .done

        .cat:
            add si, 3
            call skip_spaces
            cmp byte [si], 0
            je .cat_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited
            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_validate_cat_path
            cmp ax, 1
            jne .path_invalid

            mov si, fs_token
            call fs_cat_by_name
            cmp ax, 1
            je .done

            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .done

        .nano:
            add si, 4
            call skip_spaces
            cmp byte [si], 0
            je .nano_usage

            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_token_limited
            call skip_spaces
            cmp byte [si], 0
            jne .nano_usage

            mov si, fs_token
            call fs_resolve_with_cwd
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_validate_file_path
            cmp ax, 1
            jne .path_invalid
            mov si, fs_token
            call fs_parent_ready_for_file
            cmp ax, 1
            jne .dir_missing

            call clear_screen
            mov bl, COLOR_ACCENT
            mov si, msg_nano_title
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, fs_token
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string

            mov byte [nano_buffer], 0
            mov word [nano_line_count], 0
            mov si, fs_token
            mov di, nano_buffer
            call fs_copy_by_name
            cmp ax, 1
            jne .nano_new_file
            mov si, nano_buffer
            call count_lines_in_text
            mov [nano_line_count], ax
            mov bl, COLOR_INFO
            mov si, msg_nano_existing
            call print_color_string
            jmp .nano_edit_prompt

        .nano_new_file:
            mov bl, COLOR_WARN
            mov si, msg_nano_new_file
            call print_color_string

        .nano_edit_prompt:
            mov bl, COLOR_INFO
            mov si, msg_nano_prompt_1
            call print_color_string
            mov si, msg_nano_prompt_2
            call print_color_string

        .nano_loop:
            mov bl, COLOR_PROMPT
            mov si, msg_nano_line_prompt
            call print_color_string
            mov di, input_buffer
            mov word [input_limit], MAX_INPUT
            call read_line_limited

            mov si, input_buffer
            mov di, cmd_nano_save
            call strcmp
            cmp ax, 1
            je .nano_save

            mov si, input_buffer
            mov di, cmd_nano_write
            call strcmp
            cmp ax, 1
            je .nano_write

            mov si, input_buffer
            mov di, cmd_nano_help
            call strcmp
            cmp ax, 1
            je .nano_help

            mov si, input_buffer
            mov di, cmd_nano_quit
            call strcmp
            cmp ax, 1
            je .nano_cancel

            cmp word [nano_line_count], NANO_MAX_LINES
            jae .nano_line_limit

            mov si, input_buffer
            mov di, nano_buffer
            call append_line_limited
            cmp ax, 1
            jne .nano_size_limit
            inc word [nano_line_count]
            jmp .nano_loop

        .nano_save:
            mov si, nano_buffer
            mov di, fs_token
            call fs_write_by_name
            cmp ax, 1
            je .done
            cmp ax, 2
            je .fs_full

            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .done

        .nano_write:
            mov si, nano_buffer
            mov di, fs_token
            call fs_write_by_name
            cmp ax, 1
            je .nano_write_ok
            cmp ax, 2
            je .fs_full
            mov bl, COLOR_ERROR
            mov si, msg_file_not_found
            call print_color_string
            jmp .nano_loop
        .nano_write_ok:
            mov bl, COLOR_INFO
            mov si, msg_nano_written
            call print_color_string
            jmp .nano_loop

        .nano_help:
            mov bl, COLOR_INFO
            mov si, msg_nano_prompt_3
            call print_color_string
            jmp .nano_loop

        .nano_line_limit:
            mov bl, COLOR_WARN
            mov si, msg_nano_line_limit
            call print_color_string
            jmp .nano_loop

        .nano_size_limit:
            mov bl, COLOR_WARN
            mov si, msg_nano_size_limit
            call print_color_string
            jmp .nano_loop

        .nano_cancel:
            mov bl, COLOR_WARN
            mov si, msg_nano_cancel
            call print_color_string
            jmp .done

        .rm_dir_hint:
            mov bl, COLOR_WARN
            mov si, msg_rm_dir_hint
            call print_color_string
            jmp .done

        .cat_usage:
            mov bl, COLOR_WARN
            mov si, msg_cat_usage
            call print_color_string
            jmp .done

        .nano_usage:
            mov bl, COLOR_WARN
            mov si, msg_nano_usage
            call print_color_string
            jmp .done

        .fswrite_usage:
            mov bl, COLOR_WARN
            mov si, msg_fswrite_usage
            call print_color_string
            jmp .done

        .append_usage:
            mov bl, COLOR_WARN
            mov si, msg_append_usage
            call print_color_string
            jmp .done

        .rm_usage:
            mov bl, COLOR_WARN
            mov si, msg_rm_usage
            call print_color_string
            jmp .done

        .touch_usage:
            mov bl, COLOR_WARN
            mov si, msg_touch_usage
            call print_color_string
            jmp .done

        .mkdir_usage:
            mov bl, COLOR_WARN
            mov si, msg_mkdir_usage
            call print_color_string
            jmp .done

        .rmdir_usage:
            mov bl, COLOR_WARN
            mov si, msg_rmdir_usage
            call print_color_string
            jmp .done

        .path_invalid:
            mov bl, COLOR_WARN
            mov si, msg_path_invalid
            call print_color_string
            jmp .done

        .dir_missing:
            mov bl, COLOR_ERROR
            mov si, msg_dir_missing
            call print_color_string
            jmp .done

        .fs_full:
            mov bl, COLOR_ERROR
            mov si, msg_fs_full
            call print_color_string

        .done:
            ret

        show_banner:
            cmp byte [cfg_banner_enabled], 1
            jne .done

            mov bl, [cfg_color_frame]
            mov si, banner_top
            call print_color_string

            mov bl, COLOR_BANNER_1
            mov si, art_line_1
            call print_color_string
            mov bl, COLOR_BANNER_2
            mov si, art_line_2
            call print_color_string
            mov bl, COLOR_BANNER_3
            mov si, art_line_3
            call print_color_string
            mov bl, COLOR_BANNER_4
            mov si, art_line_4
            call print_color_string
            mov bl, COLOR_BANNER_5
            mov si, art_line_5
            call print_color_string
            mov bl, COLOR_BANNER_6
            mov si, art_line_6
            call print_color_string
            mov bl, [cfg_color_frame]
            mov si, banner_bottom
            call print_color_string

            mov bl, COLOR_BANNER_2
            mov si, fs_tagline
            call print_color_string

        .done:
            ret

        show_setup_wizard:
            mov bl, [cfg_color_frame]
            mov si, msg_setup_top
            call print_color_string
            mov bl, [cfg_color_ascii]
            mov si, msg_setup_title
            call print_color_string
            mov bl, [cfg_color_frame]
            mov si, msg_setup_sep
            call print_color_string
            mov bl, [cfg_color_info]
            mov si, msg_setup_line_1
            call print_color_string
            mov si, msg_setup_line_2
            call print_color_string
            mov bl, [cfg_color_frame]
            mov si, msg_setup_bottom
            call print_color_string
            ret

        first_boot_setup:
            mov byte [setup_touched], 0
            cmp byte [user_initialized], 1
            jne .needs_setup
            cmp byte [region_initialized], 1
            jne .needs_setup
            cmp byte [password_initialized], 1
            jne .needs_setup
            jmp .done

        .needs_setup:
            call clear_screen
            call show_setup_wizard
            cmp byte [user_initialized], 1
            je .check_region

            mov bl, COLOR_BANNER_2
            mov si, msg_setup_step_user
            call print_color_string
            mov bl, COLOR_WARN
            mov si, msg_pick_name
            call print_color_string
            mov di, username
            mov word [input_limit], USER_MAX
            call read_line_limited
            cmp byte [username], 0
            jne .name_done
            mov si, default_user
            mov di, username
            call copy_string
        .name_done:
            mov byte [user_initialized], 1
            mov byte [setup_touched], 1

        .check_region:
            cmp byte [region_initialized], 1
            je .check_password
            mov bl, COLOR_BANNER_2
            mov si, msg_setup_step_region
            call print_color_string
            call region_setup_interactive

        .check_password:
            cmp byte [password_initialized], 1
            je .finish
            mov bl, COLOR_BANNER_2
            mov si, msg_setup_step_pass
            call print_color_string
            call password_setup_interactive

        .finish:
            cmp byte [setup_touched], 1
            jne .done
            mov bl, COLOR_INFO
            mov si, msg_hello_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            cmp byte [username], 0
            jne .hello_name
            mov si, default_user
            call print_color_string
            jmp .hello_tail
        .hello_name:
            mov si, username
            call print_color_string
        .hello_tail:
            mov bl, COLOR_INFO
            mov si, msg_hello_suffix
            call print_color_string
            call fs_store_save
            mov bl, [cfg_color_frame]
            mov si, msg_setup_done
            call print_color_string
            call clear_screen
            call show_banner
            mov bl, COLOR_TITLE
            mov si, boot_msg
            call print_color_string

        .done:
            ret

        show_boot_notice:
            mov bl, [cfg_color_info]
            mov si, msg_boot_notice_line_1
            call print_color_string
            mov bl, COLOR_BANNER_5
            mov si, msg_boot_notice_line_2
            call print_color_string
            ret

        region_setup_interactive:
            mov bl, COLOR_WARN
            mov si, msg_pick_region_title
            call print_color_string
            mov bl, COLOR_INFO
            mov si, msg_region_opt_1
            call print_color_string
            mov si, msg_region_opt_2
            call print_color_string
            mov si, msg_region_opt_3
            call print_color_string
            mov si, msg_region_opt_4
            call print_color_string
            mov si, msg_region_opt_5
            call print_color_string
            mov si, msg_region_opt_6
            call print_color_string
            mov si, msg_region_opt_7
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, msg_pick_region_choice
            call print_color_string
            mov di, input_buffer
            mov word [input_limit], 1
            call read_line_limited
            mov al, [input_buffer]
            cmp al, '1'
            je .set_pacific
            cmp al, '2'
            je .set_eastern
            cmp al, '3'
            je .set_utc
            cmp al, '4'
            je .set_cet
            cmp al, '5'
            je .set_moscow
            cmp al, '6'
            je .set_sg
            cmp al, '7'
            je .set_tokyo
            jmp .set_utc

        .set_pacific:
            mov byte [timezone_offset], -8
            mov si, region_name_pacific
            jmp .store
        .set_eastern:
            mov byte [timezone_offset], -5
            mov si, region_name_eastern
            jmp .store
        .set_utc:
            mov byte [timezone_offset], 0
            mov si, region_name_utc
            jmp .store
        .set_cet:
            mov byte [timezone_offset], 1
            mov si, region_name_cet
            jmp .store
        .set_moscow:
            mov byte [timezone_offset], 3
            mov si, region_name_moscow
            jmp .store
        .set_sg:
            mov byte [timezone_offset], 8
            mov si, region_name_sg
            jmp .store
        .set_tokyo:
            mov byte [timezone_offset], 9
            mov si, region_name_tokyo

        .store:
            mov di, region_name
            mov cx, REGION_MAX
            call copy_string_limited
            mov byte [region_initialized], 1
            mov byte [setup_touched], 1
            mov bl, COLOR_INFO
            mov si, msg_region_set_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, region_name
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            ret

        password_setup_interactive:
            mov bl, COLOR_WARN
            mov si, msg_pick_pass
            call print_color_string
            mov di, password_plain
            mov word [input_limit], PASS_MAX
            call read_secret_limited
            cmp byte [password_plain], 0
            jne .set
            mov si, default_password
            mov di, password_plain
            mov cx, PASS_MAX
            call copy_string_limited
        .set:
            mov si, password_plain
            call encrypt_password_to_store
            mov byte [password_initialized], 1
            mov byte [setup_touched], 1
            mov bl, COLOR_INFO
            mov si, msg_pass_set
            call print_color_string
            ret

        show_region:
            mov bl, COLOR_ACCENT
            mov si, msg_region_current_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            cmp byte [region_initialized], 1
            je .region_named
            mov si, region_name_utc
            call print_color_string
            jmp .offset
        .region_named:
            mov si, region_name
            call print_color_string
        .offset:
            mov bl, COLOR_INFO
            mov si, msg_region_offset_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [timezone_offset]
            call print_utc_offset
            mov bl, COLOR_INFO
            mov si, msg_region_offset_suffix
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            ret

        show_prompt:
            mov bl, [cfg_color_prompt]
            cmp byte [username], 0
            jne .named
            mov si, default_user
            call print_color_string
            jmp .path

        .named:
            mov si, username
            call print_color_string

        .path:
            mov bl, [cfg_color_accent]
            mov al, ':'
            call putc_color
            mov al, '/'
            call putc_color
            cmp byte [current_dir], 0
            je .tail
            mov si, current_dir
            call print_color_string

        .tail:
            mov bl, [cfg_color_prompt]
            cmp byte [cfg_prompt_compact], 1
            jne .classic
            mov si, prompt_tail_compact
            call print_color_string
            ret

        .classic:
            mov si, prompt_tail
            call print_color_string
            ret

        fs_list:
            mov bl, COLOR_BANNER_2
            mov si, msg_fs_title
            call print_color_string
            mov bl, COLOR_FRAME
            mov si, msg_fs_legend
            call print_color_string
            mov bl, COLOR_INFO
            mov si, fs_entry_readme
            call print_color_string
            mov bl, COLOR_WARN
            mov si, fs_entry_judges
            call print_color_string
            mov bl, COLOR_PROMPT
            mov si, fs_entry_user
            call print_color_string
            mov bl, COLOR_ACCENT
            mov si, fs_entry_notes
            call print_color_string
            ; OATB_PATCH_FS_LIST
            call fs_list_user_files
            ret

        fs_info:
            mov bl, COLOR_BANNER_2
            mov si, msg_fsinfo_title
            call print_color_string
            mov bl, COLOR_INFO
            mov si, msg_fsinfo_line_1
            call print_color_string
            mov si, msg_fsinfo_line_2
            call print_color_string
            mov bl, COLOR_WARN
            mov si, msg_fsinfo_line_3
            call print_color_string
            ret

        fs_cat_by_name:
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .readme

            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .judges

            mov di, fs_name_user
            call strcmp
            cmp ax, 1
            je .user

            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .notes

            ; OATB_PATCH_FS_CAT
            call fs_user_find_by_name
            cmp ax, 1
            jne .not_found
            mov bl, COLOR_ACCENT
            mov si, di
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            mov ax, 1
            ret

        .not_found:
            xor ax, ax
            ret

        .readme:
            mov bl, COLOR_INFO
            mov si, fs_readme
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            mov ax, 1
            ret

        .judges:
            mov bl, COLOR_WARN
            mov si, fs_judges
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            mov ax, 1
            ret

        .user:
            mov bl, COLOR_BANNER_2
            mov si, msg_userfile_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            cmp byte [username], 0
            jne .show_saved_name
            mov si, default_user
            call print_color_string
            jmp .tail

        .show_saved_name:
            mov si, username
            call print_color_string

        .tail:
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            mov ax, 1
            ret

        .notes:
            mov bl, COLOR_ACCENT
            mov si, fs_notes
            call print_color_string
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            mov ax, 1
            ret

        fs_write_by_name:
            mov bx, si
            mov si, di
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .write_readme

            mov si, fs_token
            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .write_judges

            mov si, fs_token
            mov di, fs_name_user
            call strcmp
            cmp ax, 1
            je .write_user

            mov si, fs_token
            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .write_notes

            mov si, fs_token
            call fs_user_find_by_name
            cmp ax, 1
            je .write_custom
            mov si, fs_token
            call fs_user_create
            cmp ax, 1
            jne .write_no_slot

        .write_custom:
            mov si, bx
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov bl, COLOR_INFO
            mov si, msg_fswrite_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        .write_no_slot:
            mov ax, 2
            ret

        .write_readme:
            mov si, bx
            mov di, fs_readme
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov bl, COLOR_INFO
            mov si, msg_fswrite_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        .write_judges:
            mov si, bx
            mov di, fs_judges
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov bl, COLOR_WARN
            mov si, msg_fswrite_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        .write_user:
            mov si, bx
            mov di, username
            mov cx, USER_MAX
            call copy_string_limited
            mov byte [user_initialized], 1
            mov bl, COLOR_INFO
            mov si, msg_fswrite_user_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        .write_notes:
            mov si, bx
            mov di, fs_notes
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov bl, COLOR_ACCENT
            mov si, msg_fswrite_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        fs_append_by_name:
            mov bx, si
            mov si, di
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .append_readme

            mov si, fs_token
            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .append_judges

            mov si, fs_token
            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .append_notes

            mov si, fs_token
            call fs_user_find_by_name
            cmp ax, 1
            je .append_custom
            mov si, fs_token
            call fs_user_create
            cmp ax, 1
            jne .append_no_slot
        .append_custom:
            jmp .append_to_target

        .append_no_slot:
            mov ax, 2
            ret

        .append_readme:
            mov di, fs_readme
            jmp .append_to_target

        .append_judges:
            mov di, fs_judges
            jmp .append_to_target

        .append_notes:
            mov di, fs_notes

        .append_to_target:
            mov dx, di
            mov cx, FS_TEXT_MAX
        .seek_end:
            cmp cx, 0
            je .append_done
            cmp byte [di], 0
            je .append_space
            inc di
            dec cx
            jmp .seek_end

        .append_space:
            cmp di, dx
            je .append_copy

            cmp cx, 0
            je .append_done
            mov byte [di], ' '
            inc di
            dec cx
            je .append_done

        .append_copy:
            mov si, bx
            call copy_string_limited
        .append_done:
            mov bl, COLOR_INFO
            mov si, msg_append_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        fs_remove_by_name:
            mov si, di
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .rm_readme

            mov si, fs_token
            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .rm_judges

            mov si, fs_token
            mov di, fs_name_user
            call strcmp
            cmp ax, 1
            je .rm_user

            mov si, fs_token
            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .rm_notes

            mov si, fs_token
            call fs_user_remove_by_name
            cmp ax, 1
            je .rm_ok

            xor ax, ax
            ret

        .rm_readme:
            mov byte [fs_readme], 0
            jmp .rm_ok

        .rm_judges:
            mov byte [fs_judges], 0
            jmp .rm_ok

        .rm_user:
            mov byte [username], 0
            mov byte [user_initialized], 0
            jmp .rm_ok

        .rm_notes:
            mov byte [fs_notes], 0

        .rm_ok:
            mov bl, COLOR_WARN
            mov si, msg_rm_ok
            call print_color_string
            call fs_store_save
            mov ax, 1
            ret

        fs_list_user_files:
            mov si, ufs1_name
            call fs_list_user_entry
            mov si, ufs2_name
            call fs_list_user_entry
            mov si, ufs3_name
            call fs_list_user_entry
            mov si, ufs4_name
            call fs_list_user_entry
            mov si, ufs5_name
            call fs_list_user_entry
            mov si, ufs6_name
            call fs_list_user_entry
            ret

        fs_list_user_entry:
            cmp byte [si], 0
            je .done
            cmp byte [si], '/'
            jne .check_kind
            cmp byte [si + 1], 0
            je .done
        .check_kind:
            push si
            call fs_is_directory_marker
            cmp ax, 1
            pop si
            jne .entry_file
            mov bl, COLOR_BANNER_5
            push si
            mov si, msg_fs_dir_prefix
            call print_color_string
            pop si
            call print_dir_name_clean
            jmp .entry_tail
        .entry_file:
            mov bl, COLOR_PROMPT
            push si
            mov si, msg_fs_file_prefix
            call print_color_string
            pop si
            call print_color_string
        .entry_tail:
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
        .done:
            ret

        print_dir_name_clean:
        .loop:
            mov al, [si]
            cmp al, 0
            je .done
            cmp al, '/'
            jne .emit
            cmp byte [si + 1], 0
            je .done
        .emit:
            call putc_color
            inc si
            jmp .loop
        .done:
            ret

        fs_user_find_by_name:
            mov di, ufs1_name
            call strcmp
            cmp ax, 1
            je .slot1
            mov di, ufs2_name
            call strcmp
            cmp ax, 1
            je .slot2
            mov di, ufs3_name
            call strcmp
            cmp ax, 1
            je .slot3
            mov di, ufs4_name
            call strcmp
            cmp ax, 1
            je .slot4
            mov di, ufs5_name
            call strcmp
            cmp ax, 1
            je .slot5
            mov di, ufs6_name
            call strcmp
            cmp ax, 1
            je .slot6
            xor ax, ax
            ret
        .slot1:
            mov di, ufs1_data
            mov ax, 1
            ret
        .slot2:
            mov di, ufs2_data
            mov ax, 1
            ret
        .slot3:
            mov di, ufs3_data
            mov ax, 1
            ret
        .slot4:
            mov di, ufs4_data
            mov ax, 1
            ret
        .slot5:
            mov di, ufs5_data
            mov ax, 1
            ret
        .slot6:
            mov di, ufs6_data
            mov ax, 1
            ret

        fs_user_find_free_slot:
            cmp byte [ufs1_name], 0
            je .slot1
            cmp byte [ufs2_name], 0
            je .slot2
            cmp byte [ufs3_name], 0
            je .slot3
            cmp byte [ufs4_name], 0
            je .slot4
            cmp byte [ufs5_name], 0
            je .slot5
            cmp byte [ufs6_name], 0
            je .slot6
            xor ax, ax
            ret
        .slot1:
            mov bx, ufs1_name
            mov di, ufs1_data
            mov ax, 1
            ret
        .slot2:
            mov bx, ufs2_name
            mov di, ufs2_data
            mov ax, 1
            ret
        .slot3:
            mov bx, ufs3_name
            mov di, ufs3_data
            mov ax, 1
            ret
        .slot4:
            mov bx, ufs4_name
            mov di, ufs4_data
            mov ax, 1
            ret
        .slot5:
            mov bx, ufs5_name
            mov di, ufs5_data
            mov ax, 1
            ret
        .slot6:
            mov bx, ufs6_name
            mov di, ufs6_data
            mov ax, 1
            ret

        fs_user_create:
            call fs_user_find_by_name
            cmp ax, 1
            jne .create_new
            mov ax, 2
            ret
        .create_new:
            call fs_user_find_free_slot
            cmp ax, 1
            jne .full
            push di
            mov di, bx
            mov cx, FS_NAME_MAX
            call copy_string_limited
            pop di
            mov byte [di], 0
            mov ax, 1
            ret
        .full:
            xor ax, ax
            ret

        fs_user_remove_by_name:
            mov di, ufs1_name
            call strcmp
            cmp ax, 1
            je .slot1
            mov di, ufs2_name
            call strcmp
            cmp ax, 1
            je .slot2
            mov di, ufs3_name
            call strcmp
            cmp ax, 1
            je .slot3
            mov di, ufs4_name
            call strcmp
            cmp ax, 1
            je .slot4
            mov di, ufs5_name
            call strcmp
            cmp ax, 1
            je .slot5
            mov di, ufs6_name
            call strcmp
            cmp ax, 1
            je .slot6
            xor ax, ax
            ret
        .slot1:
            mov byte [ufs1_name], 0
            mov byte [ufs1_data], 0
            mov ax, 1
            ret
        .slot2:
            mov byte [ufs2_name], 0
            mov byte [ufs2_data], 0
            mov ax, 1
            ret
        .slot3:
            mov byte [ufs3_name], 0
            mov byte [ufs3_data], 0
            mov ax, 1
            ret
        .slot4:
            mov byte [ufs4_name], 0
            mov byte [ufs4_data], 0
            mov ax, 1
            ret
        .slot5:
            mov byte [ufs5_name], 0
            mov byte [ufs5_data], 0
            mov ax, 1
            ret
        .slot6:
            mov byte [ufs6_name], 0
            mov byte [ufs6_data], 0
            mov ax, 1
            ret

        fs_validate_dir_name:
            cmp byte [si], 0
            je .no
            cmp byte [si], '/'
            je .no
        .loop:
            mov al, [si]
            cmp al, 0
            je .yes
            cmp al, '/'
            je .no
            inc si
            jmp .loop
        .yes:
            mov ax, 1
            ret
        .no:
            xor ax, ax
            ret

        fs_validate_file_path:
            cmp byte [si], 0
            je .no
            cmp byte [si], '/'
            je .no
            xor dx, dx
        .loop:
            mov al, [si]
            cmp al, 0
            je .yes
            cmp al, '/'
            jne .next
            inc dl
            cmp dl, 1
            ja .no
            cmp byte [si + 1], 0
            je .no
        .next:
            inc si
            jmp .loop
        .yes:
            mov ax, 1
            ret
        .no:
            xor ax, ax
            ret

        fs_resolve_with_cwd:
            push bx
            push cx
            push di
            mov bx, si
            cmp byte [current_dir], 0
            je .copy_plain

            mov si, bx
        .scan_path:
            mov al, [si]
            cmp al, 0
            je .merge
            cmp al, '/'
            je .copy_plain
            inc si
            jmp .scan_path

        .merge:
            mov si, current_dir
            mov di, fs_token
            mov cx, FS_NAME_MAX - 1
            call copy_string_limited
            mov si, fs_token
            call string_length
            cmp ax, FS_NAME_MAX - 1
            jae .fail
            mov di, fs_token
            add di, ax
            mov byte [di], '/'
            inc di
            mov byte [di], 0
            mov cx, FS_NAME_MAX
            sub cx, ax
            sub cx, 2
            jb .fail
            mov si, bx
            call copy_string_limited
            mov si, fs_token
            mov ax, 1
            jmp .done

        .copy_plain:
            mov si, bx
            mov di, fs_token
            mov cx, FS_NAME_MAX
            call copy_string_limited
            mov si, fs_token
            mov ax, 1
            jmp .done

        .fail:
            xor ax, ax

        .done:
            pop di
            pop cx
            pop bx
            ret

        fs_validate_cat_path:
            push si
            call fs_validate_file_path
            cmp ax, 1
            jne .no
            pop si
            push si
            call fs_is_directory_marker
            cmp ax, 1
            je .no
            mov ax, 1
            pop si
            ret
        .no:
            pop si
            xor ax, ax
            ret

        fs_is_directory_marker:
            cmp byte [si], 0
            je .no
            cmp byte [si], '/'
            je .no
            xor dx, dx
        .loop:
            mov al, [si]
            cmp al, 0
            je .no
            cmp al, '/'
            jne .next
            inc dl
            cmp dl, 1
            jne .no
            cmp byte [si + 1], 0
            jne .no
            mov ax, 1
            ret
        .next:
            inc si
            jmp .loop
        .no:
            xor ax, ax
            ret

        fs_dir_build_marker:
            push si
            push di
            push cx
            mov di, dir_marker
            mov cx, FS_NAME_MAX - 1
            call copy_string_limited
            mov byte [di], '/'
            inc di
            mov byte [di], 0
            pop cx
            pop di
            pop si
            ret

        fs_dir_exists:
            push si
            call fs_validate_dir_name
            cmp ax, 1
            jne .no
            pop si
            call fs_dir_build_marker
            mov si, dir_marker
            call fs_user_find_by_name
            cmp ax, 1
            jne .no_ret
            mov ax, 1
            ret
        .no:
            pop si
        .no_ret:
            xor ax, ax
            ret

        fs_parent_ready_for_file:
            push bx
            push cx
            push di
            mov bx, si
        .scan:
            mov al, [si]
            cmp al, 0
            je .root_ok
            cmp al, '/'
            je .have_dir
            inc si
            jmp .scan
        .root_ok:
            mov ax, 1
            jmp .done
        .have_dir:
            mov si, bx
            mov di, dir_token
            mov cx, FS_NAME_MAX - 1
        .copy_dir:
            mov al, [si]
            cmp al, '/'
            je .copy_done
            cmp al, 0
            je .copy_fail
            mov [di], al
            inc di
            inc si
            dec cx
            jnz .copy_dir
            jmp .copy_fail
        .copy_done:
            mov byte [di], 0
            mov si, dir_token
            call fs_dir_exists
            jmp .done
        .copy_fail:
            xor ax, ax
        .done:
            pop di
            pop cx
            pop bx
            ret

        fs_dir_create:
            call fs_validate_dir_name
            cmp ax, 1
            jne .invalid
            call fs_dir_build_marker
            cmp byte [dir_marker], '/'
            jne .create_try
            cmp byte [dir_marker + 1], 0
            je .invalid
        .create_try:
            mov si, dir_marker
            call fs_user_create
            cmp ax, 1
            je .ok
            cmp ax, 2
            je .exists
            xor ax, ax
            ret
        .invalid:
            mov ax, 3
            ret
        .exists:
            mov ax, 2
            ret
        .ok:
            mov ax, 1
            ret

        fs_dir_remove:
            call fs_validate_dir_name
            cmp ax, 1
            jne .invalid
            call fs_dir_build_marker
            mov si, dir_marker
            call fs_user_find_by_name
            cmp ax, 1
            jne .not_found

            mov si, ufs1_name
            call .check_slot
            cmp ax, 1
            je .not_empty
            mov si, ufs2_name
            call .check_slot
            cmp ax, 1
            je .not_empty
            mov si, ufs3_name
            call .check_slot
            cmp ax, 1
            je .not_empty
            mov si, ufs4_name
            call .check_slot
            cmp ax, 1
            je .not_empty
            mov si, ufs5_name
            call .check_slot
            cmp ax, 1
            je .not_empty
            mov si, ufs6_name
            call .check_slot
            cmp ax, 1
            je .not_empty

            mov si, dir_marker
            call fs_user_remove_by_name
            cmp ax, 1
            jne .not_found
            mov ax, 1
            ret

        .check_slot:
            cmp byte [si], 0
            je .slot_ok
            push si
            mov di, dir_marker
            call strprefix
            cmp ax, 1
            jne .slot_not_prefix
            pop si
            push si
            mov di, dir_marker
            call strcmp
            cmp ax, 1
            jne .slot_not_empty
            pop si
            xor ax, ax
            ret
        .slot_not_prefix:
            pop si
        .slot_ok:
            xor ax, ax
            ret
        .slot_not_empty:
            pop si
            mov ax, 1
            ret

        .invalid:
            xor ax, ax
            ret
        .not_found:
            mov ax, 2
            ret
        .not_empty:
            mov ax, 3
            ret

        fs_copy_by_name:
            push bx
            mov bx, di
            mov di, fs_name_readme
            call strcmp
            cmp ax, 1
            je .copy_readme
            mov di, fs_name_judges
            call strcmp
            cmp ax, 1
            je .copy_judges
            mov di, fs_name_notes
            call strcmp
            cmp ax, 1
            je .copy_notes
            mov di, fs_name_user
            call strcmp
            cmp ax, 1
            je .copy_user
            call fs_user_find_by_name
            cmp ax, 1
            jne .not_found
            mov si, di
            jmp .copy
        .copy_readme:
            mov si, fs_readme
            jmp .copy
        .copy_judges:
            mov si, fs_judges
            jmp .copy
        .copy_notes:
            mov si, fs_notes
            jmp .copy
        .copy_user:
            mov si, username
        .copy:
            mov di, bx
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov ax, 1
            pop bx
            ret
        .not_found:
            xor ax, ax
            pop bx
            ret

        count_user_files:
            xor bx, bx
            mov si, ufs1_name
            call .count_slot
            mov si, ufs2_name
            call .count_slot
            mov si, ufs3_name
            call .count_slot
            mov si, ufs4_name
            call .count_slot
            mov si, ufs5_name
            call .count_slot
            mov si, ufs6_name
            call .count_slot
            mov ax, bx
            ret
        .count_slot:
            cmp byte [si], 0
            je .count_done
            push si
            call fs_is_directory_marker
            cmp ax, 1
            pop si
            je .count_done
            inc bx
        .count_done:
            ret

        count_user_dirs:
            xor bx, bx
            mov si, ufs1_name
            call .count_slot
            mov si, ufs2_name
            call .count_slot
            mov si, ufs3_name
            call .count_slot
            mov si, ufs4_name
            call .count_slot
            mov si, ufs5_name
            call .count_slot
            mov si, ufs6_name
            call .count_slot
            mov ax, bx
            ret
        .count_slot:
            cmp byte [si], 0
            je .count_done
            push si
            call fs_is_directory_marker
            cmp ax, 1
            pop si
            jne .count_done
            inc bx
        .count_done:
            ret

        show_help:
            mov bl, [cfg_color_accent]
            mov si, msg_help_title
            call print_color_string
            mov bl, [cfg_color_info]
            mov si, msg_help_core
            call print_color_string
            mov bl, [cfg_color_ascii]
            mov si, msg_help_utils
            call print_color_string
            mov bl, [cfg_color_frame]
            mov si, msg_help_info
            call print_color_string
            mov bl, [cfg_color_info]
            mov si, msg_help_fs
            call print_color_string
            mov bl, [cfg_color_info]
            mov si, msg_help_atbman
            call print_color_string
            mov bl, [patch_state_retro_color]
            mov si, msg_help_patch_retro
            call print_color_string
            mov bl, [patch_state_hints_color]
            mov si, msg_help_patch_alias
            call print_color_string
            mov bl, [patch_state_hack_color]
            mov si, msg_help_patch_hack
            call print_color_string
            mov bl, [patch_state_customize_color]
            mov si, msg_help_patch_customize
            call print_color_string
            mov bl, [cfg_color_warn]
            mov si, msg_help_tip
            call print_color_string
            ret

        show_about:
            mov bl, [cfg_color_ascii]
            mov si, about_top
            call print_color_string
            mov si, about_title
            call print_color_string
            mov si, about_sep
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, about_line_1
            call print_color_string
            mov bl, [cfg_color_frame]
            mov si, about_line_2
            call print_color_string
            mov bl, [cfg_color_ascii]
            mov si, about_line_3
            call print_color_string

            mov bl, [cfg_color_accent]
            mov si, about_user_prefix
            call print_color_string
            mov bl, [cfg_color_prompt]
            cmp byte [username], 0
            jne .name
            mov si, default_user
            call print_color_string
            jmp .user_tail

        .name:
            mov si, username
            call print_color_string

        .user_tail:
            mov bl, [cfg_color_ascii]
            mov si, about_user_suffix
            call print_color_string
            mov si, about_bottom
            call print_color_string
            ret

        show_patches:
            mov bl, [cfg_color_frame]
            mov si, msg_patches_title
            call print_color_string
            mov bl, [patch_state_retro_color]
            mov si, msg_patch_state_retro
            call print_color_string
            mov bl, [patch_state_hints_color]
            mov si, msg_patch_state_hints
            call print_color_string
            mov bl, [patch_state_hack_color]
            mov si, msg_patch_state_hack
            call print_color_string
            mov bl, [patch_state_customize_color]
            mov si, msg_patch_state_customize
            call print_color_string
            ret

        show_patches_raw:
            mov bl, [cfg_color_frame]
            mov si, msg_patches_raw_title
            call print_color_string

            mov bl, COLOR_INFO
            mov si, msg_patch_raw_retro
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [patch_state_retro_color]
            cmp al, COLOR_PROMPT
            jne .retro_off
            mov al, '1'
            jmp .retro_emit
        .retro_off:
            mov al, '0'
        .retro_emit:
            call putc_color
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string

            mov bl, COLOR_INFO
            mov si, msg_patch_raw_hints
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [patch_state_hints_color]
            cmp al, COLOR_PROMPT
            jne .hints_off
            mov al, '1'
            jmp .hints_emit
        .hints_off:
            mov al, '0'
        .hints_emit:
            call putc_color
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string

            mov bl, COLOR_INFO
            mov si, msg_patch_raw_hack
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [patch_state_hack_color]
            cmp al, COLOR_PROMPT
            jne .hack_off
            mov al, '1'
            jmp .hack_emit
        .hack_off:
            mov al, '0'
        .hack_emit:
            call putc_color
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string

            mov bl, COLOR_INFO
            mov si, msg_patch_raw_customize
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [patch_state_customize_color]
            cmp al, COLOR_PROMPT
            jne .customize_off
            mov al, '1'
            jmp .customize_emit
        .customize_off:
            mov al, '0'
        .customize_emit:
            call putc_color
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            ret

        show_uptime:
            mov bl, COLOR_ACCENT
            mov si, msg_uptime_prefix
            call print_color_string
            call get_elapsed_ticks
            mov bx, 1092
            div bx
            mov bl, COLOR_PROMPT
            call print_u16
            mov bl, COLOR_DEFAULT
            mov si, msg_uptime_suffix
            call print_color_string
            ret

        show_time:
            mov ah, 0x02
            int 0x1A
            jc .read_fail
            mov al, ch
            call bcd_to_bin8
            add al, [timezone_offset]
        .normalize_low:
            cmp al, 0
            jge .normalize_high
            add al, 24
            jmp .normalize_low
        .normalize_high:
            cmp al, 24
            jb .emit
            sub al, 24
            jmp .normalize_high
        .emit:
            mov [time_hour], al
            mov al, cl
            call bcd_to_bin8
            mov [time_min], al
            mov al, dh
            call bcd_to_bin8
            mov [time_sec], al
            mov bl, COLOR_ACCENT
            mov si, msg_time_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [time_hour]
            call print_two_digits
            mov al, ':'
            call putc_color
            mov al, [time_min]
            call print_two_digits
            mov al, ':'
            call putc_color
            mov al, [time_sec]
            call print_two_digits
            mov bl, COLOR_INFO
            mov si, msg_fetch_tz
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, [timezone_offset]
            call print_utc_offset
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            ret
        .read_fail:
            mov bl, COLOR_ERROR
            mov si, msg_rtc_fail
            call print_color_string
            ret

        show_date:
            mov ah, 0x04
            int 0x1A
            jc .read_fail
            mov bl, COLOR_ACCENT
            mov si, msg_date_prefix
            call print_color_string
            mov bl, COLOR_PROMPT
            mov al, dl
            call print_bcd_byte
            mov al, '.'
            call putc_color
            mov al, dh
            call print_bcd_byte
            mov al, '.'
            call putc_color
            mov al, ch
            call print_bcd_byte
            mov al, cl
            call print_bcd_byte
            mov bl, COLOR_DEFAULT
            mov si, msg_newline
            call print_color_string
            ret
        .read_fail:
            mov bl, COLOR_ERROR
            mov si, msg_rtc_fail
            call print_color_string
            ret

        show_version:
            mov bl, COLOR_BANNER_1
            mov si, msg_version
            call print_color_string
            ret

        show_fetch:
            mov bl, [cfg_color_frame]
            mov si, msg_fetch_head
            call print_color_string
            mov bl, [cfg_color_ascii]
            mov si, msg_fetch_logo_1
            call print_color_string
            mov si, msg_fetch_logo_2
            call print_color_string
            mov si, msg_fetch_logo_3
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_product
            call print_color_string
            mov bl, [cfg_color_info]
            mov si, msg_fetch_component_1
            call print_color_string
            mov bl, [cfg_color_warn]
            mov si, msg_fetch_component_2
            call print_color_string
            mov bl, [cfg_color_accent]
            mov si, msg_fetch_component_3
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_user
            call print_color_string
            mov bl, [cfg_color_prompt]
            cmp byte [username], 0
            jne .fetch_user_named
            mov si, default_user
            call print_color_string
            jmp .fetch_user_done
        .fetch_user_named:
            mov si, username
            call print_color_string
        .fetch_user_done:
            mov bl, [cfg_color_default]
            mov si, msg_newline
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_cwd
            call print_color_string
            mov bl, [cfg_color_prompt]
            cmp byte [current_dir], 0
            jne .fetch_cwd_named
            mov si, arg_root
            call print_color_string
            jmp .fetch_cwd_done
        .fetch_cwd_named:
            mov al, '/'
            call putc_color
            mov si, current_dir
            call print_color_string
        .fetch_cwd_done:
            mov bl, [cfg_color_default]
            mov si, msg_newline
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_region
            call print_color_string
            mov bl, [cfg_color_prompt]
            cmp byte [region_initialized], 1
            je .fetch_region_named
            mov si, region_name_utc
            call print_color_string
            jmp .fetch_region_offset
        .fetch_region_named:
            mov si, region_name
            call print_color_string
        .fetch_region_offset:
            mov bl, [cfg_color_info]
            mov si, msg_region_offset_prefix
            call print_color_string
            mov bl, [cfg_color_prompt]
            mov al, [timezone_offset]
            call print_utc_offset
            mov bl, [cfg_color_info]
            mov si, msg_region_offset_suffix
            call print_color_string
            mov bl, [cfg_color_default]
            mov si, msg_newline
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_uptime
            call print_color_string
            call get_elapsed_ticks
            mov bx, 1092
            div bx
            mov bl, [cfg_color_prompt]
            call print_u16
            mov bl, [cfg_color_info]
            mov si, msg_uptime_suffix
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_fs
            call print_color_string
            call count_user_dirs
            mov bl, [cfg_color_prompt]
            call print_u16
            mov bl, [cfg_color_info]
            mov si, msg_fetch_dirs_sep
            call print_color_string
            call count_user_files
            mov bl, [cfg_color_prompt]
            call print_u16
            mov bl, [cfg_color_info]
            mov si, msg_fetch_files_tail
            call print_color_string

            mov bl, [cfg_color_info]
            mov si, msg_fetch_auth
            call print_color_string
            mov bl, [cfg_color_prompt]
            cmp byte [password_initialized], 1
            je .fetch_auth_on
            mov si, msg_fetch_auth_off
            call print_color_string
            jmp .fetch_done
        .fetch_auth_on:
            mov si, msg_fetch_auth_on
            call print_color_string
        .fetch_done:
            mov bl, [cfg_color_default]
            mov si, msg_newline
            call print_color_string
            ret

        init_boot_ticks:
            call get_bios_ticks
            mov [boot_ticks], ax
            mov [boot_ticks + 2], dx
            ret

        init_openasm_fs:
            mov si, fs_readme_default
            mov di, fs_readme
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov si, fs_judges_default
            mov di, fs_judges
            mov cx, FS_TEXT_MAX
            call copy_string_limited
            mov byte [fs_notes], 0
            mov byte [ufs1_name], 0
            mov byte [ufs1_data], 0
            mov byte [ufs2_name], 0
            mov byte [ufs2_data], 0
            mov byte [ufs3_name], 0
            mov byte [ufs3_data], 0
            mov byte [ufs4_name], 0
            mov byte [ufs4_data], 0
            mov byte [ufs5_name], 0
            mov byte [ufs5_data], 0
            mov byte [ufs6_name], 0
            mov byte [ufs6_data], 0
            mov byte [region_initialized], 0
            mov byte [timezone_offset], 0
            mov si, region_name_utc
            mov di, region_name
            mov cx, REGION_MAX
            call copy_string_limited
            mov byte [password_initialized], 0
            mov byte [user_pass_enc], 0
            mov byte [current_dir], 0
            mov byte [setup_touched], 0
            mov byte [cscript_enabled], 0
            mov byte [atb_pkg1_name], 0
            mov byte [atb_pkg1_source], 0
            mov byte [atb_pkg1_runtime], 0
            mov byte [atb_pkg2_name], 0
            mov byte [atb_pkg2_source], 0
            mov byte [atb_pkg2_runtime], 0
            mov byte [atb_pkg3_name], 0
            mov byte [atb_pkg3_source], 0
            mov byte [atb_pkg3_runtime], 0
            mov byte [cfg_banner_enabled], 1
            mov byte [cfg_prompt_compact], 0
            mov byte [cfg_theme_index], 0
            mov byte [cfg_color_default], COLOR_DEFAULT
            mov byte [cfg_color_info], COLOR_INFO
            mov byte [cfg_color_warn], COLOR_WARN
            mov byte [cfg_color_error], COLOR_ERROR
            mov byte [cfg_color_prompt], COLOR_PROMPT
            mov byte [cfg_color_ascii], COLOR_ASCII
            mov byte [cfg_color_frame], COLOR_FRAME
            mov byte [cfg_color_accent], COLOR_ACCENT
            ret

        init_runtime_strings:
            mov si, msg_unknown_default
            mov di, msg_unknown
            mov cx, 63
            call copy_string_limited
            ret

        sanitize_runtime_state:
            cmp byte [msg_unknown], 0
            jne .check_default
            mov si, msg_unknown_default
            mov di, msg_unknown
            mov cx, 63
            call copy_string_limited

        .check_default:
            cmp byte [cfg_color_default], 0
            jne .check_info
            mov byte [cfg_color_default], COLOR_DEFAULT
        .check_info:
            cmp byte [cfg_color_info], 0
            jne .check_warn
            mov byte [cfg_color_info], COLOR_INFO
        .check_warn:
            cmp byte [cfg_color_warn], 0
            jne .check_error
            mov byte [cfg_color_warn], COLOR_WARN
        .check_error:
            cmp byte [cfg_color_error], 0
            jne .check_prompt
            mov byte [cfg_color_error], COLOR_ERROR
        .check_prompt:
            cmp byte [cfg_color_prompt], 0
            jne .check_ascii
            mov byte [cfg_color_prompt], COLOR_PROMPT
        .check_ascii:
            cmp byte [cfg_color_ascii], 0
            jne .check_frame
            mov byte [cfg_color_ascii], COLOR_ASCII
        .check_frame:
            cmp byte [cfg_color_frame], 0
            jne .check_accent
            mov byte [cfg_color_frame], COLOR_FRAME
        .check_accent:
            cmp byte [cfg_color_accent], 0
            jne .check_region
            mov byte [cfg_color_accent], COLOR_ACCENT
        .check_region:
            cmp byte [region_initialized], 1
            je .check_region_name
            mov byte [timezone_offset], 0
            mov si, region_name_utc
            mov di, region_name
            mov cx, REGION_MAX
            call copy_string_limited
            jmp .check_tz
        .check_region_name:
            cmp byte [region_name], 0
            jne .check_tz
            mov si, region_name_utc
            mov di, region_name
            mov cx, REGION_MAX
            call copy_string_limited
        .check_tz:
            mov al, [timezone_offset]
            cmp al, -12
            jl .reset_tz
            cmp al, 14
            jg .reset_tz
            jmp .check_password
        .reset_tz:
            mov byte [timezone_offset], 0
        .check_password:
            cmp byte [password_initialized], 1
            jne .check_cwd
            cmp byte [user_pass_enc], 0
            jne .check_cwd
            mov byte [password_initialized], 0
        .check_cwd:
            cmp byte [current_dir], 0
            je .done
            mov si, current_dir
            call fs_dir_exists
            cmp ax, 1
            je .done
            mov byte [current_dir], 0
        .done:
            ret

        fs_store_load:
            push ds
            push es

            mov ax, FS_STORE_SEG
            mov es, ax
            mov ax, FS_STORE_LBA
            mov bx, FS_STORE_BUFFER
            mov cx, FS_STORE_SECTORS
            call disk_read_lba_multi
            jc .init_store

            mov ax, FS_STORE_SEG
            mov ds, ax
            mov ax, cs
            mov es, ax

            mov si, FS_STORE_BUFFER
            mov di, fs_store_magic
            mov cx, 8
            call mem_equal_n
            cmp ax, 1
            jne .init_store

            mov si, FS_STORE_BUFFER + 8
            lodsb
            mov [user_initialized], al

            mov di, username
            mov cx, USER_MAX + 1
            call mem_copy_n

            mov di, msg_unknown
            mov cx, 64
            call mem_copy_n

            mov di, fs_readme
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov di, fs_judges
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov di, fs_notes
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov di, ufs1_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs1_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov di, ufs2_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs2_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov di, ufs3_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs3_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov di, ufs4_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs4_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov di, ufs5_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs5_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov di, ufs6_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov di, ufs6_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            lodsb
            mov [cfg_banner_enabled], al
            lodsb
            mov [cfg_prompt_compact], al
            lodsb
            mov [cfg_theme_index], al
            lodsb
            mov [cfg_color_default], al
            lodsb
            mov [cfg_color_info], al
            lodsb
            mov [cfg_color_warn], al
            lodsb
            mov [cfg_color_error], al
            lodsb
            mov [cfg_color_prompt], al
            lodsb
            mov [cfg_color_ascii], al
            lodsb
            mov [cfg_color_frame], al
            lodsb
            mov [cfg_color_accent], al

            lodsb
            mov [cscript_enabled], al

            mov di, atb_pkg1_name
            mov cx, 33
            call mem_copy_n
            mov di, atb_pkg1_source
            mov cx, 65
            call mem_copy_n
            mov di, atb_pkg1_runtime
            mov cx, 16
            call mem_copy_n

            mov di, atb_pkg2_name
            mov cx, 33
            call mem_copy_n
            mov di, atb_pkg2_source
            mov cx, 65
            call mem_copy_n
            mov di, atb_pkg2_runtime
            mov cx, 16
            call mem_copy_n

            mov di, atb_pkg3_name
            mov cx, 33
            call mem_copy_n
            mov di, atb_pkg3_source
            mov cx, 65
            call mem_copy_n
            mov di, atb_pkg3_runtime
            mov cx, 16
            call mem_copy_n

            lodsb
            mov [region_initialized], al
            lodsb
            mov [timezone_offset], al
            mov di, region_name
            mov cx, REGION_MAX + 1
            call mem_copy_n
            lodsb
            mov [password_initialized], al
            mov di, user_pass_enc
            mov cx, PASS_MAX * 2 + 1
            call mem_copy_n
            mov di, current_dir
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n

            mov byte [username + USER_MAX], 0
            mov byte [current_dir + FS_NAME_MAX], 0
            mov byte [msg_unknown + 63], 0
            mov byte [fs_readme + FS_TEXT_MAX], 0
            mov byte [fs_judges + FS_TEXT_MAX], 0
            mov byte [fs_notes + FS_TEXT_MAX], 0
            mov byte [atb_pkg1_name + 32], 0
            mov byte [atb_pkg2_name + 32], 0
            mov byte [atb_pkg3_name + 32], 0
            mov byte [atb_pkg1_source + 64], 0
            mov byte [atb_pkg2_source + 64], 0
            mov byte [atb_pkg3_source + 64], 0
            mov byte [atb_pkg1_runtime + 15], 0
            mov byte [atb_pkg2_runtime + 15], 0
            mov byte [atb_pkg3_runtime + 15], 0
            mov byte [region_name + REGION_MAX], 0
            mov byte [user_pass_enc + PASS_MAX * 2], 0
            mov byte [ufs1_name + FS_NAME_MAX], 0
            mov byte [ufs2_name + FS_NAME_MAX], 0
            mov byte [ufs3_name + FS_NAME_MAX], 0
            mov byte [ufs4_name + FS_NAME_MAX], 0
            mov byte [ufs5_name + FS_NAME_MAX], 0
            mov byte [ufs6_name + FS_NAME_MAX], 0
            mov byte [ufs1_data + FS_TEXT_MAX], 0
            mov byte [ufs2_data + FS_TEXT_MAX], 0
            mov byte [ufs3_data + FS_TEXT_MAX], 0
            mov byte [ufs4_data + FS_TEXT_MAX], 0
            mov byte [ufs5_data + FS_TEXT_MAX], 0
            mov byte [ufs6_data + FS_TEXT_MAX], 0
            jmp .restore_segments

        .init_store:
            mov ax, cs
            mov ds, ax
            mov es, ax
            call fs_store_save

        .restore_segments:
            pop es
            pop ds
            ret

        fs_store_save:
            push ds
            push es

            mov ax, cs
            mov ds, ax
            mov ax, FS_STORE_SEG
            mov es, ax

            mov di, FS_STORE_BUFFER
            mov si, fs_store_magic
            mov cx, 8
            call mem_copy_n

            mov al, [user_initialized]
            stosb

            mov si, username
            mov cx, USER_MAX + 1
            call mem_copy_n

            mov si, msg_unknown
            mov cx, 64
            call mem_copy_n

            mov si, fs_readme
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov si, fs_judges
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov si, fs_notes
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov si, ufs1_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs1_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov si, ufs2_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs2_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov si, ufs3_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs3_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov si, ufs4_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs4_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov si, ufs5_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs5_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n
            mov si, ufs6_name
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n
            mov si, ufs6_data
            mov cx, FS_TEXT_MAX + 1
            call mem_copy_n

            mov al, [cfg_banner_enabled]
            stosb
            mov al, [cfg_prompt_compact]
            stosb
            mov al, [cfg_theme_index]
            stosb
            mov al, [cfg_color_default]
            stosb
            mov al, [cfg_color_info]
            stosb
            mov al, [cfg_color_warn]
            stosb
            mov al, [cfg_color_error]
            stosb
            mov al, [cfg_color_prompt]
            stosb
            mov al, [cfg_color_ascii]
            stosb
            mov al, [cfg_color_frame]
            stosb
            mov al, [cfg_color_accent]
            stosb

            mov al, [cscript_enabled]
            stosb

            mov si, atb_pkg1_name
            mov cx, 33
            call mem_copy_n
            mov si, atb_pkg1_source
            mov cx, 65
            call mem_copy_n
            mov si, atb_pkg1_runtime
            mov cx, 16
            call mem_copy_n

            mov si, atb_pkg2_name
            mov cx, 33
            call mem_copy_n
            mov si, atb_pkg2_source
            mov cx, 65
            call mem_copy_n
            mov si, atb_pkg2_runtime
            mov cx, 16
            call mem_copy_n

            mov si, atb_pkg3_name
            mov cx, 33
            call mem_copy_n
            mov si, atb_pkg3_source
            mov cx, 65
            call mem_copy_n
            mov si, atb_pkg3_runtime
            mov cx, 16
            call mem_copy_n

            mov al, [region_initialized]
            stosb
            mov al, [timezone_offset]
            stosb
            mov si, region_name
            mov cx, REGION_MAX + 1
            call mem_copy_n
            mov al, [password_initialized]
            stosb
            mov si, user_pass_enc
            mov cx, PASS_MAX * 2 + 1
            call mem_copy_n
            mov si, current_dir
            mov cx, FS_NAME_MAX + 1
            call mem_copy_n

            mov ax, FS_STORE_LBA
            mov bx, FS_STORE_BUFFER
            mov cx, FS_STORE_SECTORS
            call disk_write_lba_multi

            pop es
            pop ds
            ret

        disk_read_lba_multi:
            push ax
            push bx
            push cx
            push dx
            push si
            push di
            mov si, ax
            mov di, bx
        .read_loop:
            cmp cx, 0
            je .read_ok
            mov ax, si
            mov bx, di
            call disk_read_lba
            jc .read_fail
            inc si
            add di, 512
            dec cx
            jmp .read_loop
        .read_ok:
            clc
            jmp .read_done
        .read_fail:
            stc
        .read_done:
            pop di
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        disk_write_lba_multi:
            push ax
            push bx
            push cx
            push dx
            push si
            push di
            mov si, ax
            mov di, bx
        .write_loop:
            cmp cx, 0
            je .write_ok
            mov ax, si
            mov bx, di
            call disk_write_lba
            jc .write_fail
            inc si
            add di, 512
            dec cx
            jmp .write_loop
        .write_ok:
            clc
            jmp .write_done
        .write_fail:
            stc
        .write_done:
            pop di
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        disk_read_lba:
            push ax
            push bx
            push cx
            push dx
            push si
            mov si, bx
            call lba_to_chs
            mov bx, si
            mov ah, 0x02
            mov al, 1
            mov dl, [boot_drive]
            int 0x13
            jc .read_one_fail
            clc
            jmp .read_one_done
        .read_one_fail:
            stc
        .read_one_done:
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        disk_write_lba:
            push ax
            push bx
            push cx
            push dx
            push si
            mov si, bx
            call lba_to_chs
            mov bx, si
            mov ah, 0x03
            mov al, 1
            mov dl, [boot_drive]
            int 0x13
            jc .write_one_fail
            clc
            jmp .write_one_done
        .write_one_fail:
            stc
        .write_one_done:
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        lba_to_chs:
            push ax
            push bx
            xor dx, dx
            mov bx, 36
            div bx
            mov ch, al
            mov ax, dx
            xor dx, dx
            mov bx, 18
            div bx
            mov dh, al
            mov cl, dl
            inc cl
            pop bx
            pop ax
            ret

        get_bios_ticks:
            mov ah, 0x00
            int 0x1A
            mov ax, dx
            mov dx, cx
            ret

        get_elapsed_ticks:
            call get_bios_ticks
            sub ax, [boot_ticks]
            sbb dx, [boot_ticks + 2]
            jnc .done
            add ax, 0x00B0
            adc dx, 0x0018
        .done:
            ret

        clear_screen:
            mov ax, 0x0003
            int 0x10
            ret

        exit_cmd:
            ; Fast-path for QEMU with isa-debug-exit device.
            mov dx, 0x0F4
            mov ax, 0x2000
            out dx, ax

            ; Fallback: try ACPI/APM power-off.
            mov ax, 0x5301
            xor bx, bx
            int 0x15
            mov ax, 0x530E
            mov bx, 0x0001
            mov cx, 0x0003
            int 0x15
            mov ax, 0x5307
            mov bx, 0x0001
            mov cx, 0x0003
            int 0x15

            cli
        .halt:
            hlt
            jmp .halt

        print_string:
            push bx
            mov bl, [cfg_color_default]
            call print_color_string
            pop bx
            ret

        print_color_string:
        .next_char:
            lodsb
            cmp al, 0
            je .done
            call putc_color
            jmp .next_char
        .done:
            ret

        print_upper_string:
        .next_char:
            lodsb
            cmp al, 0
            je .done
            cmp al, 'a'
            jb .emit
            cmp al, 'z'
            ja .emit
            sub al, 32
        .emit:
            call putc_color
            jmp .next_char
        .done:
            ret

        print_lower_string:
        .next_char:
            lodsb
            cmp al, 0
            je .done
            cmp al, 'A'
            jb .emit
            cmp al, 'Z'
            ja .emit
            add al, 32
        .emit:
            call putc_color
            jmp .next_char
        .done:
            ret

        print_u16:
            push ax
            push bx
            push cx
            push dx
            push si

            cmp ax, 0
            jne .convert
            mov al, '0'
            call putc_color
            jmp .done

        .convert:
            mov si, 10
            xor cx, cx
        .loop:
            xor dx, dx
            div si
            push dx
            inc cx
            cmp ax, 0
            jne .loop
        .print:
            pop dx
            mov al, dl
            add al, '0'
            call putc_color
            loop .print

        .done:
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        print_bcd_byte:
            push ax
            push bx

            mov ah, al
            shr al, 4
            and al, 0x0F
            add al, '0'
            call putc_color

            mov al, ah
            and al, 0x0F
            add al, '0'
            call putc_color

            pop bx
            pop ax
            ret

        bcd_to_bin8:
            push bx
            push cx
            mov ah, al
            and al, 0x0F
            mov bl, al
            mov al, ah
            shr al, 4
            and al, 0x0F
            mov cl, 10
            mul cl
            add al, bl
            pop cx
            pop bx
            ret

        print_two_digits:
            push ax
            push cx
            xor ah, ah
            mov cl, 10
            div cl
            add al, '0'
            call putc_color
            mov al, ah
            add al, '0'
            call putc_color
            pop cx
            pop ax
            ret

        print_utc_offset:
            push ax
            push dx
            mov dl, al
            cmp dl, 0
            jge .positive
            mov al, '-'
            call putc_color
            mov al, dl
            neg al
            jmp .emit_digits
        .positive:
            mov al, '+'
            call putc_color
            mov al, dl
        .emit_digits:
            call print_two_digits
            pop dx
            pop ax
            ret

        putc_color:
            push ax
            push bx
            push cx
            push dx

            cmp al, 13
            je .teletype
            cmp al, 10
            je .teletype
            cmp al, 8
            je .teletype

            mov ah, 0x09
            mov bh, 0x00
            mov cx, 1
            int 0x10

            mov ah, 0x03
            mov bh, 0x00
            int 0x10
            inc dl
            cmp dl, 80
            jb .set_cursor
            mov dl, 0
            inc dh
            cmp dh, 25
            jb .set_cursor
            call scroll_screen_up_one
            mov dh, 24

        .set_cursor:
            mov ah, 0x02
            mov bh, 0x00
            int 0x10
            jmp .done

        .teletype:
            mov ah, 0x0E
            mov bh, 0x00
            int 0x10

        .done:
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        scroll_screen_up_one:
            push ax
            push bx
            push cx
            push dx

            mov ax, 0x0601
            mov bh, [cfg_color_default]
            xor cx, cx
            mov dx, 0x184F
            int 0x10

            pop dx
            pop cx
            pop bx
            pop ax
            ret

        read_line:
            mov word [input_limit], MAX_INPUT

        read_line_limited:
            xor cx, cx
        .read_char:
            mov ah, 0x00
            int 0x16
            cmp al, 0
            je .read_char
            cmp al, 0xE0
            je .read_char
            cmp al, 13
            je .finish
            cmp al, 8
            je .backspace
            cmp cx, [input_limit]
            jae .read_char

            mov [di], al
            inc di
            inc cx
            mov bl, COLOR_DEFAULT
            call putc_color
            jmp .read_char

        .backspace:
            cmp cx, 0
            je .read_char
            dec di
            dec cx
            mov byte [di], 0
            call erase_char
            jmp .read_char

        .finish:
            mov byte [di], 0
            mov bl, COLOR_DEFAULT
            mov al, 13
            call putc_color
            mov al, 10
            call putc_color
            ret

        read_secret_limited:
            xor cx, cx
        .read_char:
            mov ah, 0x00
            int 0x16
            cmp al, 0
            je .read_char
            cmp al, 0xE0
            je .read_char
            cmp al, 13
            je .finish
            cmp al, 8
            je .backspace
            cmp cx, [input_limit]
            jae .read_char

            mov [di], al
            inc di
            inc cx
            mov bl, COLOR_DEFAULT
            mov al, '*'
            call putc_color
            jmp .read_char

        .backspace:
            cmp cx, 0
            je .read_char
            dec di
            dec cx
            mov byte [di], 0
            call erase_char
            jmp .read_char

        .finish:
            mov byte [di], 0
            mov bl, COLOR_DEFAULT
            mov al, 13
            call putc_color
            mov al, 10
            call putc_color
            ret

        erase_char:
            push ax
            push bx
            push cx
            push dx

            mov ah, 0x03
            mov bh, 0x00
            int 0x10

            cmp dl, 0
            jne .left
            cmp dh, 0
            je .done
            dec dh
            mov dl, 79
            jmp .set_cursor

        .left:
            dec dl

        .set_cursor:
            mov ah, 0x02
            mov bh, 0x00
            int 0x10

            mov ah, 0x09
            mov al, ' '
            mov bh, 0x00
            mov bl, COLOR_DEFAULT
            mov cx, 1
            int 0x10

            mov ah, 0x02
            mov bh, 0x00
            int 0x10

        .done:
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        strcmp:
            push si
            push di
            push bx
        .compare:
            mov al, [si]
            mov bl, [di]
            cmp al, bl
            jne .not_equal
            cmp al, 0
            je .equal
            inc si
            inc di
            jmp .compare
        .equal:
            mov ax, 1
            jmp .done
        .not_equal:
            xor ax, ax
        .done:
            pop bx
            pop di
            pop si
            ret

        skip_spaces:
        .loop:
            cmp byte [si], ' '
            jne .done
            inc si
            jmp .loop
        .done:
            ret

        strcmd:
            push si
            push di
            push bx
        .compare:
            mov al, [di]
            cmp al, 0
            je .boundary
            mov bl, [si]
            cmp al, bl
            jne .no
            inc si
            inc di
            jmp .compare
        .boundary:
            mov bl, [si]
            cmp bl, 0
            je .yes
            cmp bl, ' '
            je .yes
        .no:
            xor ax, ax
            jmp .done
        .yes:
            mov ax, 1
        .done:
            pop bx
            pop di
            pop si
            ret

        strprefix:
            push si
            push di
            push bx
        .loop:
            mov al, [di]
            cmp al, 0
            je .yes
            mov bl, [si]
            cmp bl, 0
            je .no
            cmp al, bl
            jne .no
            inc si
            inc di
            jmp .loop
        .yes:
            mov ax, 1
            jmp .done
        .no:
            xor ax, ax
        .done:
            pop bx
            pop di
            pop si
            ret

        copy_string:
        .copy:
            lodsb
            mov [di], al
            inc di
            cmp al, 0
            jne .copy
            ret

        copy_string_limited:
            cmp cx, 0
            jne .copy
            mov byte [di], 0
            ret
        .copy:
            lodsb
            cmp al, 0
            je .done
            mov [di], al
            inc di
            dec cx
            jnz .copy
            mov byte [di], 0
            ret
        .done:
            mov [di], al
            ret

        string_length:
            xor ax, ax
        .loop:
            cmp byte [si], 0
            je .done
            inc si
            inc ax
            jmp .loop
        .done:
            ret

        count_lines_in_text:
            xor bx, bx
            cmp byte [si], 0
            je .done
            mov bx, 1
        .loop:
            mov al, [si]
            cmp al, 0
            je .done
            cmp al, 13
            je .line_break
            cmp al, 10
            je .line_break_single
            inc si
            jmp .loop
        .line_break:
            inc si
            cmp byte [si], 10
            jne .line_count
            inc si
        .line_count:
            inc bx
            jmp .loop
        .line_break_single:
            inc si
            inc bx
            jmp .loop
        .done:
            mov ax, bx
            ret

        encrypt_password_to_store:
            push ax
            push bx
            push cx
            push dx
            push si
            push di

            mov di, password_work
            mov bx, pass_key
        .transform:
            lodsb
            cmp al, 0
            je .transform_done
            add al, 3
            xor al, [bx]
            mov [di], al
            inc di
            inc bx
            cmp byte [bx], 0
            jne .transform
            mov bx, pass_key
            jmp .transform
        .transform_done:
            mov byte [di], 0

            mov si, password_work
            call string_length
            mov cx, ax
            mov di, user_pass_enc
            cmp cx, 0
            je .encode_done

            mov bx, cx
        .encode_loop:
            dec bx
            js .encode_done
            mov si, password_work
            add si, bx
            mov al, [si]
            call encode_byte_hex
            jmp .encode_loop

        .encode_done:
            mov byte [di], 0
            pop di
            pop si
            pop dx
            pop cx
            pop bx
            pop ax
            ret

        encode_byte_hex:
            push ax
            mov ah, al
            shr al, 4
            call nibble_to_hex
            mov [di], al
            inc di
            mov al, ah
            and al, 0x0F
            call nibble_to_hex
            mov [di], al
            inc di
            pop ax
            ret

        nibble_to_hex:
            cmp al, 9
            jbe .digit
            add al, 'A' - 10
            ret
        .digit:
            add al, '0'
            ret

        append_line_limited:
            push bx
            push cx
            push dx
            push si
            push di

            mov bx, di
            mov cx, FS_TEXT_MAX
        .seek_end:
            cmp cx, 0
            je .fail
            cmp byte [di], 0
            je .at_end
            inc di
            dec cx
            jmp .seek_end

        .at_end:
            cmp di, bx
            je .copy_line
            cmp cx, 2
            jb .fail
            mov byte [di], 13
            inc di
            dec cx
            mov byte [di], 10
            inc di
            dec cx

        .copy_line:
            cmp cx, 1
            jb .fail
        .copy_next:
            lodsb
            cmp al, 0
            je .ok
            cmp cx, 1
            jbe .fail
            mov [di], al
            inc di
            dec cx
            jmp .copy_next

        .ok:
            mov byte [di], 0
            mov ax, 1
            jmp .done

        .fail:
            xor ax, ax

        .done:
            pop di
            pop si
            pop dx
            pop cx
            pop bx
            ret

        copy_token_limited:
            cmp cx, 0
            jne .copy
            mov byte [di], 0
            ret
        .copy:
            mov al, [si]
            cmp al, 0
            je .done
            cmp al, ' '
            je .done
            mov [di], al
            inc di
            inc si
            dec cx
            jnz .copy
        .skip_tail:
            mov al, [si]
            cmp al, 0
            je .done
            cmp al, ' '
            je .done
            inc si
            jmp .skip_tail
        .done:
            mov byte [di], 0
            ret

        mem_copy_n:
            rep movsb
            ret

        mem_equal_n:
            push si
            push di
            repe cmpsb
            jne .no
            mov ax, 1
            jmp .done
        .no:
            xor ax, ax
        .done:
            pop di
            pop si
            ret

        boot_msg db "OpenATB open-source utility by Roman Masovskiy.", 13, 10, 0

        cmd_help db "help", 0
        cmd_about db "about", 0
        cmd_clear db "clear", 0
        cmd_cls db "cls", 0
        cmd_banner db "banner", 0
        cmd_patches db "patches", 0
        cmd_sys db "sys", 0
        cmd_uptime db "uptime", 0
        cmd_time db "time", 0
        cmd_date db "date", 0
        cmd_version db "version", 0
        cmd_fetch db "fetch", 0
        cmd_exit db "exit", 0
        cmd_echo db "echo", 0
        cmd_setname db "setname", 0
        cmd_region db "region", 0
        cmd_passwd db "passwd", 0
        cmd_cd db "cd", 0
        cmd_reboot db "reboot", 0
        cmd_ls db "ls", 0
        cmd_fsls db "fsls", 0
        cmd_fsinfo db "fsinfo", 0
        cmd_fswrite db "fswrite", 0
        cmd_write db "write", 0
        cmd_append db "append", 0
        cmd_rm db "rm", 0
        cmd_touch db "touch", 0
        cmd_mk db "mk", 0
        cmd_mkdir db "mkdir", 0
        cmd_rmdir db "rmdir", 0
        cmd_cat db "cat", 0
        cmd_nano db "nano", 0
        cmd_nano_write db ":w", 0
        cmd_nano_save db ":wq", 0
        cmd_nano_quit db ":q", 0
        cmd_nano_help db ":h", 0

        arg_full db "full", 0
        arg_raw db "raw", 0
        arg_info db "info", 0
        arg_root db "/", 0
        arg_dotdot db "..", 0
        arg_set db "set", 0
        arg_reset db "reset", 0
        arg_dash_h db "-h", 0
        arg_dash_dash_help db "--help", 0

        msg_help_title db "[OpenATB open-source utility]", 13, 10, 0
        msg_help_core db " core : help about clear cls reboot exit", 13, 10, 0
        msg_help_utils db " tools: echo setname region passwd fetch banner", 13, 10, 0
        msg_help_info db " info : sys uptime time date version fetch patches", 13, 10, 0
        msg_help_fs db " fs   : ls cd touch mk mkdir rmdir nano write append rm cat fsinfo", 13, 10, 0
        msg_help_atbman db " atb  : atbman -e/-i/-u/-l", 13, 10, 0
        msg_help_patch_retro db " patch: retro-banner", 13, 10, 0
        msg_help_patch_alias db " patch: command-hints (?, whoami)", 13, 10, 0
        msg_help_patch_hack db " patch: hackathon-demo", 13, 10, 0
        msg_help_patch_customize db " patch: customize (c.atb + OpenACT)", 13, 10, 0
        msg_help_tip db " includes: 1) OATB DevKit 2) OpenASM-FS 3) OpenACT", 13, 10, 0
        msg_unknown_default db "Unknown cmd. Try help.", 0
        msg_unknown times 64 db 0
        msg_echo_usage db "Usage: echo [-n|-u|-l] <text>", 13, 10, 0
        msg_setname_usage db "Usage: setname [<name up to 32 chars>|reset]", 13, 10, 0
        msg_setname_ok_prefix db "Username updated: ", 0
        msg_setname_reset db "Username reset to guest.", 13, 10, 0
        msg_current_user_prefix db "Current user: ", 0
        msg_region_usage db "Usage: region [set]", 13, 10, 0
        msg_passwd_usage db "Usage: passwd", 13, 10, 0
        msg_cd_usage db "Usage: cd [folder|/|..]", 13, 10, 0
        msg_cd_now db "Current directory: ", 0
        msg_cd_not_found db "OpenASM-FS: directory not found.", 13, 10, 0
        msg_banner_usage db "Usage: banner [clear|full]", 13, 10, 0
        msg_patches_usage db "Usage: patches [raw]", 13, 10, 0
        msg_sys_usage db "Usage: sys <info|time|date|uptime|version|fetch|patches|banner>", 13, 10, 0
        msg_cat_usage db "Usage: cat <file>", 13, 10, 0
        msg_nano_usage db "Usage: nano <file>", 13, 10, 0
        msg_nano_title db "[nano] editing ", 0
        msg_nano_existing db "[nano] loaded. Saving rewrites this file.", 13, 10, 0
        msg_nano_new_file db "[nano] new file.", 13, 10, 0
        msg_nano_prompt_1 db "[nano] multiline mode.", 13, 10, 0
        msg_nano_prompt_2 db "[nano] :w save, :wq save+exit, :q quit", 13, 10, 0
        msg_nano_prompt_3 db "[nano] commands: :w, :wq, :q, :h", 13, 10, 0
        msg_nano_line_prompt db "nano> ", 0
        msg_nano_line_limit db "[nano] 1000 lines reached. Use :wq.", 13, 10, 0
        msg_nano_size_limit db "[nano] size limit reached. Use :wq.", 13, 10, 0
        msg_nano_cancel db "[nano] no changes saved.", 13, 10, 0
        msg_nano_written db "[nano] file saved.", 13, 10, 0
        msg_fswrite_usage db "Usage: fswrite <file> <text>", 13, 10, 0
        msg_append_usage db "Usage: append <file> <text>", 13, 10, 0
        msg_rm_usage db "Usage: rm <file>", 13, 10, 0
        msg_touch_usage db "Usage: touch|mk <file.ext>", 13, 10, 0
        msg_mkdir_usage db "Usage: mkdir <folder>", 13, 10, 0
        msg_rmdir_usage db "Usage: rmdir <folder>", 13, 10, 0
        msg_touch_ok_prefix db "OpenASM-FS: created file ", 0
        msg_touch_exists_prefix db "OpenASM-FS: already exists ", 0
        msg_mkdir_ok_prefix db "OpenASM-FS: folder created ", 0
        msg_mkdir_exists_prefix db "OpenASM-FS: folder exists ", 0
        msg_mkdir_invalid db "OpenASM-FS: invalid folder name.", 13, 10, 0
        msg_rmdir_ok_prefix db "OpenASM-FS: folder removed ", 0
        msg_rmdir_not_found_prefix db "OpenASM-FS: folder not found ", 0
        msg_rmdir_not_empty_prefix db "OpenASM-FS: folder is not empty ", 0
        msg_fs_full db "OpenASM-FS: user file table full (6 max).", 13, 10, 0
        msg_fswrite_ok db "OpenASM-FS: file updated.", 13, 10, 0
        msg_fswrite_user_ok db "OpenASM-FS: user profile updated.", 13, 10, 0
        msg_append_ok db "OpenASM-FS: text appended.", 13, 10, 0
        msg_rm_ok db "OpenASM-FS: file deleted permanently.", 13, 10, 0
        msg_rm_dir_hint db "Use rmdir <folder> for folders.", 13, 10, 0
        msg_file_not_found db "OpenASM-FS: file not found.", 13, 10, 0
        msg_path_invalid db "OpenASM-FS: invalid path.", 13, 10, 0
        msg_dir_missing db "OpenASM-FS: parent folder is missing.", 13, 10, 0
        msg_setup_top db "+-------------------------------------------------------+", 13, 10, 0
        msg_setup_title db "|         OpenATB Setup Wizard (graphical mode)        |", 13, 10, 0
        msg_setup_sep db "+-------------------------------------------------------+", 13, 10, 0
        msg_setup_line_1 db "| Configure profile, region and security for OpenATB.  |", 13, 10, 0
        msg_setup_line_2 db "| Use Enter to confirm each step.                      |", 13, 10, 0
        msg_setup_bottom db "+-------------------------------------------------------+", 13, 10, 0
        msg_setup_step_user db "[Step 1/3] User profile", 13, 10, 0
        msg_setup_step_region db "[Step 2/3] Region / time zone", 13, 10, 0
        msg_setup_step_pass db "[Step 3/3] Password", 13, 10, 0
        msg_setup_done db "[Setup complete] Entering OpenATB shell.", 13, 10, 0
        msg_pick_name db "First boot setup: choose username (max 32, empty = guest): ", 0
        msg_pick_region_title db "First boot setup: choose region:", 13, 10, 0
        msg_pick_region_choice db "Region [1-7]: ", 0
        msg_region_opt_1 db " 1) Pacific (UTC-08)", 13, 10, 0
        msg_region_opt_2 db " 2) Eastern (UTC-05)", 13, 10, 0
        msg_region_opt_3 db " 3) UTC (UTC+00)", 13, 10, 0
        msg_region_opt_4 db " 4) Central Europe (UTC+01)", 13, 10, 0
        msg_region_opt_5 db " 5) Moscow (UTC+03)", 13, 10, 0
        msg_region_opt_6 db " 6) Singapore (UTC+08)", 13, 10, 0
        msg_region_opt_7 db " 7) Tokyo (UTC+09)", 13, 10, 0
        msg_region_set_prefix db "Region set: ", 0
        msg_region_current_prefix db "Region: ", 0
        msg_region_offset_prefix db " (UTC", 0
        msg_region_offset_suffix db ")", 0
        msg_pick_pass db "First boot setup: set password (max 32): ", 0
        msg_pass_set db "Password saved (encrypted).", 13, 10, 0
        msg_hello_prefix db "Welcome, ", 0
        msg_hello_suffix db "! Your profile is now mounted in OpenASM-FS.", 13, 10, 0
        msg_boot_notice_line_1 db "[ OpenATB ] visual shell online: gradients, cards, colorized ls.", 13, 10, 0
        msg_boot_notice_line_2 db "[ OpenATB ] [DIR]=amber [FILE]=green [CORE]=cyan | DevKit fs+.", 13, 10, 13, 10, 0
        msg_userfile_prefix db "user.txt => ", 0
        msg_uptime_prefix db "Uptime: ", 0
        msg_uptime_suffix db " min", 13, 10, 0
        msg_time_prefix db "Time: ", 0
        msg_date_prefix db "Date: ", 0
        msg_version db "OpenATB runtime v0.3.0", 13, 10, 0
        msg_fetch_head db "[OpenATB fetch]", 13, 10, 0
        msg_fetch_logo_1 db "   O P E N A T B", 13, 10, 0
        msg_fetch_logo_2 db "   open-source utility card", 13, 10, 0
        msg_fetch_logo_3 db "   by Roman Masovskiy", 13, 10, 0
        msg_fetch_product db " utility: OpenATB (Open Assembly ToolBox)", 13, 10, 0
        msg_fetch_component_1 db " 1) OATB DevKit   - app/dev instructions", 13, 10, 0
        msg_fetch_component_2 db " 2) OpenASM-FS    - assembly filesystem", 13, 10, 0
        msg_fetch_component_3 db " 3) OpenACT (c.atb) - graphical customization", 13, 10, 0
        msg_fetch_user db " user   : ", 0
        msg_fetch_cwd db " cwd    : ", 0
        msg_fetch_region db " region : ", 0
        msg_fetch_uptime db " uptime : ", 0
        msg_fetch_fs db " fs     : dirs=", 0
        msg_fetch_dirs_sep db " files=", 0
        msg_fetch_files_tail db " (core=4)", 13, 10, 0
        msg_fetch_auth db " auth   : ", 0
        msg_fetch_auth_on db "configured", 0
        msg_fetch_auth_off db "not set", 0
        msg_fetch_tz db " UTC", 0
        msg_rtc_fail db "RTC is unavailable on this machine.", 13, 10, 0
        msg_patches_title db "[Patch status]", 13, 10, 0
        msg_patches_raw_title db "[Patch status raw: 1=enabled, 0=disabled]", 13, 10, 0
        msg_patch_raw_retro db " retro-banner   = ", 0
        msg_patch_raw_hints db " command-hints  = ", 0
        msg_patch_raw_hack db " hackathon-demo = ", 0
        msg_patch_raw_customize db " customize      = ", 0
        msg_patch_state_retro db " retro-banner   : green=on, red=off", 13, 10, 0
        msg_patch_state_hints db " command-hints  : green=on, red=off", 13, 10, 0
        msg_patch_state_hack db " hackathon-demo : green=on, red=off", 13, 10, 0
        msg_patch_state_customize db " customize      : green=on, red=off", 13, 10, 0
        msg_newline db 13, 10, 0
        prompt_tail db "@OATB> ", 0
        prompt_tail_compact db "# ", 0

        msg_fs_title db "OpenASM-FS mounted files:", 13, 10, 0
        msg_fs_legend db " legend: [CORE]=system files, [FILE]=user files, [DIR]=folders", 13, 10, 0
        msg_fsinfo_title db "[OpenASM-FS]", 13, 10, 0
        msg_fsinfo_line_1 db " core : readme.txt judges.txt user.txt notes.txt", 13, 10, 0
        msg_fsinfo_line_2 db " user : cd, touch/mk, mkdir/rmdir, nano, write, append, cat, rm", 13, 10, 0
        msg_fsinfo_line_3 db " path : folder/file.ext (one level folders)", 13, 10, 0
        fs_entry_readme db " [CORE] readme.txt", 13, 10, 0
        fs_entry_judges db " [CORE] judges.txt", 13, 10, 0
        fs_entry_user db " [CORE] user.txt", 13, 10, 0
        fs_entry_notes db " [CORE] notes.txt", 13, 10, 0
        msg_fs_file_prefix db " [FILE] ", 0
        msg_fs_dir_prefix db " [DIR ] ", 0

        fs_name_readme db "readme.txt", 0
        fs_name_judges db "judges.txt", 0
        fs_name_user db "user.txt", 0
        fs_name_notes db "notes.txt", 0
        region_name_pacific db "Pacific", 0
        region_name_eastern db "Eastern", 0
        region_name_utc db "UTC", 0
        region_name_cet db "Central Europe", 0
        region_name_moscow db "Moscow", 0
        region_name_sg db "Singapore", 0
        region_name_tokyo db "Tokyo", 0
        default_password db "openatb", 0
        pass_key db "OATB26", 0

        fs_readme_default db "OpenASM-FS: tiny in-memory FS with live editing.", 0
        fs_judges_default db "Roman note: tuned for real demos and practical tweaks.", 0
        fs_readme times FS_TEXT_MAX + 1 db 0
        fs_judges times FS_TEXT_MAX + 1 db 0
        fs_notes times FS_TEXT_MAX + 1 db 0
        ufs1_name times FS_NAME_MAX + 1 db 0
        ufs1_data times FS_TEXT_MAX + 1 db 0
        ufs2_name times FS_NAME_MAX + 1 db 0
        ufs2_data times FS_TEXT_MAX + 1 db 0
        ufs3_name times FS_NAME_MAX + 1 db 0
        ufs3_data times FS_TEXT_MAX + 1 db 0
        ufs4_name times FS_NAME_MAX + 1 db 0
        ufs4_data times FS_TEXT_MAX + 1 db 0
        ufs5_name times FS_NAME_MAX + 1 db 0
        ufs5_data times FS_TEXT_MAX + 1 db 0
        ufs6_name times FS_NAME_MAX + 1 db 0
        ufs6_data times FS_TEXT_MAX + 1 db 0

        banner_top db "+----------------------------------------------------------------+", 13, 10, 0
        art_line_1 db "|                                                                |", 13, 10, 0
        art_line_2 db "|    OOO   PPPP  EEEEE N   N   AAA  TTTTT BBBB                   |", 13, 10, 0
        art_line_3 db "|   O   O  P   P E     NN  N  A   A   T   B   B                  |", 13, 10, 0
        art_line_4 db "|   O   O  PPPP  EEEE  N N N  AAAAA   T   BBBB                   |", 13, 10, 0
        art_line_5 db "|   O   O  P     E     N  NN  A   A   T   B   B                  |", 13, 10, 0
        art_line_6 db "|    OOO   P     EEEEE N   N  A   A   T   BBBB                   |", 13, 10, 0
        banner_bottom db "+----------------------------------------------------------------+", 13, 10, 0
        fs_tagline db "            OpenASM-FS * by Roman Masovskiy", 13, 10, 13, 10, 0

        about_top db "+-------------------------------------------------------+", 13, 10, 0
        about_title db "|             OpenATB Open-Source Utility              |", 13, 10, 0
        about_sep db "+-------------------------------------------------------+", 13, 10, 0
        about_line_1 db "  1) OATB DevKit  : instruction set for OpenATB apps", 13, 10, 0
        about_line_2 db "  2) OpenASM-FS   : assembly filesystem for OpenATB", 13, 10, 0
        about_line_3 db "  3) OpenACT c.atb: graphical customization toolbox", 13, 10, 0
        about_user_prefix db "  User   : ", 0
        about_user_suffix db 13, 10, 0
        about_bottom db "+-------------------------------------------------------+", 13, 10, 0

        patch_state_retro_color db COLOR_ERROR
        patch_state_hints_color db COLOR_ERROR
        patch_state_hack_color db COLOR_ERROR
        patch_state_customize_color db COLOR_ERROR

        cfg_banner_enabled db 1
        cfg_prompt_compact db 0
        cfg_theme_index db 0
        cfg_color_default db COLOR_DEFAULT
        cfg_color_info db COLOR_INFO
        cfg_color_warn db COLOR_WARN
        cfg_color_error db COLOR_ERROR
        cfg_color_prompt db COLOR_PROMPT
        cfg_color_ascii db COLOR_ASCII
        cfg_color_frame db COLOR_FRAME
        cfg_color_accent db COLOR_ACCENT

        fs_store_magic db "OAFS1", 0, 0, 0
        boot_drive db 0
        boot_ticks dd 0
        time_hour db 0
        time_min db 0
        time_sec db 0
        input_limit dw MAX_INPUT
        nano_line_count dw 0
        fs_token times FS_NAME_MAX + 1 db 0
        dir_token times FS_NAME_MAX + 1 db 0
        dir_marker times FS_NAME_MAX + 1 db 0
        current_dir times FS_NAME_MAX + 1 db 0
        nano_buffer times FS_TEXT_MAX + 1 db 0
        default_user db "guest", 0
        region_initialized db 0
        timezone_offset db 0
        region_name times REGION_MAX + 1 db 0
        password_initialized db 0
        user_pass_enc times PASS_MAX * 2 + 1 db 0
        password_plain times PASS_MAX + 1 db 0
        password_work times PASS_MAX + 1 db 0
        setup_touched db 0
        user_initialized db 0
        username times USER_MAX + 1 db 0
        ; OATB_PATCH_KERNEL_DATA

        input_buffer times MAX_INPUT + 1 db 0
        """
    )


def command_template(command_name: str, description: str) -> str:
    label = safe_identifier(command_name)
    return _block(
        f"""
        ; Command: {command_name}
        ; Description: {description}
        ; Hook this handler from your kernel dispatch logic.

        {label}_cmd:
            mov si, {label}_msg
            call print_string
            ret

        {label}_msg db "[{command_name}] stub command. Put your logic here.", 13, 10, 0
        """
    )


def patch_note_template() -> str:
    return _block(
        """
        # Patch Name

        ## Goal
        Describe the behavior change.

        ## File Changes
        - `src/...`: what you changed and why

        ## Validation
        1. Build image.
        2. Boot and run the related command.
        3. Confirm no regressions in `help`, `about`, `clear`, `reboot`.
        """
    )


def project_readme_template(project_name: str) -> str:
    return _block(
        f"""
        # {project_name}

        Generated with {TOOL_NAME}.

        OpenATB is an open-source utility that includes:
        - Open Assembly ToolBox Developer Kit (OATB DevKit)
        - Open Assembly FileSystem (OpenASM-FS)
        - Open Assembly Customization ToolBox (OpenACT via `c.atb`)

        This repository is a bootable assembly project scaffold:
        - `src/boot/boot.asm`: boot sector loader
        - `src/kernel/kernel.asm`: vivid multi-color shell with first-boot setup wizard
        - `src/commands/`: command templates and map
        - `scripts/build.py`: cross-platform build pipeline
        - `scripts/run.py`: cross-platform runner for QEMU (keeps persisted state by default)
        - `scripts/flash.py`: USB flashing helper
        - `scripts/build.sh`, `scripts/run.sh`, `scripts/flash.sh`: shell wrappers

        Built-in shell tools:
        - OpenASM-FS is sector-backed and persists inside the floppy image
        - `exit`: close QEMU / power off VM
        - `echo [-n|-u|-l] <text>`: print text, no-newline, upper/lower transforms
        - `setname [name|reset]`: update active profile name (max 32) or reset to guest
        - `region [set]`: show or reconfigure region/timezone
        - `passwd`: update encrypted password
        - `sys <info|time|date|uptime|version|patches|banner>`: multi-tool command
        - `time`: show RTC time
        - `date`: show RTC date
        - `version`: print runtime version
        - `uptime`: show session uptime in minutes
        - `fetch`: visual runtime card (fastfetch-like)
        - `patches [raw]`: show patch status (red before apply, green after apply)
        - `banner [clear|full]`: redraw or control banner screen
        - `cls`: alias for `clear`
        - `ls`: list files in OpenASM-FS
        - `cd [folder|/|..]`: switch working folder
        - `fsinfo`: show OpenASM-FS layout and editing hints
        - `touch/mk <file.ext>`: create custom file with any extension
        - `nano <file>`: inline multi-line editor (`:wq` save, `:q` cancel, up to 1000 lines and large file size)
        - `write/fswrite <file> <text>`: overwrite file text
        - `append <file> <text>`: append text
        - `rm <file>`: permanently delete file content
        - `cat <file>`: read file from OpenASM-FS
        - `atbman -e|-i|-u|-l`: `.atb` manager (run local files or installed packages)
          - DevKit runtime supports: `var :: name :: int|str => input()`, `output() => ...`, `output(expr)`, `if ...` + `else => ...`, `oatb.system.output => ...`, `oatb.system.clear`, `oatb.menu.title/item/input => ...`, `oatb.system.run("cmd")`, `oatb.fs.write => "file :: text"`, `oatb.fs.append => "file :: text"`, `oatb.fs.read => "file"`, `oatb.fs.copy|move => "src :: dst"`; chain statements with `;`
        - after `customize` patch: `c.atb` + `customization.yaml` appear, OpenACT is unlocked, and `cp`/`mv` are available in shell

        ## Requirements
        - `nasm`
        - `qemu-system-i386` (for running the image)
        - Optional host apps: `python`, `neofetch`, `screenfetch`

        ## Host App Installer (from toolbox root)
        ```bash
        python3 main.py app list
        python3 main.py app managers
        python3 main.py app install nasm --yes
        python3 main.py app install qemu --yes
        python3 main.py app install neofetch --yes
        ```

        ## Build
        ```bash
        python3 ./scripts/build.py
        ```

        ## Run
        ```bash
        # uses existing build/openatb.img (persistent data kept)
        python3 ./scripts/run.py

        # optional explicit rebuild before run
        python3 ./scripts/run.py --rebuild
        ```

        ## Flash To USB (Destructive)
        ```bash
        # Linux (run as root)
        sudo python3 ./scripts/flash.py --device /dev/sdX --yes

        # macOS
        python3 ./scripts/flash.py --device /dev/diskN --yes
        ```

        On first boot, setup wizard asks username, region and password.
        Banner is configured in `src/kernel/kernel.asm` (`art_line_1` ... `art_line_6`) and can be edited.
        OpenASM-FS labels, banner and about card keep the Roman Masovskiy credit line.
        Hackathon mode is optional and enabled only via `hackathon` command.

        ## Tooling examples
        Run these from the OpenATB toolbox repository root:
        ```bash
        python3 main.py new-command /path/to/your/project clock --description "Print custom clock text"
        python3 main.py app list
        python3 main.py app managers
        python3 main.py app install neofetch
        python3 main.py app install python --yes
        python3 main.py patch list
        python3 main.py patch apply /path/to/your/project retro-banner
        python3 main.py patch apply /path/to/your/project customize
        python3 main.py new-template asm-command ./tmp/demo_cmd.asm --name demo
        python3 main.py hackathon-pack /path/to/your/project
        # in shell after boot:
        # hackathon
        # demo
        ```
        """
    )


def build_script_template() -> str:
    return _block(
        """
        #!/usr/bin/env bash
        set -euo pipefail

        ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        python3 "$ROOT/scripts/build.py"
        """
    )


def run_script_template() -> str:
    return _block(
        """
        #!/usr/bin/env bash
        set -euo pipefail

        ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        python3 "$ROOT/scripts/run.py"
        """
    )


def flash_script_template() -> str:
    return _block(
        """
        #!/usr/bin/env bash
        set -euo pipefail

        ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        python3 "$ROOT/scripts/flash.py" "$@"
        """
    )


def build_python_template() -> str:
    return _block(
        f"""
        #!/usr/bin/env python3
        from __future__ import annotations

        import shutil
        import subprocess
        import sys
        from pathlib import Path

        KERNEL_SECTORS = {KERNEL_SECTORS}
        IMAGE_SECTORS = 2880
        SECTOR_SIZE = 512


        def resolve_executable(candidates: list[str]) -> str:
            for candidate in candidates:
                path = shutil.which(candidate)
                if path:
                    return path
            raise SystemExit(f"Missing executable. Tried: {{', '.join(candidates)}}")


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
                    f"Kernel is {{kernel_size}} bytes, max is {{max_size}} bytes. "
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
            print(f"Image ready: {{image_path}}")
            return 0


        if __name__ == "__main__":
            sys.exit(main())
        """
    )


def run_python_template() -> str:
    return _block(
        """
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
        """
    )


def flash_python_template() -> str:
    return _block(
        """
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
        """
    )


def makefile_template() -> str:
    return _block(
        """
        .PHONY: build run flash build-py run-py flash-py

        build:
        	./scripts/build.sh

        run:
        	./scripts/run.sh

        flash:
        	./scripts/flash.sh

        build-py:
        	python3 ./scripts/build.py

        run-py:
        	python3 ./scripts/run.py

        flash-py:
        	python3 ./scripts/flash.py
        """
    )


def sentinel_template(project_name: str) -> str:
    return _block(
        f"""
        name = "{project_name}"
        generator = "{TOOL_NAME}"
        version = "{TOOL_VERSION}"
        """
    )


def commands_map_template() -> str:
    return _block(
        """
        # command | description | source
        help | built-in | src/kernel/kernel.asm
        about | built-in | src/kernel/kernel.asm
        clear | clear screen + redraw banner | src/kernel/kernel.asm
        cls | alias for clear | src/kernel/kernel.asm
        banner | redraw banner / banner clear / banner full | src/kernel/kernel.asm
        sys | sys <info|time|date|uptime|version|patches|banner> | src/kernel/kernel.asm
        uptime | show session uptime in minutes | src/kernel/kernel.asm
        time | show RTC time | src/kernel/kernel.asm
        date | show RTC date | src/kernel/kernel.asm
        version | show runtime version | src/kernel/kernel.asm
        patches | show patch status / patches raw | src/kernel/kernel.asm
        exit | close VM / power off | src/kernel/kernel.asm
        echo | echo [-n|-u|-l] <text> | src/kernel/kernel.asm
        setname | setname [name|reset] (max 32) | src/kernel/kernel.asm
        region | region [set] | src/kernel/kernel.asm
        passwd | set encrypted password | src/kernel/kernel.asm
        fetch | utility runtime card | src/kernel/kernel.asm
        reboot | built-in | src/kernel/kernel.asm
        ls | list files in OpenASM-FS | src/kernel/kernel.asm
        fsls | list files in OpenASM-FS | src/kernel/kernel.asm
        cd | cd [folder|/|..] | src/kernel/kernel.asm
        fsinfo | show OpenASM-FS info | src/kernel/kernel.asm
        fswrite | fswrite <file> <text> | src/kernel/kernel.asm
        write | alias for fswrite | src/kernel/kernel.asm
        touch | create user file (any extension) | src/kernel/kernel.asm
        mk | alias for touch | src/kernel/kernel.asm
        nano | inline file editor | src/kernel/kernel.asm
        append | append <file> <text> | src/kernel/kernel.asm
        rm | remove/reset file | src/kernel/kernel.asm
        cat | print file from OpenASM-FS | src/kernel/kernel.asm
        """
    )


def hackathon_pitch_template(team: str, project_name: str) -> str:
    return _block(
        f"""
        # {project_name} - Hackathon Pitch

        Team: {team}

        ## What We Built
        - A bootable real-mode shell written in assembly.
        - Commands and patches that can be added fast during a live demo.

        ## Why We Built It
        - We wanted a tiny OS sandbox that is understandable end-to-end.
        - It is fast to setup, easy to demo, and fun to extend.

        ## Live Demo Plan (3-4 min)
        1. Boot image in QEMU.
        2. Run built-in commands: `help`, `about`, `fsls`.
        3. Enable hackathon mode with `hackathon`, then run `demo`.
        4. Add one custom command from template.
        5. Apply one patch live and reboot.

        ## Why This Matters
        - The full flow is reproducible on a clean laptop.
        - Every change is visible in code and on screen.
        """
    )


def hackathon_demo_script_template() -> str:
    return _block(
        """
        # Demo Script

        1. Explain goal in one sentence: tiny hackable real-mode shell.
        2. Build image (`python3 ./scripts/build.py`) and boot in QEMU (`python3 ./scripts/run.py`).
        3. Run `help` and `about`.
        4. Type `hackathon`, then run `demo`.
        5. Apply one patch and reboot.
        6. End with one concrete next step for the project.
        """
    )


def hackathon_checklist_template() -> str:
    return _block(
        """
        # Judge Checklist

        - [ ] Boots on a clean machine.
        - [ ] Basic commands respond without crash.
        - [ ] One custom command is shown.
        - [ ] One patch is applied live.
        - [ ] Team explains architecture in under 60 seconds.
        """
    )


def customization_yaml_template() -> str:
    return _block(
        """
        version: 1
        profile: "default"
        banner:
          enabled: true
          mode: "full"   # full | clear
        prompt:
          compact: false
          tail_classic: "@OATB> "
          tail_compact: "# "
        theme:
          name: "classic" # classic | ice | amber
          colors:
            default: "0x07"
            info: "0x0B"
            warn: "0x0E"
            error: "0x0C"
            prompt: "0x0A"
            ascii: "0x0D"
            frame: "0x09"
            accent: "0x03"
        menu:
          title: "OpenACT - Open Assembly Customization ToolBox"
          keys:
            toggle_banner: "1"
            cycle_theme: "2"
            toggle_prompt: "3"
            edit_username: "4"
            edit_readme: "5"
            edit_judges: "6"
            edit_unknown_message: "7"
            reset_profile: "R"
            save_exit: "S"
        shell:
          unknown_message: "Unknown command. Type help."
          compact_prompt_default: false
        filesystem:
          backend: "sector-backed"
          label: "OpenASM-FS"
          persistent: true
          files:
            - "readme.txt"
            - "judges.txt"
            - "user.txt"
            - "notes.txt"
        command_map:
          lock_credits: true
          preserve_core:
            - "help"
            - "about"
            - "atbman"
            - "ls"
            - "cat"
            - "write"
        runtimes:
          supported:
            - "atbdevkit"
            - "python"
            - "c"
        atbman:
          package_manager: "atbman"
          core_script: "c.atb"
          core_source: "core://openatb"
          examples:
            exec: "atbman -e c.atb"
            install: "atbman -i cooltheme.atb https://github.com/user/openatb-cooltheme atbdevkit"
            uninstall: "atbman -u cooltheme.atb"
            list: "atbman -l"
        """
    )


def customization_script_template() -> str:
    return _block(
        """
        <OATB DevKit app :: c.atb>
        <Run in OpenATB shell :: atbman -e c.atb>
        <Goal :: full OpenACT customization profile>

        app :: openact.customizer
        meta :: version :: 2.0.0
        meta :: author :: Roman Masovskiy
        meta :: mode :: "full-customize"

        func output() => oatb.system.output
        func input() => oatb.system.input

        var boot_text :: str => "OpenACT boot" <main startup text>
        var profile_name :: str => "roman-max"
        var readme_text :: str => "OpenASM-FS tuned by Roman Masovskiy"
        var judges_text :: str => "credits fixed to Roman Masovskiy"
        var unknown_text :: str => "Unknown command. Type help."
        var theme_name :: str => "amber"
        var prompt_mode :: str => "compact"
        var banner_mode :: str => "on"
        var user_choice :: str => "0"

        output() => boot_text
        oatb.profile.load => profile_name
        oatb.ui.mode => "fullscreen"
        oatb.ui.layout => "openact.grid"
        oatb.theme.set => theme_name
        oatb.prompt.mode => prompt_mode
        oatb.banner.mode => banner_mode
        oatb.menu.hotkeys => "1,2,3,4,5,6,7,R,S"
        oatb.menu.title => "OpenACT - Open Assembly Customization ToolBox"
        oatb.menu.lock.about_credit => "Roman Masovskiy" <always locked>

        oatb.system.set => "cfg.banner.enabled :: 1"
        oatb.system.set => "cfg.prompt.compact :: 1"
        oatb.system.set => "cfg.theme.index :: 2"
        oatb.system.set => "cfg.colors.default :: 0x07"
        oatb.system.set => "cfg.colors.info :: 0x0E"
        oatb.system.set => "cfg.colors.warn :: 0x06"
        oatb.system.set => "cfg.colors.error :: 0x0C"
        oatb.system.set => "cfg.colors.prompt :: 0x0E"
        oatb.system.set => "cfg.colors.ascii :: 0x06"
        oatb.system.set => "cfg.colors.frame :: 0x06"
        oatb.system.set => "cfg.colors.accent :: 0x0C"

        oatb.fs.write => "user.txt :: profile=roman-max"
        oatb.fs.write => "readme.txt :: OpenASM-FS tuned by Roman Masovskiy" <fs write>
        oatb.fs.write => "judges.txt :: credits fixed to Roman Masovskiy" <credits lock>
        oatb.fs.write => "notes.txt :: OpenACT full customization preset loaded"
        oatb.system.set => "shell.unknown :: Unknown command. Type help."
        oatb.system.set => "shell.unknown.user :: dynamic"

        oatb.commands.bind => "help :: preserved"
        oatb.commands.bind => "about :: preserved"
        oatb.commands.bind => "atbman :: std"
        oatb.commands.bind => "ls :: openasm-fs"
        oatb.commands.bind => "cat :: openasm-fs"
        oatb.commands.bind => "write :: openasm-fs"

        oatb.apps.runtime.add => "atbdevkit"
        oatb.apps.runtime.add => "python"
        oatb.apps.runtime.add => "c"
        oatb.apps.registry.sync => "atbman"

        oatb.system.clear
        oatb.menu.title => "OpenACT quick menu"
        oatb.menu.item => "1) Python bridge check"
        oatb.menu.item => "2) C bridge check"
        oatb.menu.item => "3) Continue startup"
        oatb.menu.input => user_choice
        if user_choice == 1 => oatb.system.run("python3 tools/theme_sync.py")
        else => output() => "No host runtime command selected"

        output() => "OpenACT profile applied"
        oatb.ui.open => "openact"
        """
    )


PATCHES: dict[str, PatchDefinition] = {
    "retro-banner": PatchDefinition(
        description="Adds boot-time loading animation and status line.",
        actions=(
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_BOOT",
                snippet="    mov byte [patch_state_retro_color], COLOR_PROMPT",
            ),
            PatchAction(
                file="src/boot/boot.asm",
                marker="; OATB_PATCH_BOOT_CODE",
                snippet=(
                    "    mov si, patch_retro_line\n"
                    "    call print_string\n"
                    "    mov cx, 6\n"
                    "patch_retro_dot_loop:\n"
                    "    mov ah, 0x0E\n"
                    "    mov al, '.'\n"
                    "    int 0x10\n"
                    "    mov bx, 0x3FFF\n"
                    "patch_retro_delay_loop:\n"
                    "    dec bx\n"
                    "    jnz patch_retro_delay_loop\n"
                    "    loop patch_retro_dot_loop\n"
                    "    mov si, patch_retro_done\n"
                    "    call print_string"
                ),
            ),
            PatchAction(
                file="src/boot/boot.asm",
                marker="; OATB_PATCH_BOOT_DATA",
                snippet=(
                    'patch_retro_line db "Loading modules", 0\n'
                    'patch_retro_done db " ok", 13, 10, 0'
                ),
            ),
        ),
    ),
    "command-hints": PatchDefinition(
        description="Adds functional aliases: '?' (help) and 'whoami' (active profile).",
        actions=(
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_BOOT",
                snippet="    mov byte [patch_state_hints_color], COLOR_PROMPT",
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_COMMANDS",
                snippet=(
                    "    mov di, cmd_qmark\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_hints_after_qmark\n"
                    "    call show_help\n"
                    "    ret\n"
                    ".patch_hints_after_qmark:\n"
                    "    mov di, cmd_whoami\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_hints_after_whoami\n"
                    "    mov bl, COLOR_ACCENT\n"
                    "    mov si, msg_whoami_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, COLOR_PROMPT\n"
                    "    cmp byte [username], 0\n"
                    "    jne .patch_hints_show_name\n"
                    "    mov si, default_user\n"
                    "    call print_color_string\n"
                    "    jmp .patch_hints_user_tail\n"
                    ".patch_hints_show_name:\n"
                    "    mov si, username\n"
                    "    call print_color_string\n"
                    ".patch_hints_user_tail:\n"
                    "    mov bl, COLOR_DEFAULT\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_hints_after_whoami:"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_DATA",
                snippet=(
                    'cmd_qmark db "?", 0\n'
                    'cmd_whoami db "whoami", 0\n'
                    'msg_whoami_prefix db "Current user: ", 0'
                ),
            ),
            PatchAction(
                file="src/commands/commands.map",
                marker="# command | description | source",
                snippet=(
                    "? | alias for help | src/kernel/kernel.asm\n"
                    "whoami | print active user name | src/kernel/kernel.asm"
                ),
            ),
        ),
    ),
    "hackathon-demo": PatchDefinition(
        description="Adds command-driven hackathon mode and gated demo command.",
        actions=(
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_BOOT",
                snippet="    mov byte [patch_state_hack_color], COLOR_PROMPT",
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_COMMANDS",
                snippet=(
                    "    mov di, cmd_hackathon\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_hackathon_check_demo\n"
                    "    cmp byte [hackathon_mode], 1\n"
                    "    jne .patch_hackathon_enable\n"
                    "    mov byte [hackathon_mode], 0\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_hackathon_off\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_hackathon_enable:\n"
                    "    mov byte [hackathon_mode], 1\n"
                    "    mov bl, COLOR_ASCII\n"
                    "    mov si, msg_hackathon_on\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_hackathon_check_demo:\n"
                    "    mov di, cmd_demo\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_hackathon_end\n"
                    "    cmp byte [hackathon_mode], 1\n"
                    "    jne .patch_hackathon_locked\n"
                    "    mov bl, COLOR_ASCII\n"
                    "    mov si, msg_demo\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_hackathon_locked:\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_hackathon_locked\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_hackathon_end:"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_DATA",
                snippet=(
                    'cmd_hackathon db "hackathon", 0\n'
                    'cmd_demo db "demo", 0\n'
                    "hackathon_mode db 0\n"
                    'msg_hackathon_on db "[Hackathon mode] enabled. Demo command unlocked.", 13, 10, 0\n'
                    'msg_hackathon_off db "[Hackathon mode] disabled.", 13, 10, 0\n'
                    'msg_hackathon_locked db "Enable hackathon mode first: type hackathon.", 13, 10, 0\n'
                    'msg_demo db "Demo mode: live patches, no slides.", 13, 10, 0'
                ),
            ),
            PatchAction(
                file="src/commands/commands.map",
                marker="# command | description | source",
                snippet=(
                    "hackathon | toggle hackathon mode | src/kernel/kernel.asm\n"
                    "demo | run hackathon demo payload | src/kernel/kernel.asm"
                ),
            ),
        ),
    ),
    "customize": PatchDefinition(
        description="Enables c.atb + customization.yaml and unlocks OpenACT customization mode.",
        actions=(
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_BOOT",
                snippet=(
                    "    mov byte [patch_state_customize_color], COLOR_PROMPT\n"
                    "    mov byte [cscript_enabled], 1"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_COMMANDS",
                snippet=(
                    "    mov di, cmd_atbman\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_after_atbman\n"
                    "    add si, 6\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, arg_dash_h\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, arg_dash_dash_help\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, arg_dash_l\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_list\n"
                    "    mov di, arg_dash_dash_list\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_list\n"
                    "    mov di, arg_dash_e\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_short\n"
                    "    mov di, arg_dash_dash_exec\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_long\n"
                    "    mov di, arg_dash_i\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_install_short\n"
                    "    mov di, arg_dash_dash_install\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_install_long\n"
                    "    mov di, arg_dash_u\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_uninstall_short\n"
                    "    mov di, arg_dash_dash_uninstall\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_uninstall_long\n"
                    "    jmp .patch_customize_usage\n"
                    ".patch_customize_exec_short:\n"
                    "    add si, 2\n"
                    "    jmp .patch_customize_exec_tail\n"
                    ".patch_customize_exec_long:\n"
                    "    add si, 6\n"
                    ".patch_customize_exec_tail:\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, atb_arg_name\n"
                    "    mov cx, 32\n"
                    "    call .patch_customize_copy_token\n"
                    "    call .patch_customize_exec_program\n"
                    "    ret\n"
                    ".patch_customize_install_short:\n"
                    "    add si, 2\n"
                    "    jmp .patch_customize_install_tail\n"
                    ".patch_customize_install_long:\n"
                    "    add si, 9\n"
                    ".patch_customize_install_tail:\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, atb_arg_name\n"
                    "    mov cx, 32\n"
                    "    call .patch_customize_copy_token\n"
                    "    mov si, runtime_atbdevkit\n"
                    "    mov di, atb_arg_runtime\n"
                    "    call copy_string\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    jne .patch_customize_install_with_source\n"
                    "    mov si, atb_source_default\n"
                    "    mov di, atb_arg_source\n"
                    "    call copy_string\n"
                    "    jmp .patch_customize_install_apply\n"
                    ".patch_customize_install_with_source:\n"
                    "    mov di, atb_arg_source\n"
                    "    mov cx, 64\n"
                    "    call .patch_customize_copy_token\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_install_apply\n"
                    "    mov di, atb_arg_runtime\n"
                    "    mov cx, 15\n"
                    "    call .patch_customize_copy_token\n"
                    ".patch_customize_install_apply:\n"
                    "    call .patch_customize_install_program\n"
                    "    ret\n"
                    ".patch_customize_uninstall_short:\n"
                    "    add si, 2\n"
                    "    jmp .patch_customize_uninstall_tail\n"
                    ".patch_customize_uninstall_long:\n"
                    "    add si, 11\n"
                    ".patch_customize_uninstall_tail:\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_usage\n"
                    "    mov di, atb_arg_name\n"
                    "    mov cx, 32\n"
                    "    call .patch_customize_copy_token\n"
                    "    call .patch_customize_uninstall_program\n"
                    "    ret\n"
                    ".patch_customize_list:\n"
                    "    call .patch_customize_list_programs\n"
                    "    ret\n"
                    ".patch_customize_usage:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_usage\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_after_atbman:\n"
                    "    mov di, cmd_cp\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cp\n"
                    "    mov di, cmd_mv\n"
                    "    call strcmd\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_mv\n"
                    "    jmp .patch_customize_dispatch_continue\n"
                    ".patch_customize_cp:\n"
                    "    add si, 2\n"
                    "    mov byte [atb_fsop_mode], 0\n"
                    "    jmp .patch_customize_cp_mv_parse\n"
                    ".patch_customize_mv:\n"
                    "    add si, 2\n"
                    "    mov byte [atb_fsop_mode], 1\n"
                    ".patch_customize_cp_mv_parse:\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_cp_mv_usage\n"
                    "    mov di, fs_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call .patch_customize_copy_token\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_cp_mv_usage\n"
                    "    mov di, dir_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call .patch_customize_copy_token\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    jne .patch_customize_cp_mv_usage\n"
                    "    call .patch_customize_fs_transfer_tokens\n"
                    "    ret\n"
                    ".patch_customize_cp_mv_usage:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_fs_copy_usage\n"
                    "    cmp byte [atb_fsop_mode], 0\n"
                    "    je .patch_customize_cp_mv_usage_emit\n"
                    "    mov si, msg_fs_move_usage\n"
                    ".patch_customize_cp_mv_usage_emit:\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_tokens:\n"
                    "    mov si, fs_token\n"
                    "    call fs_resolve_with_cwd\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_path_invalid\n"
                    "    mov si, fs_token\n"
                    "    call fs_validate_cat_path\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_path_invalid\n"
                    "    mov si, dir_token\n"
                    "    call fs_resolve_with_cwd\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_path_invalid\n"
                    "    mov si, dir_token\n"
                    "    call fs_validate_file_path\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_path_invalid\n"
                    "    mov si, dir_token\n"
                    "    call fs_parent_ready_for_file\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_dir_missing\n"
                    "    mov si, fs_token\n"
                    "    mov di, atb_exec_buf\n"
                    "    call fs_copy_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_fs_transfer_file_missing\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, dir_token\n"
                    "    call fs_write_by_name\n"
                    "    cmp ax, 2\n"
                    "    jne .patch_customize_fs_transfer_post_write\n"
                    "    mov bl, [cfg_color_error]\n"
                    "    mov si, msg_fs_full\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_post_write:\n"
                    "    cmp byte [atb_fsop_mode], 1\n"
                    "    jne .patch_customize_fs_transfer_emit_copy\n"
                    "    mov si, fs_token\n"
                    "    mov di, dir_token\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_fs_transfer_emit_move\n"
                    "    mov di, fs_token\n"
                    "    call fs_remove_by_name\n"
                    ".patch_customize_fs_transfer_emit_move:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_fs_move_ok\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_emit_copy:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_fs_copy_ok\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_path_invalid:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_path_invalid\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_dir_missing:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_dir_missing\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_fs_transfer_file_missing:\n"
                    "    mov bl, [cfg_color_error]\n"
                    "    mov si, msg_file_not_found\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_copy_token:\n"
                    "    push ax\n"
                    "    push dx\n"
                    "    mov dx, cx\n"
                    "    cmp dx, 0\n"
                    "    jne .patch_customize_copy_token_loop\n"
                    "    mov byte [di], 0\n"
                    "    jmp .patch_customize_copy_token_done\n"
                    ".patch_customize_copy_token_loop:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_token_end\n"
                    "    cmp al, ' '\n"
                    "    je .patch_customize_copy_token_end\n"
                    "    cmp dx, 0\n"
                    "    je .patch_customize_copy_token_skip_store\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec dx\n"
                    ".patch_customize_copy_token_skip_store:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_token_loop\n"
                    ".patch_customize_copy_token_end:\n"
                    "    mov byte [di], 0\n"
                    ".patch_customize_copy_token_done:\n"
                    "    pop dx\n"
                    "    pop ax\n"
                    "    ret\n"
                    ".patch_customize_exec_program:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, fs_name_cscript\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_check_slot1\n"
                    "    cmp byte [cscript_enabled], 1\n"
                    "    jne .patch_customize_exec_check_slot1\n"
                    ".patch_customize_apply_script:\n"
                    "    call .patch_customize_apply_cscript_profile\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_cscript\n"
                    "    call print_color_string\n"
                    "    call .patch_customize_openact\n"
                    "    ret\n"
                    ".patch_customize_exec_check_slot1:\n"
                    "    mov di, atb_pkg1_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_slot1\n"
                    "    mov di, atb_pkg2_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_slot2\n"
                    "    mov di, atb_pkg3_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_slot3\n"
                    "    mov si, atb_arg_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_local\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_atbman_exec_missing_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    call fs_store_save\n"
                    "    ret\n"
                    ".patch_customize_exec_slot1:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_runtime_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg1_runtime\n"
                    "    mov di, runtime_python\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot1_check_c\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_python_hint\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_exec_slot1_hint_done\n"
                    ".patch_customize_exec_slot1_check_c:\n"
                    "    mov si, atb_pkg1_runtime\n"
                    "    mov di, runtime_c\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot1_hint_done\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_c_hint\n"
                    "    call print_color_string\n"
                    ".patch_customize_exec_slot1_hint_done:\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot1_done\n"
                    "    mov si, di\n"
                    "    call .patch_customize_exec_source\n"
                    ".patch_customize_exec_slot1_done:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_done\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_exec_slot2:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_runtime_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg2_runtime\n"
                    "    mov di, runtime_python\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot2_check_c\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_python_hint\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_exec_slot2_hint_done\n"
                    ".patch_customize_exec_slot2_check_c:\n"
                    "    mov si, atb_pkg2_runtime\n"
                    "    mov di, runtime_c\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot2_hint_done\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_c_hint\n"
                    "    call print_color_string\n"
                    ".patch_customize_exec_slot2_hint_done:\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot2_done\n"
                    "    mov si, di\n"
                    "    call .patch_customize_exec_source\n"
                    ".patch_customize_exec_slot2_done:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_done\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_exec_slot3:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_runtime_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg3_runtime\n"
                    "    mov di, runtime_python\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot3_check_c\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_python_hint\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_exec_slot3_hint_done\n"
                    ".patch_customize_exec_slot3_check_c:\n"
                    "    mov si, atb_pkg3_runtime\n"
                    "    mov di, runtime_c\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot3_hint_done\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_runtime_c_hint\n"
                    "    call print_color_string\n"
                    ".patch_customize_exec_slot3_hint_done:\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_slot3_done\n"
                    "    mov si, di\n"
                    "    call .patch_customize_exec_source\n"
                    ".patch_customize_exec_slot3_done:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_done\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_exec_local:\n"
                    "    push di\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_source_local\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_runtime_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, runtime_atbdevkit\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    pop si\n"
                    "    call .patch_customize_exec_source\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_done\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_exec_source:\n"
                    "    push ax\n"
                    "    push bx\n"
                    "    push cx\n"
                    "    push dx\n"
                    "    push di\n"
                    "    mov byte [atb_var_name], 0\n"
                    "    mov byte [atb_var_value], 0\n"
                    "    mov byte [atb_if_pending], 0\n"
                    "    mov byte [atb_if_result], 0\n"
                    "    mov word [atb_int_a], 0\n"
                    "    mov word [atb_int_b], 0\n"
                    "    mov word [atb_int_user_choice], 0\n"
                    ".patch_customize_exec_line:\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_exec_source_done\n"
                    "    mov di, atb_line_buf\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    mov byte [atb_quote_state], 0\n"
                    ".patch_customize_exec_copy_line:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_exec_line_end\n"
                    "    cmp al, 13\n"
                    "    je .patch_customize_exec_line_cr\n"
                    "    cmp al, 10\n"
                    "    je .patch_customize_exec_line_lf\n"
                    "    cmp al, '\"'\n"
                    "    jne .patch_customize_exec_copy_line_check_sc\n"
                    "    xor byte [atb_quote_state], 1\n"
                    "    jmp .patch_customize_exec_copy_line_store\n"
                    ".patch_customize_exec_copy_line_check_sc:\n"
                    "    cmp al, ';'\n"
                    "    je .patch_customize_exec_line_sc\n"
                    ".patch_customize_exec_copy_line_store:\n"
                    "    cmp cx, 0\n"
                    "    je .patch_customize_exec_copy_skip_store\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec cx\n"
                    ".patch_customize_exec_copy_skip_store:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_exec_copy_line\n"
                    ".patch_customize_exec_line_cr:\n"
                    "    inc si\n"
                    "    cmp byte [si], 10\n"
                    "    jne .patch_customize_exec_line_end\n"
                    "    inc si\n"
                    "    jmp .patch_customize_exec_line_end\n"
                    ".patch_customize_exec_line_lf:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_exec_line_end\n"
                    ".patch_customize_exec_line_sc:\n"
                    "    cmp byte [atb_quote_state], 0\n"
                    "    jne .patch_customize_exec_copy_line_store\n"
                    "    inc si\n"
                    ".patch_customize_exec_line_end:\n"
                    "    mov byte [di], 0\n"
                    "    mov [atb_exec_src_ptr], si\n"
                    "    mov si, atb_line_buf\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_exec_continue\n"
                    "    cmp byte [si], '<'\n"
                    "    je .patch_customize_exec_continue\n"
                    "    mov di, atb_devkit_cmd_func\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_continue\n"
                    "    mov di, atb_devkit_cmd_else\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_else\n"
                    "    mov byte [atb_if_pending], 0\n"
                    "    mov di, atb_devkit_cmd_if\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_if\n"
                    "    mov di, atb_devkit_cmd_output3\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_output3\n"
                    "    mov di, atb_devkit_cmd_output1\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_output1\n"
                    "    mov di, atb_devkit_cmd_output2\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_output2\n"
                    "    mov di, atb_devkit_cmd_run1\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_run1\n"
                    "    mov di, atb_devkit_cmd_run2\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_run2\n"
                    "    mov di, atb_devkit_cmd_clear\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_clear\n"
                    "    mov di, atb_devkit_cmd_menu_title\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_menu_title\n"
                    "    mov di, atb_devkit_cmd_menu_item\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_menu_item\n"
                    "    mov di, atb_devkit_cmd_menu_input\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_menu_input\n"
                    "    mov di, atb_devkit_cmd_var\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_var\n"
                    "    mov di, atb_devkit_cmd_write\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_write\n"
                    "    mov di, atb_devkit_cmd_copy\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_copy\n"
                    "    mov di, atb_devkit_cmd_move\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_move\n"
                    "    mov di, atb_devkit_cmd_append\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_append\n"
                    "    mov di, atb_devkit_cmd_read\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_exec_read\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_output1:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_output2:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_output3:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_run1:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_run2:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_clear:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_menu_title:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_menu_item:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_menu_input:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_else:\n"
                    "    add si, 4\n"
                    "    call skip_spaces\n"
                    "    cmp byte [atb_if_pending], 1\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    cmp byte [atb_if_result], 1\n"
                    "    je .patch_customize_exec_else_done\n"
                    "    call .patch_customize_find_arrow\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_else_done\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    ".patch_customize_exec_else_done:\n"
                    "    mov byte [atb_if_pending], 0\n"
                    "    mov byte [atb_if_result], 0\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_if:\n"
                    "    mov byte [atb_if_pending], 1\n"
                    "    mov byte [atb_if_result], 0\n"
                    "    add si, 2\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_if_left\n"
                    "    mov cx, 32\n"
                    "    call copy_token_limited\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], '='\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    inc si\n"
                    "    cmp byte [si], '='\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    inc si\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_if_rhs], ax\n"
                    "    mov si, atb_if_left\n"
                    "    call .patch_customize_get_named_int\n"
                    "    cmp dx, 1\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    cmp ax, [atb_if_rhs]\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    mov byte [atb_if_result], 1\n"
                    "    call .patch_customize_find_arrow\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_inline_stmt:\n"
                    "    push bx\n"
                    "    push cx\n"
                    "    push di\n"
                    "    mov di, atb_devkit_cmd_output1\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_output2\n"
                    "    add si, 22\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    call .patch_customize_emit_expr_from_buf\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_output2:\n"
                    "    mov di, atb_devkit_cmd_output2\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_output3\n"
                    "    add si, 12\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    call .patch_customize_emit_expr_from_buf\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_output3:\n"
                    "    mov di, atb_devkit_cmd_output3\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_run1\n"
                    "    add si, 7\n"
                    "    call .patch_customize_copy_until_rparen\n"
                    "    mov bx, si\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_tmp_token\n"
                    "    mov cx, 32\n"
                    "    call copy_token_limited\n"
                    "    mov si, bx\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_inline_output3_emit_expr\n"
                    "    call .patch_customize_find_arrow\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_output3_emit_expr\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    call .patch_customize_emit_expr_from_buf\n"
                    "    call .patch_customize_output3_maybe_read_input\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_output3_emit_expr:\n"
                    "    call .patch_customize_emit_expr_from_buf\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_run1:\n"
                    "    mov di, atb_devkit_cmd_run1\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_run2\n"
                    "    add si, 19\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call .patch_customize_run_command_buf\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_run2:\n"
                    "    mov di, atb_devkit_cmd_run2\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_clear\n"
                    "    add si, 16\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call .patch_customize_run_command_buf\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_clear:\n"
                    "    mov di, atb_devkit_cmd_clear\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_menu_title\n"
                    "    call clear_screen\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_menu_title:\n"
                    "    mov di, atb_devkit_cmd_menu_title\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_menu_item\n"
                    "    add si, 19\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov bl, [cfg_color_frame]\n"
                    "    mov si, msg_atb_menu_frame\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_ascii]\n"
                    "    mov si, atb_exec_buf\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_frame]\n"
                    "    mov si, msg_atb_menu_frame\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_menu_item:\n"
                    "    mov di, atb_devkit_cmd_menu_item\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_menu_input\n"
                    "    add si, 18\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atb_menu_item_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_exec_buf\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_menu_input:\n"
                    "    mov di, atb_devkit_cmd_menu_input\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_write\n"
                    "    add si, 19\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_var_name\n"
                    "    mov cx, 32\n"
                    "    call copy_token_limited\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atb_menu_prompt\n"
                    "    call print_color_string\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, atb_var_value\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    call .patch_customize_set_named_int\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_write:\n"
                    "    mov di, atb_devkit_cmd_write\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_append\n"
                    "    add si, 17\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call copy_token_limited\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    call fs_write_by_name\n"
                    "    cmp ax, 2\n"
                    "    jne .patch_customize_inline_write_done\n"
                    "    mov bl, [cfg_color_error]\n"
                    "    mov si, msg_fs_full\n"
                    "    call print_color_string\n"
                    ".patch_customize_inline_write_done:\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_append:\n"
                    "    mov di, atb_devkit_cmd_append\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_read\n"
                    "    add si, 18\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call copy_token_limited\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    call fs_append_by_name\n"
                    "    cmp ax, 2\n"
                    "    jne .patch_customize_inline_append_done\n"
                    "    mov bl, [cfg_color_error]\n"
                    "    mov si, msg_fs_full\n"
                    "    call print_color_string\n"
                    ".patch_customize_inline_append_done:\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_read:\n"
                    "    mov di, atb_devkit_cmd_read\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_copy\n"
                    "    add si, 16\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call copy_token_limited\n"
                    "    mov si, fs_token\n"
                    "    call fs_validate_cat_path\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_inline_read_try\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_path_invalid\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_read_try:\n"
                    "    mov si, fs_token\n"
                    "    call fs_cat_by_name\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_inline_read_done\n"
                    "    mov bl, [cfg_color_error]\n"
                    "    mov si, msg_file_not_found\n"
                    "    call print_color_string\n"
                    ".patch_customize_inline_read_done:\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_check_copy:\n"
                    "    mov di, atb_devkit_cmd_copy\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_check_move\n"
                    "    add si, 16\n"
                    "    mov byte [atb_fsop_mode], 0\n"
                    "    jmp .patch_customize_inline_copy_move_parse\n"
                    ".patch_customize_inline_check_move:\n"
                    "    mov di, atb_devkit_cmd_move\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    add si, 16\n"
                    "    mov byte [atb_fsop_mode], 1\n"
                    ".patch_customize_inline_copy_move_parse:\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, fs_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call copy_token_limited\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    cmp byte [si], ':'\n"
                    "    jne .patch_customize_inline_noop\n"
                    "    inc si\n"
                    "    call skip_spaces\n"
                    "    mov di, dir_token\n"
                    "    mov cx, FS_NAME_MAX\n"
                    "    call copy_token_limited\n"
                    "    call .patch_customize_fs_transfer_tokens\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_inline_done\n"
                    ".patch_customize_inline_noop:\n"
                    "    xor ax, ax\n"
                    ".patch_customize_inline_done:\n"
                    "    pop di\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_run_command_buf:\n"
                    "    push ax\n"
                    "    push bx\n"
                    "    push cx\n"
                    "    push di\n"
                    "    push bp\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_run_done\n"
                    "    mov di, atb_tmp_token\n"
                    "    mov cx, 32\n"
                    "    call copy_token_limited\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, runtime_python\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_python\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, runtime_python3\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_python\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, runtime_c\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_c\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, runtime_generic\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_native\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg1_runtime\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg_runtime\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg2_runtime\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg_runtime\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg3_runtime\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg_runtime\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg1_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg1\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg2_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg2\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_pkg3_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_host_pkg3\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, input_buffer\n"
                    "    mov cx, MAX_INPUT\n"
                    "    call copy_string_limited\n"
                    "    mov si, input_buffer\n"
                    "    call dispatch_command\n"
                    "    jmp .patch_customize_run_done\n"
                    ".patch_customize_run_host_python:\n"
                    "    mov bp, runtime_python\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_c:\n"
                    "    mov bp, runtime_c\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_native:\n"
                    "    mov bp, runtime_generic\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_pkg_runtime:\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, runtime_atbdevkit\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_done\n"
                    "    mov bp, atb_tmp_token\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_pkg1:\n"
                    "    mov si, atb_pkg1_runtime\n"
                    "    mov di, runtime_atbdevkit\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_done\n"
                    "    mov bp, atb_pkg1_runtime\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_pkg2:\n"
                    "    mov si, atb_pkg2_runtime\n"
                    "    mov di, runtime_atbdevkit\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_done\n"
                    "    mov bp, atb_pkg2_runtime\n"
                    "    jmp .patch_customize_run_host_emit\n"
                    ".patch_customize_run_host_pkg3:\n"
                    "    mov si, atb_pkg3_runtime\n"
                    "    mov di, runtime_atbdevkit\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_run_done\n"
                    "    mov bp, atb_pkg3_runtime\n"
                    ".patch_customize_run_host_emit:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atb_run_host_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, bp\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atb_run_host_cmd\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_exec_buf\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    ".patch_customize_run_done:\n"
                    "    pop bp\n"
                    "    pop di\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    pop ax\n"
                    "    ret\n"
                    ".patch_customize_exec_write:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_copy:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_move:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_append:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_read:\n"
                    "    call .patch_customize_exec_inline_stmt\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_var:\n"
                    "    add si, 3\n"
                    "    call .patch_customize_skip_var_delims\n"
                    "    mov di, atb_var_name\n"
                    "    mov cx, 32\n"
                    "    call .patch_customize_copy_var_ident\n"
                    "    call .patch_customize_find_arrow\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_continue\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_devkit_expr_input\n"
                    "    call strprefix\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_exec_var_assign_expr\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, atb_var_value\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    call .patch_customize_set_named_int\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_exec_var_assign_expr:\n"
                    "    call .patch_customize_copy_payload\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, atb_var_value\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    call .patch_customize_set_named_int\n"
                    "    jmp .patch_customize_exec_continue\n"
                    ".patch_customize_skip_var_delims:\n"
                    ".patch_customize_skip_var_delims_loop:\n"
                    "    mov al, [si]\n"
                    "    cmp al, ' '\n"
                    "    je .patch_customize_skip_var_delims_inc\n"
                    "    cmp al, ':'\n"
                    "    je .patch_customize_skip_var_delims_inc\n"
                    "    ret\n"
                    ".patch_customize_skip_var_delims_inc:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_skip_var_delims_loop\n"
                    ".patch_customize_copy_var_ident:\n"
                    "    cmp cx, 0\n"
                    "    jne .patch_customize_copy_var_ident_loop\n"
                    "    mov byte [di], 0\n"
                    "    ret\n"
                    ".patch_customize_copy_var_ident_loop:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ' '\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ':'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '='\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '>'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '('\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ')'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    inc si\n"
                    "    dec cx\n"
                    "    jnz .patch_customize_copy_var_ident_loop\n"
                    ".patch_customize_copy_var_ident_skip_tail:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ' '\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ':'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '='\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '>'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, '('\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    cmp al, ')'\n"
                    "    je .patch_customize_copy_var_ident_done\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_var_ident_skip_tail\n"
                    ".patch_customize_copy_var_ident_done:\n"
                    "    mov byte [di], 0\n"
                    "    ret\n"
                    ".patch_customize_find_arrow:\n"
                    "    push bx\n"
                    ".patch_customize_find_arrow_loop:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_find_arrow_no\n"
                    "    cmp al, '='\n"
                    "    jne .patch_customize_find_arrow_next\n"
                    "    mov bx, si\n"
                    "    inc bx\n"
                    ".patch_customize_find_arrow_skip_spaces:\n"
                    "    cmp byte [bx], ' '\n"
                    "    jne .patch_customize_find_arrow_check_gt\n"
                    "    inc bx\n"
                    "    jmp .patch_customize_find_arrow_skip_spaces\n"
                    ".patch_customize_find_arrow_check_gt:\n"
                    "    cmp byte [bx], '>'\n"
                    "    jne .patch_customize_find_arrow_next\n"
                    "    mov si, bx\n"
                    "    inc si\n"
                    "    mov ax, 1\n"
                    "    jmp .patch_customize_find_arrow_done\n"
                    ".patch_customize_find_arrow_next:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_find_arrow_loop\n"
                    ".patch_customize_find_arrow_no:\n"
                    "    xor ax, ax\n"
                    ".patch_customize_find_arrow_done:\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_copy_until_rparen:\n"
                    "    push ax\n"
                    "    push cx\n"
                    "    push di\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    ".patch_customize_copy_until_rparen_loop:\n"
                    "    cmp cx, 0\n"
                    "    je .patch_customize_copy_until_rparen_done\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_until_rparen_done\n"
                    "    cmp al, ')'\n"
                    "    je .patch_customize_copy_until_rparen_close\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec cx\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_until_rparen_loop\n"
                    ".patch_customize_copy_until_rparen_close:\n"
                    "    inc si\n"
                    ".patch_customize_copy_until_rparen_done:\n"
                    "    mov byte [di], 0\n"
                    "    pop di\n"
                    "    pop cx\n"
                    "    pop ax\n"
                    "    ret\n"
                    ".patch_customize_set_named_int:\n"
                    "    mov si, atb_var_name\n"
                    "    mov di, atb_name_a\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_set_named_int_check_b\n"
                    "    mov si, atb_var_value\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_a], ax\n"
                    "    ret\n"
                    ".patch_customize_set_named_int_check_b:\n"
                    "    mov si, atb_var_name\n"
                    "    mov di, atb_name_b\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_set_named_int_check_choice\n"
                    "    mov si, atb_var_value\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_b], ax\n"
                    "    ret\n"
                    ".patch_customize_set_named_int_check_choice:\n"
                    "    mov si, atb_var_name\n"
                    "    mov di, atb_name_user_choice\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_set_named_int_done\n"
                    "    mov si, atb_var_value\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_user_choice], ax\n"
                    ".patch_customize_set_named_int_done:\n"
                    "    ret\n"
                    ".patch_customize_output3_maybe_read_input:\n"
                    "    mov si, atb_tmp_token\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_output3_input_done\n"
                    "    mov di, atb_name_a\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_output3_read_a\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_name_b\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_output3_read_b\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_name_user_choice\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_output3_read_choice\n"
                    "    mov si, atb_tmp_token\n"
                    "    mov di, atb_var_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_output3_input_done\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    mov di, atb_var_value\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    call .patch_customize_set_named_int\n"
                    "    jmp .patch_customize_output3_input_done\n"
                    ".patch_customize_output3_read_a:\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_a], ax\n"
                    "    jmp .patch_customize_output3_input_done\n"
                    ".patch_customize_output3_read_b:\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_b], ax\n"
                    "    jmp .patch_customize_output3_input_done\n"
                    ".patch_customize_output3_read_choice:\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov word [input_limit], MAX_INPUT\n"
                    "    call read_line_limited\n"
                    "    mov si, atb_exec_buf\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov [atb_int_user_choice], ax\n"
                    ".patch_customize_output3_input_done:\n"
                    "    ret\n"
                    ".patch_customize_get_named_int:\n"
                    "    mov di, atb_name_a\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_get_named_int_check_b\n"
                    "    mov ax, [atb_int_a]\n"
                    "    mov dx, 1\n"
                    "    ret\n"
                    ".patch_customize_get_named_int_check_b:\n"
                    "    mov di, atb_name_b\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_get_named_int_check_choice\n"
                    "    mov ax, [atb_int_b]\n"
                    "    mov dx, 1\n"
                    "    ret\n"
                    ".patch_customize_get_named_int_check_choice:\n"
                    "    mov di, atb_name_user_choice\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_get_named_int_check_var\n"
                    "    mov ax, [atb_int_user_choice]\n"
                    "    mov dx, 1\n"
                    "    ret\n"
                    ".patch_customize_get_named_int_check_var:\n"
                    "    mov di, atb_var_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_get_named_int_no\n"
                    "    mov si, atb_var_value\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov dx, 1\n"
                    "    ret\n"
                    ".patch_customize_get_named_int_no:\n"
                    "    xor ax, ax\n"
                    "    xor dx, dx\n"
                    "    ret\n"
                    ".patch_customize_emit_expr_from_buf:\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    cmp byte [si], 0\n"
                    "    je .patch_customize_emit_expr_done\n"
                    "    mov di, atb_var_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_emit_expr_check_num_a\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, atb_var_value\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_emit_expr_newline\n"
                    ".patch_customize_emit_expr_check_num_a:\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_name_a\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_emit_expr_check_num_b\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov ax, [atb_int_a]\n"
                    "    call print_u16\n"
                    "    jmp .patch_customize_emit_expr_newline\n"
                    ".patch_customize_emit_expr_check_num_b:\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_name_b\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_emit_expr_check_num_choice\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov ax, [atb_int_b]\n"
                    "    call print_u16\n"
                    "    jmp .patch_customize_emit_expr_newline\n"
                    ".patch_customize_emit_expr_check_num_choice:\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    mov di, atb_name_user_choice\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_emit_expr_eval\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov ax, [atb_int_user_choice]\n"
                    "    call print_u16\n"
                    "    jmp .patch_customize_emit_expr_newline\n"
                    ".patch_customize_emit_expr_eval:\n"
                    "    mov si, atb_exec_buf\n"
                    "    call skip_spaces\n"
                    "    call .patch_customize_eval_int_expr\n"
                    "    cmp dx, 1\n"
                    "    jne .patch_customize_emit_expr_raw\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    call print_u16\n"
                    "    jmp .patch_customize_emit_expr_newline\n"
                    ".patch_customize_emit_expr_raw:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, atb_exec_buf\n"
                    "    call print_color_string\n"
                    ".patch_customize_emit_expr_newline:\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    ".patch_customize_emit_expr_done:\n"
                    "    ret\n"
                    ".patch_customize_parse_u16:\n"
                    "    push bx\n"
                    "    xor ax, ax\n"
                    "    call skip_spaces\n"
                    ".patch_customize_parse_u16_loop:\n"
                    "    mov bl, [si]\n"
                    "    cmp bl, '0'\n"
                    "    jb .patch_customize_parse_u16_done\n"
                    "    cmp bl, '9'\n"
                    "    ja .patch_customize_parse_u16_done\n"
                    "    mov bx, ax\n"
                    "    shl ax, 1\n"
                    "    shl bx, 3\n"
                    "    add ax, bx\n"
                    "    mov bl, [si]\n"
                    "    sub bl, '0'\n"
                    "    xor bh, bh\n"
                    "    add ax, bx\n"
                    "    inc si\n"
                    "    jmp .patch_customize_parse_u16_loop\n"
                    ".patch_customize_parse_u16_done:\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_eval_int_expr:\n"
                    "    push bx\n"
                    "    push cx\n"
                    "    call .patch_customize_parse_operand\n"
                    "    cmp dx, 1\n"
                    "    jne .patch_customize_eval_int_expr_fail\n"
                    "    mov cx, ax\n"
                    "    call skip_spaces\n"
                    "    mov bl, [si]\n"
                    "    cmp bl, 0\n"
                    "    je .patch_customize_eval_int_expr_single\n"
                    "    cmp bl, '+'\n"
                    "    je .patch_customize_eval_int_expr_op\n"
                    "    cmp bl, '-'\n"
                    "    je .patch_customize_eval_int_expr_op\n"
                    "    cmp bl, '*'\n"
                    "    je .patch_customize_eval_int_expr_op\n"
                    "    cmp bl, '/'\n"
                    "    je .patch_customize_eval_int_expr_op\n"
                    "    cmp bl, 92\n"
                    "    je .patch_customize_eval_int_expr_op\n"
                    "    jmp .patch_customize_eval_int_expr_fail\n"
                    ".patch_customize_eval_int_expr_op:\n"
                    "    push bx\n"
                    "    inc si\n"
                    "    call .patch_customize_parse_operand\n"
                    "    pop bx\n"
                    "    cmp dx, 1\n"
                    "    jne .patch_customize_eval_int_expr_fail\n"
                    "    mov dx, ax\n"
                    "    mov ax, cx\n"
                    "    cmp bl, '+'\n"
                    "    jne .patch_customize_eval_int_expr_check_sub\n"
                    "    add ax, dx\n"
                    "    jmp .patch_customize_eval_int_expr_ok\n"
                    ".patch_customize_eval_int_expr_check_sub:\n"
                    "    cmp bl, '-'\n"
                    "    jne .patch_customize_eval_int_expr_check_mul\n"
                    "    sub ax, dx\n"
                    "    jmp .patch_customize_eval_int_expr_ok\n"
                    ".patch_customize_eval_int_expr_check_mul:\n"
                    "    cmp bl, '*'\n"
                    "    jne .patch_customize_eval_int_expr_check_div\n"
                    "    mul dx\n"
                    "    jmp .patch_customize_eval_int_expr_ok\n"
                    ".patch_customize_eval_int_expr_check_div:\n"
                    "    cmp dx, 0\n"
                    "    je .patch_customize_eval_int_expr_fail\n"
                    "    mov bx, dx\n"
                    "    xor dx, dx\n"
                    "    div bx\n"
                    "    jmp .patch_customize_eval_int_expr_ok\n"
                    ".patch_customize_eval_int_expr_single:\n"
                    "    mov ax, cx\n"
                    ".patch_customize_eval_int_expr_ok:\n"
                    "    mov dx, 1\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_eval_int_expr_fail:\n"
                    "    xor ax, ax\n"
                    "    xor dx, dx\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_parse_operand:\n"
                    "    call skip_spaces\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_parse_operand_fail\n"
                    "    cmp al, '0'\n"
                    "    jb .patch_customize_parse_operand_name\n"
                    "    cmp al, '9'\n"
                    "    ja .patch_customize_parse_operand_name\n"
                    "    call .patch_customize_parse_u16\n"
                    "    mov dx, 1\n"
                    "    ret\n"
                    ".patch_customize_parse_operand_name:\n"
                    "    push bx\n"
                    "    push cx\n"
                    "    push di\n"
                    "    mov di, atb_tmp_token\n"
                    "    mov cx, 32\n"
                    ".patch_customize_parse_operand_name_loop:\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, ' '\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, '+'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, '-'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, '*'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, '/'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, 92\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, ')'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp al, ';'\n"
                    "    je .patch_customize_parse_operand_name_done\n"
                    "    cmp cx, 0\n"
                    "    je .patch_customize_parse_operand_name_skip_store\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec cx\n"
                    ".patch_customize_parse_operand_name_skip_store:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_parse_operand_name_loop\n"
                    ".patch_customize_parse_operand_name_done:\n"
                    "    mov byte [di], 0\n"
                    "    mov bx, si\n"
                    "    mov si, atb_tmp_token\n"
                    "    call .patch_customize_get_named_int\n"
                    "    mov si, bx\n"
                    "    pop di\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    ret\n"
                    ".patch_customize_parse_operand_fail:\n"
                    "    xor ax, ax\n"
                    "    xor dx, dx\n"
                    "    ret\n"
                    ".patch_customize_exec_continue:\n"
                    "    mov si, [atb_exec_src_ptr]\n"
                    "    jmp .patch_customize_exec_line\n"
                    ".patch_customize_copy_payload:\n"
                    "    push ax\n"
                    "    push cx\n"
                    "    push di\n"
                    "    mov di, atb_exec_buf\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    cmp byte [si], '\"'\n"
                    "    jne .patch_customize_copy_payload_raw\n"
                    "    inc si\n"
                    ".patch_customize_copy_payload_qloop:\n"
                    "    cmp cx, 0\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    cmp al, '\"'\n"
                    "    je .patch_customize_copy_payload_qend\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec cx\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_payload_qloop\n"
                    ".patch_customize_copy_payload_qend:\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_payload_done\n"
                    ".patch_customize_copy_payload_raw:\n"
                    ".patch_customize_copy_payload_rloop:\n"
                    "    cmp cx, 0\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    mov al, [si]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    cmp al, 13\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    cmp al, 10\n"
                    "    je .patch_customize_copy_payload_done\n"
                    "    mov [di], al\n"
                    "    inc di\n"
                    "    dec cx\n"
                    "    inc si\n"
                    "    jmp .patch_customize_copy_payload_rloop\n"
                    ".patch_customize_copy_payload_done:\n"
                    "    mov byte [di], 0\n"
                    "    pop di\n"
                    "    pop cx\n"
                    "    pop ax\n"
                    "    ret\n"
                    ".patch_customize_exec_source_done:\n"
                    "    call fs_store_save\n"
                    "    pop di\n"
                    "    pop dx\n"
                    "    pop cx\n"
                    "    pop bx\n"
                    "    pop ax\n"
                    "    ret\n"
                    ".patch_customize_install_program:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, fs_name_cscript\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_install_check_existing\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_core_present\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_install_check_existing:\n"
                    "    mov di, atb_pkg1_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_install_exists\n"
                    "    mov di, atb_pkg2_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_install_exists\n"
                    "    mov di, atb_pkg3_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_install_exists\n"
                    "    cmp byte [atb_pkg1_name], 0\n"
                    "    je .patch_customize_install_slot1\n"
                    "    cmp byte [atb_pkg2_name], 0\n"
                    "    je .patch_customize_install_slot2\n"
                    "    cmp byte [atb_pkg3_name], 0\n"
                    "    je .patch_customize_install_slot3\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_atbman_install_full\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_install_exists:\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_install_exists_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    call fs_store_save\n"
                    "    ret\n"
                    ".patch_customize_install_slot1:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, atb_pkg1_name\n"
                    "    mov cx, 32\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_source\n"
                    "    mov di, atb_pkg1_source\n"
                    "    mov cx, 64\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_runtime\n"
                    "    mov di, atb_pkg1_runtime\n"
                    "    mov cx, 15\n"
                    "    call copy_string_limited\n"
                    "    jmp .patch_customize_install_ok\n"
                    ".patch_customize_install_slot2:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, atb_pkg2_name\n"
                    "    mov cx, 32\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_source\n"
                    "    mov di, atb_pkg2_source\n"
                    "    mov cx, 64\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_runtime\n"
                    "    mov di, atb_pkg2_runtime\n"
                    "    mov cx, 15\n"
                    "    call copy_string_limited\n"
                    "    jmp .patch_customize_install_ok\n"
                    ".patch_customize_install_slot3:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, atb_pkg3_name\n"
                    "    mov cx, 32\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_source\n"
                    "    mov di, atb_pkg3_source\n"
                    "    mov cx, 64\n"
                    "    call copy_string_limited\n"
                    "    mov si, atb_arg_runtime\n"
                    "    mov di, atb_pkg3_runtime\n"
                    "    mov cx, 15\n"
                    "    call copy_string_limited\n"
                    ".patch_customize_install_ok:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_install_ok_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_install_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_install_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_uninstall_program:\n"
                    "    mov si, atb_arg_name\n"
                    "    mov di, fs_name_cscript\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_uninstall_check_slot1\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_atbman_core_protected\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_uninstall_check_slot1:\n"
                    "    mov di, atb_pkg1_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_uninstall_slot1\n"
                    "    mov di, atb_pkg2_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_uninstall_slot2\n"
                    "    mov di, atb_pkg3_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_uninstall_slot3\n"
                    "    mov bl, COLOR_ERROR\n"
                    "    mov si, msg_atbman_uninstall_missing_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_uninstall_slot1:\n"
                    "    mov byte [atb_pkg1_name], 0\n"
                    "    mov byte [atb_pkg1_source], 0\n"
                    "    mov byte [atb_pkg1_runtime], 0\n"
                    "    jmp .patch_customize_uninstall_ok\n"
                    ".patch_customize_uninstall_slot2:\n"
                    "    mov byte [atb_pkg2_name], 0\n"
                    "    mov byte [atb_pkg2_source], 0\n"
                    "    mov byte [atb_pkg2_runtime], 0\n"
                    "    jmp .patch_customize_uninstall_ok\n"
                    ".patch_customize_uninstall_slot3:\n"
                    "    mov byte [atb_pkg3_name], 0\n"
                    "    mov byte [atb_pkg3_source], 0\n"
                    "    mov byte [atb_pkg3_runtime], 0\n"
                    ".patch_customize_uninstall_ok:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_uninstall_ok_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_arg_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_list_programs:\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, msg_atbman_list_title\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, fs_name_cscript\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_source_core\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_runtime_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, runtime_atbdevkit\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    xor dl, dl\n"
                    "    cmp byte [atb_pkg1_name], 0\n"
                    "    je .patch_customize_list_slot2\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_runtime_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    inc dl\n"
                    ".patch_customize_list_slot2:\n"
                    "    cmp byte [atb_pkg2_name], 0\n"
                    "    je .patch_customize_list_slot3\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_runtime_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    inc dl\n"
                    ".patch_customize_list_slot3:\n"
                    "    cmp byte [atb_pkg3_name], 0\n"
                    "    je .patch_customize_list_finish\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_list_runtime_sep\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_runtime\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    inc dl\n"
                    ".patch_customize_list_finish:\n"
                    "    cmp dl, 0\n"
                    "    jne .patch_customize_list_done\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_atbman_list_none\n"
                    "    call print_color_string\n"
                    ".patch_customize_list_done:\n"
                    "    ret\n"
                    ".patch_customize_apply_cscript_profile:\n"
                    "    mov byte [cfg_banner_enabled], 1\n"
                    "    mov byte [cfg_prompt_compact], 1\n"
                    "    mov byte [cfg_theme_index], 2\n"
                    "    call .patch_customize_theme_2\n"
                    "    ret\n"
                    ".patch_customize_cycle_theme:\n"
                    "    mov al, [cfg_theme_index]\n"
                    "    inc al\n"
                    "    cmp al, 3\n"
                    "    jb .patch_customize_cycle_store\n"
                    "    xor al, al\n"
                    ".patch_customize_cycle_store:\n"
                    "    mov [cfg_theme_index], al\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_theme_0\n"
                    "    cmp al, 1\n"
                    "    je .patch_customize_theme_1\n"
                    "    jmp .patch_customize_theme_2\n"
                    ".patch_customize_theme_0:\n"
                    "    mov byte [cfg_color_default], 0x07\n"
                    "    mov byte [cfg_color_info], 0x0B\n"
                    "    mov byte [cfg_color_warn], 0x0E\n"
                    "    mov byte [cfg_color_error], 0x0C\n"
                    "    mov byte [cfg_color_prompt], 0x0A\n"
                    "    mov byte [cfg_color_ascii], 0x0D\n"
                    "    mov byte [cfg_color_frame], 0x09\n"
                    "    mov byte [cfg_color_accent], 0x03\n"
                    "    ret\n"
                    ".patch_customize_theme_1:\n"
                    "    mov byte [cfg_color_default], 0x07\n"
                    "    mov byte [cfg_color_info], 0x0F\n"
                    "    mov byte [cfg_color_warn], 0x0B\n"
                    "    mov byte [cfg_color_error], 0x0C\n"
                    "    mov byte [cfg_color_prompt], 0x0B\n"
                    "    mov byte [cfg_color_ascii], 0x0F\n"
                    "    mov byte [cfg_color_frame], 0x0B\n"
                    "    mov byte [cfg_color_accent], 0x09\n"
                    "    ret\n"
                    ".patch_customize_theme_2:\n"
                    "    mov byte [cfg_color_default], 0x07\n"
                    "    mov byte [cfg_color_info], 0x0E\n"
                    "    mov byte [cfg_color_warn], 0x06\n"
                    "    mov byte [cfg_color_error], 0x0C\n"
                    "    mov byte [cfg_color_prompt], 0x0E\n"
                    "    mov byte [cfg_color_ascii], 0x06\n"
                    "    mov byte [cfg_color_frame], 0x06\n"
                    "    mov byte [cfg_color_accent], 0x0C\n"
                    "    ret\n"
                    ".patch_customize_openact:\n"
                    "    call clear_screen\n"
                    ".patch_customize_openact_redraw:\n"
                    "    mov bl, [cfg_color_ascii]\n"
                    "    mov si, msg_openact_title\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_openact_credit\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_banner\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    cmp byte [cfg_banner_enabled], 1\n"
                    "    jne .patch_customize_openact_banner_off\n"
                    "    mov si, msg_openact_on\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_openact_banner_tail\n"
                    ".patch_customize_openact_banner_off:\n"
                    "    mov si, msg_openact_off\n"
                    "    call print_color_string\n"
                    ".patch_customize_openact_banner_tail:\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_theme\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    call .patch_customize_openact_print_theme\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_prompt\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    cmp byte [cfg_prompt_compact], 1\n"
                    "    jne .patch_customize_openact_prompt_classic\n"
                    "    mov si, msg_openact_prompt_compact\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_openact_prompt_tail\n"
                    ".patch_customize_openact_prompt_classic:\n"
                    "    mov si, msg_openact_prompt_classic\n"
                    "    call print_color_string\n"
                    ".patch_customize_openact_prompt_tail:\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_user\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    cmp byte [username], 0\n"
                    "    jne .patch_customize_openact_user_named\n"
                    "    mov si, default_user\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_openact_user_tail\n"
                    ".patch_customize_openact_user_named:\n"
                    "    mov si, username\n"
                    "    call print_color_string\n"
                    ".patch_customize_openact_user_tail:\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_opt_readme\n"
                    "    call print_color_string\n"
                    "    mov si, msg_openact_opt_judges\n"
                    "    call print_color_string\n"
                    "    mov si, msg_openact_opt_unknown\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_warn]\n"
                    "    mov si, msg_openact_keys\n"
                    "    call print_color_string\n"
                    ".patch_customize_openact_wait_key:\n"
                    "    mov ah, 0x00\n"
                    "    int 0x16\n"
                    "    cmp al, '1'\n"
                    "    je .patch_customize_openact_toggle_banner\n"
                    "    cmp al, '2'\n"
                    "    je .patch_customize_openact_cycle_theme\n"
                    "    cmp al, '3'\n"
                    "    je .patch_customize_openact_toggle_prompt\n"
                    "    cmp al, '4'\n"
                    "    je .patch_customize_openact_edit_user\n"
                    "    cmp al, '5'\n"
                    "    je .patch_customize_openact_edit_readme\n"
                    "    cmp al, '6'\n"
                    "    je .patch_customize_openact_edit_judges\n"
                    "    cmp al, '7'\n"
                    "    je .patch_customize_openact_edit_unknown\n"
                    "    cmp al, 'r'\n"
                    "    je .patch_customize_openact_reset_profile\n"
                    "    cmp al, 'R'\n"
                    "    je .patch_customize_openact_reset_profile\n"
                    "    cmp al, 's'\n"
                    "    je .patch_customize_openact_save_exit\n"
                    "    cmp al, 'S'\n"
                    "    je .patch_customize_openact_save_exit\n"
                    "    cmp al, 'q'\n"
                    "    je .patch_customize_openact_save_exit\n"
                    "    cmp al, 'Q'\n"
                    "    je .patch_customize_openact_save_exit\n"
                    "    cmp al, 27\n"
                    "    je .patch_customize_openact_save_exit\n"
                    "    jmp .patch_customize_openact_wait_key\n"
                    ".patch_customize_openact_toggle_banner:\n"
                    "    mov al, [cfg_banner_enabled]\n"
                    "    xor al, 1\n"
                    "    mov [cfg_banner_enabled], al\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_cycle_theme:\n"
                    "    call .patch_customize_cycle_theme\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_toggle_prompt:\n"
                    "    mov al, [cfg_prompt_compact]\n"
                    "    xor al, 1\n"
                    "    mov [cfg_prompt_compact], al\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_edit_user:\n"
                    "    call clear_screen\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, msg_openact_enter_user\n"
                    "    call print_color_string\n"
                    "    mov di, username\n"
                    "    mov word [input_limit], USER_MAX\n"
                    "    call read_line_limited\n"
                    "    cmp byte [username], 0\n"
                    "    jne .patch_customize_openact_edit_user_done\n"
                    "    mov si, default_user\n"
                    "    mov di, username\n"
                    "    call copy_string\n"
                    ".patch_customize_openact_edit_user_done:\n"
                    "    mov byte [user_initialized], 1\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_edit_readme:\n"
                    "    call clear_screen\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, msg_openact_enter_readme\n"
                    "    call print_color_string\n"
                    "    mov di, fs_readme\n"
                    "    mov word [input_limit], FS_TEXT_MAX\n"
                    "    call read_line_limited\n"
                    "    cmp byte [fs_readme], 0\n"
                    "    jne .patch_customize_openact_redraw\n"
                    "    mov si, fs_readme_default\n"
                    "    mov di, fs_readme\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_edit_judges:\n"
                    "    call clear_screen\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, msg_openact_enter_judges\n"
                    "    call print_color_string\n"
                    "    mov di, fs_judges\n"
                    "    mov word [input_limit], FS_TEXT_MAX\n"
                    "    call read_line_limited\n"
                    "    cmp byte [fs_judges], 0\n"
                    "    jne .patch_customize_openact_redraw\n"
                    "    mov si, fs_judges_default\n"
                    "    mov di, fs_judges\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_edit_unknown:\n"
                    "    call clear_screen\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, msg_openact_enter_unknown\n"
                    "    call print_color_string\n"
                    "    mov di, msg_unknown\n"
                    "    mov word [input_limit], 63\n"
                    "    call read_line_limited\n"
                    "    cmp byte [msg_unknown], 0\n"
                    "    jne .patch_customize_openact_redraw\n"
                    "    mov si, msg_atbman_unknown_fallback\n"
                    "    mov di, msg_unknown\n"
                    "    mov cx, 63\n"
                    "    call copy_string_limited\n"
                    "    jmp .patch_customize_openact_redraw\n"
                    ".patch_customize_openact_reset_profile:\n"
                    "    call .patch_customize_apply_cscript_profile\n"
                    "    mov si, fs_readme_default\n"
                    "    mov di, fs_readme\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    mov si, fs_judges_default\n"
                    "    mov di, fs_judges\n"
                    "    mov cx, FS_TEXT_MAX\n"
                    "    call copy_string_limited\n"
                    "    mov si, msg_atbman_unknown_fallback\n"
                    "    mov di, msg_unknown\n"
                    "    mov cx, 63\n"
                    "    call copy_string_limited\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_reset_done\n"
                    "    call print_color_string\n"
                    "    jmp .patch_customize_openact_wait_key\n"
                    ".patch_customize_openact_save_exit:\n"
                    "    call fs_store_save\n"
                    "    call clear_screen\n"
                    "    call show_banner\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_openact_saved\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_openact_print_theme:\n"
                    "    mov al, [cfg_theme_index]\n"
                    "    cmp al, 0\n"
                    "    je .patch_customize_openact_theme0\n"
                    "    cmp al, 1\n"
                    "    je .patch_customize_openact_theme1\n"
                    "    mov si, msg_openact_theme_amber\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_openact_theme0:\n"
                    "    mov si, msg_openact_theme_classic\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_openact_theme1:\n"
                    "    mov si, msg_openact_theme_ice\n"
                    "    call print_color_string\n"
                    "    ret\n"
                    ".patch_customize_dispatch_continue:"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_FS_LIST",
                snippet=(
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, fs_entry_cscript\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, fs_entry_custom_yaml\n"
                    "    call print_color_string\n"
                    "    cmp byte [atb_pkg1_name], 0\n"
                    "    je .patch_customize_ls_slot2\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, msg_atbman_ls_dash\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    ".patch_customize_ls_slot2:\n"
                    "    cmp byte [atb_pkg2_name], 0\n"
                    "    je .patch_customize_ls_slot3\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, msg_atbman_ls_dash\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    ".patch_customize_ls_slot3:\n"
                    "    cmp byte [atb_pkg3_name], 0\n"
                    "    je .patch_customize_ls_done\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, msg_atbman_ls_dash\n"
                    "    call print_color_string\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    ".patch_customize_ls_done:"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_FS_CAT",
                snippet=(
                    "    mov di, fs_name_cscript\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cat_cscript\n"
                    "    mov di, fs_name_custom_yaml\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cat_yaml\n"
                    "    mov di, atb_pkg1_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cat_pkg1\n"
                    "    mov di, atb_pkg2_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cat_pkg2\n"
                    "    mov di, atb_pkg3_name\n"
                    "    call strcmp\n"
                    "    cmp ax, 1\n"
                    "    je .patch_customize_cat_pkg3\n"
                    "    jmp .patch_customize_cat_done\n"
                    ".patch_customize_cat_cscript:\n"
                    "    mov bl, [cfg_color_ascii]\n"
                    "    mov si, c_atb_script_view\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_yaml:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, customization_yaml_view\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg1:\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_cat_pkg1_meta\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, di\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg1_meta:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_cat_pkg_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg1_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg2:\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_cat_pkg2_meta\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, di\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg2_meta:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_cat_pkg_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg2_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg3:\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call fs_user_find_by_name\n"
                    "    cmp ax, 1\n"
                    "    jne .patch_customize_cat_pkg3_meta\n"
                    "    mov bl, [cfg_color_accent]\n"
                    "    mov si, di\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_pkg3_meta:\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_cat_pkg_prefix\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_name\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_info]\n"
                    "    mov si, msg_atbman_exec_from\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_prompt]\n"
                    "    mov si, atb_pkg3_source\n"
                    "    call print_color_string\n"
                    "    mov bl, [cfg_color_default]\n"
                    "    mov si, msg_newline\n"
                    "    call print_color_string\n"
                    "    mov ax, 1\n"
                    "    ret\n"
                    ".patch_customize_cat_done:"
                ),
            ),
            PatchAction(
                file="src/kernel/kernel.asm",
                marker="; OATB_PATCH_KERNEL_DATA",
                snippet=(
                    'cmd_atbman db "atbman", 0\n'
                    'cmd_cp db "cp", 0\n'
                    'cmd_mv db "mv", 0\n'
                    'arg_dash_i db "-i", 0\n'
                    'arg_dash_u db "-u", 0\n'
                    'arg_dash_l db "-l", 0\n'
                    'arg_dash_e db "-e", 0\n'
                    'arg_dash_dash_exec db "--exec", 0\n'
                    'arg_dash_dash_install db "--install", 0\n'
                    'arg_dash_dash_uninstall db "--uninstall", 0\n'
                    'arg_dash_dash_list db "--list", 0\n'
                    'fs_name_cscript db "c.atb", 0\n'
                    'fs_name_custom_yaml db "customization.yaml", 0\n'
                    'fs_entry_cscript db " - c.atb", 13, 10, 0\n'
                    'fs_entry_custom_yaml db " - customization.yaml", 13, 10, 0\n'
                    'cscript_enabled db 0\n'
                    'atb_source_default db "manual://local", 0\n'
                    'atb_source_core db "core://openatb", 0\n'
                    'atb_source_local db "local://openasm-fs", 0\n'
                    'msg_atbman_ls_dash db " - ", 0\n'
                    'msg_atbman_usage db "atbman: -e/-i/-u/-l | devkit: run/menu/fs", 13, 10, 0\n'
                    'msg_fs_copy_usage db "Usage: cp <src> <dst>", 13, 10, 0\n'
                    'msg_fs_move_usage db "Usage: mv <src> <dst>", 13, 10, 0\n'
                    'msg_fs_copy_ok db "OpenASM-FS: copy done.", 13, 10, 0\n'
                    'msg_fs_move_ok db "OpenASM-FS: move done.", 13, 10, 0\n'
                    'msg_atbman_exec_prefix db "[atbman] running ", 0\n'
                    'msg_atbman_exec_from db " from ", 0\n'
                    'msg_atbman_runtime_prefix db " runtime: ", 0\n'
                    'msg_atbman_exec_done db "[atbman] program finished.", 13, 10, 0\n'
                    'msg_atbman_exec_missing_prefix db "[atbman] package not installed: ", 0\n'
                    'msg_atbman_exec_cscript db "[atbman] launching OpenACT from c.atb...", 13, 10, 0\n'
                    'msg_atbman_runtime_python_hint db " [bridge] install python: oatb app install python.", 13, 10, 0\n'
                    'msg_atbman_runtime_c_hint db " [bridge] c runtime uses host toolchain.", 13, 10, 0\n'
                    'msg_atb_run_host_prefix db " [bridge] host runtime: ", 0\n'
                    'msg_atb_run_host_cmd db " :: cmd=", 0\n'
                    'msg_atb_menu_frame db "+------------------------------------------------+", 13, 10, 0\n'
                    'msg_atb_menu_item_prefix db " - ", 0\n'
                    'msg_atb_menu_prompt db "menu> ", 0\n'
                    'msg_atbman_install_ok_prefix db "[atbman] installed ", 0\n'
                    'msg_atbman_install_from db " from ", 0\n'
                    'msg_atbman_install_runtime db " runtime=", 0\n'
                    'msg_atbman_install_exists_prefix db "[atbman] already installed: ", 0\n'
                    'msg_atbman_install_full db "[atbman] registry full (max 3 user packages).", 13, 10, 0\n'
                    'msg_atbman_uninstall_ok_prefix db "[atbman] removed ", 0\n'
                    'msg_atbman_uninstall_missing_prefix db "[atbman] not installed: ", 0\n'
                    'msg_atbman_core_present db "[atbman] c.atb is core and ready.", 13, 10, 0\n'
                    'msg_atbman_core_protected db "[atbman] c.atb is core (protected).", 13, 10, 0\n'
                    'msg_atbman_unknown_fallback db "Unknown command. Type help.", 0\n'
                    'msg_atbman_cat_pkg_prefix db "[atbman] package: ", 0\n'
                    'msg_atbman_list_title db "[atbman registry]", 13, 10, 0\n'
                    'msg_atbman_list_sep db " <- ", 0\n'
                    'msg_atbman_list_runtime_sep db " :: ", 0\n'
                    'msg_atbman_list_none db " (no user-installed packages)", 13, 10, 0\n'
                    'runtime_atbdevkit db "atbdevkit", 0\n'
                    'runtime_python db "python", 0\n'
                    'runtime_python3 db "python3", 0\n'
                    'runtime_c db "c", 0\n'
                    'runtime_generic db "native", 0\n'
                    'atb_devkit_cmd_func db "func ", 0\n'
                    'atb_devkit_cmd_else db "else", 0\n'
                    'atb_devkit_cmd_if db "if ", 0\n'
                    'atb_devkit_cmd_output1 db "oatb.system.output => ", 0\n'
                    'atb_devkit_cmd_output2 db "output() => ", 0\n'
                    'atb_devkit_cmd_output3 db "output(", 0\n'
                    'atb_devkit_cmd_run1 db "oatb.system.run => ", 0\n'
                    'atb_devkit_cmd_run2 db "oatb.system.run(", 0\n'
                    'atb_devkit_cmd_clear db "oatb.system.clear", 0\n'
                    'atb_devkit_cmd_menu_title db "oatb.menu.title => ", 0\n'
                    'atb_devkit_cmd_menu_item db "oatb.menu.item => ", 0\n'
                    'atb_devkit_cmd_menu_input db "oatb.menu.input => ", 0\n'
                    'atb_devkit_cmd_var db "var ", 0\n'
                    'atb_devkit_cmd_write db "oatb.fs.write => ", 0\n'
                    'atb_devkit_cmd_copy db "oatb.fs.copy => ", 0\n'
                    'atb_devkit_cmd_move db "oatb.fs.move => ", 0\n'
                    'atb_devkit_cmd_append db "oatb.fs.append => ", 0\n'
                    'atb_devkit_cmd_read db "oatb.fs.read => ", 0\n'
                    'atb_devkit_expr_input db "input()", 0\n'
                    'atb_name_a db "a", 0\n'
                    'atb_name_b db "b", 0\n'
                    'atb_name_user_choice db "user_choice", 0\n'
                    'c_atb_script_view db "<c.atb :: OpenACT>", 13, 10, "author :: Roman Masovskiy", 13, 10, "mode :: full-customize", 13, 10, "oatb.system.clear", 13, 10, "oatb.ui.open => openact", 13, 10, 0\n'
                    'customization_yaml_view db "version: 1", 13, 10, "profile: default", 13, 10, "theme: classic", 13, 10, "menu: OpenACT", 13, 10, 0\n'
                    'msg_openact_title db "[OpenACT]", 13, 10, 0\n'
                    'msg_openact_credit db " Credits: Roman Masovskiy", 13, 10, 0\n'
                    'msg_openact_banner db " 1) Banner        : ", 0\n'
                    'msg_openact_theme db " 2) Color theme   : ", 0\n'
                    'msg_openact_prompt db " 3) Prompt mode   : ", 0\n'
                    'msg_openact_user db " 4) Username      : ", 0\n'
                    'msg_openact_opt_readme db " 5) Edit readme.txt", 13, 10, 0\n'
                    'msg_openact_opt_judges db " 6) Edit judges.txt", 13, 10, 0\n'
                    'msg_openact_opt_unknown db " 7) Edit unknown msg", 13, 10, 0\n'
                    'msg_openact_keys db " Keys: 1-7, R reset, S save", 13, 10, 0\n'
                    'msg_openact_on db "on", 0\n'
                    'msg_openact_off db "off", 0\n'
                    'msg_openact_theme_classic db "classic", 0\n'
                    'msg_openact_theme_ice db "ice", 0\n'
                    'msg_openact_theme_amber db "amber", 0\n'
                    'msg_openact_prompt_classic db "classic", 0\n'
                    'msg_openact_prompt_compact db "compact", 0\n'
                    'msg_openact_enter_user db "OpenACT> set username (empty=guest): ", 0\n'
                    'msg_openact_enter_readme db "OpenACT> readme.txt text: ", 0\n'
                    'msg_openact_enter_judges db "OpenACT> judges.txt text: ", 0\n'
                    'msg_openact_enter_unknown db "OpenACT> unknown-command text: ", 0\n'
                    'msg_openact_saved db "[OpenACT] settings applied.", 13, 10, 0\n'
                    'msg_openact_reset_done db "[OpenACT] c.atb profile restored.", 13, 10, 0\n'
                    'atb_fsop_mode db 0\n'
                    'atb_exec_src_ptr dw 0\n'
                    'atb_quote_state db 0\n'
                    'atb_line_buf times FS_TEXT_MAX + 1 db 0\n'
                    'atb_exec_buf times FS_TEXT_MAX + 1 db 0\n'
                    'atb_tmp_token times 33 db 0\n'
                    'atb_if_left times 33 db 0\n'
                    'atb_if_rhs dw 0\n'
                    'atb_if_pending db 0\n'
                    'atb_if_result db 0\n'
                    'atb_int_a dw 0\n'
                    'atb_int_b dw 0\n'
                    'atb_int_user_choice dw 0\n'
                    'atb_var_name times 33 db 0\n'
                    'atb_var_value times FS_TEXT_MAX + 1 db 0\n'
                    'atb_arg_name times 33 db 0\n'
                    'atb_arg_source times 65 db 0\n'
                    'atb_arg_runtime times 16 db 0\n'
                    'atb_pkg1_name times 33 db 0\n'
                    'atb_pkg1_source times 65 db 0\n'
                    'atb_pkg1_runtime times 16 db 0\n'
                    'atb_pkg2_name times 33 db 0\n'
                    'atb_pkg2_source times 65 db 0\n'
                    'atb_pkg2_runtime times 16 db 0\n'
                    'atb_pkg3_name times 33 db 0\n'
                    'atb_pkg3_source times 65 db 0\n'
                    'atb_pkg3_runtime times 16 db 0'
                ),
            ),
            PatchAction(
                file="src/commands/commands.map",
                marker="# command | description | source",
                snippet=(
                    "atbman | .atb manager (local + installed: `-e`, `-i`, `-u`, `-l`), OpenACT via c.atb | src/kernel/kernel.asm\n"
                    "cp | copy file in OpenASM-FS (customize patch) | src/kernel/kernel.asm\n"
                    "mv | move file in OpenASM-FS (customize patch) | src/kernel/kernel.asm"
                ),
            ),
        ),
        created_files=(
            ("c.atb", customization_script_template()),
            ("customization.yaml", customization_yaml_template()),
        ),
    ),
}


def create_project(project_root: Path, project_name: str, *, force: bool = False) -> None:
    if project_root.exists() and any(project_root.iterdir()) and not force:
        raise FileExistsError(
            f"Directory is not empty: {project_root}. Use --force to overwrite managed files."
        )
    project_root.mkdir(parents=True, exist_ok=True)

    files_to_write: list[tuple[Path, str]] = [
        (project_root / PROJECT_SENTINEL, sentinel_template(project_name)),
        (project_root / "README.md", project_readme_template(project_name)),
        (project_root / "Makefile", makefile_template()),
        (project_root / "scripts" / "build.sh", build_script_template()),
        (project_root / "scripts" / "run.sh", run_script_template()),
        (project_root / "scripts" / "flash.sh", flash_script_template()),
        (project_root / "scripts" / "build.py", build_python_template()),
        (project_root / "scripts" / "run.py", run_python_template()),
        (project_root / "scripts" / "flash.py", flash_python_template()),
        (project_root / "src" / "boot" / "boot.asm", boot_asm_template(project_name)),
        (project_root / "src" / "kernel" / "kernel.asm", kernel_asm_template()),
        (project_root / "src" / "commands" / "commands.map", commands_map_template()),
        (
            project_root / "src" / "commands" / "hello.asm",
            command_template("hello", "Simple greeting command template."),
        ),
    ]

    for path, content in files_to_write:
        write_text(path, content, force=force)

    # Base runtime: install atbman by default without enabling c.atb/OpenACT files.
    # Action indexes from `customize` patch:
    # 1 -> command dispatcher/runtime logic
    # 4 -> kernel data/constants for atbman
    # 5 -> commands.map entry
    apply_patch_actions_subset(project_root, "customize", (1, 4, 5))

    for script_name in ("build.sh", "run.sh", "flash.sh", "build.py", "run.py", "flash.py"):
        script_path = project_root / "scripts" / script_name
        script_path.chmod(script_path.stat().st_mode | 0o111)


def sync_kernel_sector_constants(project_root: Path) -> int:
    replacements = 0

    boot_path = project_root / "src" / "boot" / "boot.asm"
    if boot_path.exists():
        original = boot_path.read_text(encoding="utf-8")
        updated, count = re.subn(
            r"(?m)^KERNEL_SECTORS\s+equ\s+\d+\s*$",
            f"KERNEL_SECTORS equ {KERNEL_SECTORS}",
            original,
            count=1,
        )
        if count and updated != original:
            boot_path.write_text(updated, encoding="utf-8")
            replacements += 1

    build_path = project_root / "scripts" / "build.py"
    if build_path.exists():
        original = build_path.read_text(encoding="utf-8")
        updated, count = re.subn(
            r"(?m)^KERNEL_SECTORS = \d+\s*$",
            f"KERNEL_SECTORS = {KERNEL_SECTORS}",
            original,
            count=1,
        )
        if count and updated != original:
            build_path.write_text(updated, encoding="utf-8")
            replacements += 1

    run_path = project_root / "scripts" / "run.py"
    if run_path.exists():
        original = run_path.read_text(encoding="utf-8")
        needs_runtime_sync = (
            "subprocess.run([sys.executable, str(build_script)], check=True)" in original
            and "--rebuild" not in original
        )
        if needs_runtime_sync:
            run_path.write_text(run_python_template(), encoding="utf-8")
            run_path.chmod(run_path.stat().st_mode | 0o111)
            replacements += 1

    return replacements


def apply_patch_definition(project_root: Path, patch_name: str) -> tuple[int, int]:
    definition = PATCHES.get(patch_name)
    if definition is None:
        known = ", ".join(sorted(PATCHES))
        raise ValueError(f"Unknown patch '{patch_name}'. Available: {known}")

    changed = 0
    skipped = 0

    for idx, action in enumerate(definition.actions):
        target = project_root / action.file
        if not target.exists():
            raise FileNotFoundError(f"Patch target file not found: {target}")

        original = target.read_text(encoding="utf-8")
        guard_token = f"OATB_PATCH_APPLIED_{patch_name}_{idx}"
        if guard_token in original:
            skipped += 1
            continue
        if action.snippet in original:
            skipped += 1
            continue
        if action.marker not in original:
            raise ValueError(f"Marker '{action.marker}' not found in {target}")

        comment_prefix = ";" if target.suffix.lower() == ".asm" else "#"
        guard_line = f"{comment_prefix} {guard_token}"
        updated = original.replace(
            action.marker,
            f"{action.marker}\n{guard_line}\n{action.snippet}",
            1,
        )
        target.write_text(updated, encoding="utf-8")
        changed += 1

    for relative_path, content in definition.created_files:
        target = project_root / relative_path
        if target.exists():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changed += 1

    return changed, skipped


def apply_patch_actions_subset(
    project_root: Path, patch_name: str, action_indexes: tuple[int, ...]
) -> tuple[int, int]:
    definition = PATCHES.get(patch_name)
    if definition is None:
        known = ", ".join(sorted(PATCHES))
        raise ValueError(f"Unknown patch '{patch_name}'. Available: {known}")

    changed = 0
    skipped = 0

    for idx in action_indexes:
        if idx < 0 or idx >= len(definition.actions):
            raise IndexError(f"Action index out of range for patch '{patch_name}': {idx}")
        action = definition.actions[idx]
        target = project_root / action.file
        if not target.exists():
            raise FileNotFoundError(f"Patch target file not found: {target}")

        original = target.read_text(encoding="utf-8")
        guard_token = f"OATB_PATCH_APPLIED_{patch_name}_{idx}"
        if guard_token in original:
            skipped += 1
            continue
        if action.snippet in original:
            skipped += 1
            continue
        if action.marker not in original:
            raise ValueError(f"Marker '{action.marker}' not found in {target}")

        comment_prefix = ";" if target.suffix.lower() == ".asm" else "#"
        guard_line = f"{comment_prefix} {guard_token}"
        updated = original.replace(
            action.marker,
            f"{action.marker}\n{guard_line}\n{action.snippet}",
            1,
        )
        target.write_text(updated, encoding="utf-8")
        changed += 1

    return changed, skipped


def cmd_app_managers(_: argparse.Namespace) -> int:
    detected = detect_package_managers()
    if detected:
        print("Detected package managers:")
        for manager in detected:
            print(f"- {manager}")
    else:
        print("No supported package managers detected.")
    return 0


def cmd_app_list(_: argparse.Namespace) -> int:
    print("Built-in app catalog:")
    for app_name in sorted(HOST_APP_CATALOG):
        record = HOST_APP_CATALOG[app_name]
        binaries = tuple(record["check_bins"])
        installed_path = first_installed_path(binaries)
        state = "installed" if installed_path else "not installed"
        print(f"- {app_name}: {record['description']} [{state}]")
        if installed_path:
            print(f"  path: {installed_path}")
    return 0


def cmd_app_install(args: argparse.Namespace) -> int:
    manager = resolve_package_manager(args.manager)
    app_name, record, known_app = resolve_app_record(args.app)

    package_name = args.package
    if not package_name:
        packages = dict(record["packages"])
        package_name = packages.get(manager)

    if not package_name:
        raise RuntimeError(
            f"App '{app_name}' has no package mapping for '{manager}'. "
            "Use --package to provide an explicit package name."
        )

    check_bins = tuple(record["check_bins"])
    existing = first_installed_path(check_bins)
    if existing:
        print(f"[ok] '{app_name}' is already installed at: {existing}")
        return 0

    if not known_app:
        print(f"[info] Installing custom package: {app_name}")

    print(f"[info] Installing '{app_name}' using '{manager}' as package '{package_name}'")
    commands = build_install_commands(
        manager,
        package_name,
        use_sudo=(not args.no_sudo),
        yes=args.yes,
        update_index=args.update_index,
    )
    run_install_commands(commands, dry_run=args.dry_run)

    if args.dry_run:
        print("[ok] Dry-run complete.")
        return 0

    installed = first_installed_path(check_bins)
    if installed:
        print(f"[ok] Installed '{app_name}': {installed}")
    else:
        print(
            "[warn] Install command finished, but binary wasn't found in PATH yet. "
            "Open a new terminal session or check your package manager output."
        )
    return 0


def cmd_new_os(args: argparse.Namespace) -> int:
    raw_name = args.name.strip()
    explicit_path = Path(raw_name).expanduser()
    if explicit_path.is_absolute() or explicit_path.parent != Path("."):
        project_dir = explicit_path.resolve()
        project_name = safe_identifier(project_dir.name)
    else:
        target_root = Path(args.output).expanduser().resolve()
        project_name = safe_identifier(raw_name)
        project_dir = target_root / project_name
    create_project(project_dir, project_name, force=args.force)
    print(f"[ok] Project generated at: {project_dir}")
    print("Next: cd into project and run python3 ./scripts/build.py")
    return 0


def cmd_new_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project).expanduser().resolve()
    ensure_project(project_root)

    command_name = safe_identifier(args.name)
    command_path = project_root / "src" / "commands" / f"{command_name}.asm"
    write_text(
        command_path,
        command_template(command_name, args.description),
        force=args.force,
    )

    map_file = project_root / "src" / "commands" / "commands.map"
    entry = f"{command_name} | {args.description} | src/commands/{command_name}.asm"
    append_unique_line(map_file, entry)

    print(f"[ok] Command template created: {command_path}")
    print("[info] Added to commands.map. Wire handler into src/kernel/kernel.asm dispatch logic.")
    return 0


def cmd_new_template(args: argparse.Namespace) -> int:
    output_path = Path(args.output).expanduser().resolve()
    template_type = args.template_type.strip().lower()
    template_aliases = {
        "boot-sector": "boot-sector",
        "asm-command": "asm-command",
        "command": "asm-command",
        "patch-note": "patch-note",
    }
    template_kind = template_aliases.get(template_type)

    if template_kind == "boot-sector":
        content = boot_asm_template(args.name)
    elif template_kind == "asm-command":
        content = command_template(args.name, args.description)
    elif template_kind == "patch-note":
        content = patch_note_template()
    else:
        raise ValueError(
            "Unsupported template type. Use: boot-sector, asm-command, patch-note."
        )

    write_text(output_path, content, force=args.force)
    print(f"[ok] Template written: {output_path}")
    return 0


def cmd_patch_list(_: argparse.Namespace) -> int:
    print("Available patches:")
    for patch_name in sorted(PATCHES):
        print(f"- {patch_name}: {PATCHES[patch_name].description}")
    return 0


def cmd_patch_apply(args: argparse.Namespace) -> int:
    project_root = Path(args.project).expanduser().resolve()
    ensure_project(project_root)
    sync_changed = sync_kernel_sector_constants(project_root)
    patch_aliases = {
        "hackathon": "hackathon-demo",
        "hints": "command-hints",
        "retro": "retro-banner",
        "custom": "customize",
    }
    patch_name = patch_aliases.get(args.patch_name, args.patch_name)
    changed, skipped = apply_patch_definition(project_root, patch_name)
    if sync_changed:
        print(f"[ok] Boot/kernel sector config synced (updated files: {sync_changed})")
    print(f"[ok] Patch '{patch_name}' applied: changed={changed}, skipped={skipped}")
    return 0


def cmd_hackathon_pack(args: argparse.Namespace) -> int:
    project_root = Path(args.project).expanduser().resolve()
    ensure_project(project_root)
    sync_changed = sync_kernel_sector_constants(project_root)

    sentinel_data = (project_root / PROJECT_SENTINEL).read_text(encoding="utf-8")
    project_name = "OpenATB Project"
    for line in sentinel_data.splitlines():
        if line.strip().startswith("name = "):
            project_name = line.split("=", 1)[1].strip().strip('"')
            break

    hackathon_dir = project_root / "hackathon"
    write_text(
        hackathon_dir / "PITCH.md",
        hackathon_pitch_template(args.team, project_name),
        force=args.force,
    )
    write_text(
        hackathon_dir / "DEMO_SCRIPT.md",
        hackathon_demo_script_template(),
        force=args.force,
    )
    write_text(
        hackathon_dir / "JUDGE_CHECKLIST.md",
        hackathon_checklist_template(),
        force=args.force,
    )

    total_changed = 0
    total_skipped = 0
    for patch_name in ("retro-banner", "command-hints", "hackathon-demo"):
        changed, skipped = apply_patch_definition(project_root, patch_name)
        total_changed += changed
        total_skipped += skipped

    print(f"[ok] Hackathon pack generated in: {hackathon_dir}")
    if sync_changed:
        print(f"[ok] Boot/kernel sector config synced (updated files: {sync_changed})")
    print(
        f"[ok] Included patches applied (changed={total_changed}, skipped={total_skipped})."
    )
    print("[next] Build/run and type: hackathon, then demo")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oatb",
        description="Open Assembly ToolBox: generator for bootable assembly projects.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    new_os_parser = subparsers.add_parser(
        "new-os",
        help="Create a new bootable assembly project scaffold.",
    )
    new_os_parser.add_argument("name", help="Project name.")
    new_os_parser.add_argument(
        "-o",
        "--output",
        default=".",
        help="Directory where project folder will be created.",
    )
    new_os_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite managed files if they already exist.",
    )
    new_os_parser.set_defaults(func=cmd_new_os)

    new_command_parser = subparsers.add_parser(
        "new-command",
        help="Create a command ASM template inside an existing OpenATB project.",
    )
    new_command_parser.add_argument("project", help="Path to OpenATB project root.")
    new_command_parser.add_argument("name", help="Command name.")
    new_command_parser.add_argument(
        "--description",
        default="Custom command",
        help="Short command description for commands.map.",
    )
    new_command_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite command file if it already exists.",
    )
    new_command_parser.set_defaults(func=cmd_new_command)

    template_parser = subparsers.add_parser(
        "new-template",
        help="Generate a standalone template file.",
    )
    template_parser.add_argument(
        "template_type",
        help="Template type: boot-sector, asm-command, patch-note.",
    )
    template_parser.add_argument("output", help="Output file path.")
    template_parser.add_argument(
        "--name",
        default="sample",
        help="Name used by templates that require an identifier.",
    )
    template_parser.add_argument(
        "--description",
        default="Template-generated command",
        help="Description used by command templates.",
    )
    template_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )
    template_parser.set_defaults(func=cmd_new_template)

    patch_parser = subparsers.add_parser(
        "patch",
        help="List or apply built-in patches.",
    )
    patch_subparsers = patch_parser.add_subparsers(dest="patch_cmd", required=True)

    patch_list_parser = patch_subparsers.add_parser("list", help="List available patches.")
    patch_list_parser.set_defaults(func=cmd_patch_list)

    patch_apply_parser = patch_subparsers.add_parser(
        "apply", help="Apply patch to an existing OpenATB project."
    )
    patch_apply_parser.add_argument("project", help="Path to OpenATB project root.")
    patch_apply_parser.add_argument("patch_name", help="Patch name.")
    patch_apply_parser.set_defaults(func=cmd_patch_apply)

    app_parser = subparsers.add_parser(
        "app",
        help="Install or list third-party host applications for OpenATB workflows.",
    )
    app_subparsers = app_parser.add_subparsers(dest="app_cmd", required=True)

    app_list_parser = app_subparsers.add_parser(
        "list",
        help="List built-in app catalog and install status.",
    )
    app_list_parser.set_defaults(func=cmd_app_list)

    app_managers_parser = app_subparsers.add_parser(
        "managers",
        help="Show detected package managers on this machine.",
    )
    app_managers_parser.set_defaults(func=cmd_app_managers)

    app_install_parser = app_subparsers.add_parser(
        "install",
        help="Install an app from catalog (or custom package name).",
    )
    app_install_parser.add_argument("app", help="App name from catalog or custom package.")
    app_install_parser.add_argument(
        "--manager",
        default="auto",
        choices=("auto", *KNOWN_PACKAGE_MANAGERS),
        help="Package manager to use. Default: auto-detect.",
    )
    app_install_parser.add_argument(
        "--package",
        help="Override package name/id passed to package manager.",
    )
    app_install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print install command(s) without executing.",
    )
    app_install_parser.add_argument(
        "--yes",
        action="store_true",
        help="Use non-interactive flags when supported.",
    )
    app_install_parser.add_argument(
        "--update-index",
        action="store_true",
        help="Update package metadata before install when supported.",
    )
    app_install_parser.add_argument(
        "--no-sudo",
        action="store_true",
        help="Do not prefix linux package manager commands with sudo.",
    )
    app_install_parser.set_defaults(func=cmd_app_install)

    hackathon_parser = subparsers.add_parser(
        "hackathon-pack",
        help="Generate pitch/demo docs and apply hackathon-focused patches.",
    )
    hackathon_parser.add_argument("project", help="Path to OpenATB project root.")
    hackathon_parser.add_argument(
        "--team",
        default="OpenATB Team",
        help="Team name written into the pitch template.",
    )
    hackathon_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite hackathon documents if they already exist.",
    )
    hackathon_parser.set_defaults(func=cmd_hackathon_pack)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
