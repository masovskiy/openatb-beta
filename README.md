
# openatb-beta
Beta version of Open Assembly Toolbox
=======
# OpenATB (Open Assembly ToolBox)

`OpenATB` (Open Assembly ToolBox), developed by Roman Masovskiy (Mas0vsk1yy), is an open-source utility for generating and extending a bootable assembly runtime.

Important: this is not a closed product. It is a toolkit and codebase for experimentation, learning, and customization.

## What OpenATB includes

1. `OATB DevKit` (Open Assembly ToolBox Developer Kit)
- A DSL/instruction set for `.atb` programs and scripts.

2. `OpenASM-FS` (Open Assembly FileSystem)
- The runtime filesystem used by OpenATB (sector-backed storage inside the disk image).

3. `OpenACT` (Open Assembly Customization ToolBox)
- A full-screen customization mode launched via `c.atb`.

## What is in this repository

This repository contains the **OpenATB project generator** (`main.py`).

The generator creates a bootable scaffold with:
- `boot.asm` (bootloader),
- `kernel.asm` (shell, OpenASM-FS, commands),
- build/run/flash scripts,
- patch system,
- command templates.

Current tool version: `0.2.0`.

## Generator capabilities

- create a new OpenATB project (`new-os`);
- create a new ASM command template (`new-command`);
- generate standalone templates (`new-template`);
- apply built-in patches (`patch apply`);
- install host applications (`app install`);
- generate hackathon docs and patch set (`hackathon-pack`).

## Requirements

Minimum:
- `python3`
- `nasm`
- `qemu-system-i386` or `qemu-system-x86_64`

For USB flashing:
- Linux/macOS + raw device access (`dd`, root/sudo)

Optional:
- `python`/`python3` for DevKit host-bridge workflows
- C toolchain (`gcc`/`clang`) for `c` bridge commands

## Quick start

```bash
python3 main.py new-os OpenATBOS
cd openatbos
python3 scripts/build.py
python3 scripts/run.py
```

## Generated project structure

```text
<project>/
├── .oatb_project
├── README.md
├── Makefile
├── scripts/
│   ├── build.py
│   ├── run.py
│   ├── flash.py
│   ├── build.sh
│   ├── run.sh
│   └── flash.sh
└── src/
    ├── boot/
    │   └── boot.asm
    ├── kernel/
    │   └── kernel.asm
    └── commands/
        ├── commands.map
        └── hello.asm
```

## Generator CLI (`main.py`)

### 1) Create project

```bash
python3 main.py new-os <name> [-o <dir>] [--force]
```

- If `<name>` is a path, the project is created at that path.
- Otherwise, the name is normalized via `safe_identifier` and created under `--output`.

### 2) Create command template

```bash
python3 main.py new-command <project_path> <command_name> [--description "..."] [--force]
```

- Creates `src/commands/<command_name>.asm`.
- Automatically appends command metadata to `src/commands/commands.map`.

### 3) Create standalone template

```bash
python3 main.py new-template <template_type> <output_file> [--name ...] [--description ...] [--force]
```

Supported `template_type` values:
- `boot-sector`
- `asm-command`
- `command` (alias for `asm-command`)
- `patch-note`

### 4) Patches

```bash
python3 main.py patch list
python3 main.py patch apply <project_path> <patch_name>
```

Available patches:
- `retro-banner`
- `command-hints`
- `hackathon-demo`
- `customize`

Aliases:
- `retro` -> `retro-banner`
- `hints` -> `command-hints`
- `hackathon` -> `hackathon-demo`
- `custom` -> `customize`

Patch status behavior in runtime:
- before enable: `red`
- after apply: `green`

You can see this in `help` and `patches`.

### 5) Host app manager

```bash
python3 main.py app list
python3 main.py app managers
python3 main.py app install <app> [--manager auto|brew|apt-get|dnf|pacman|zypper|apk|winget|choco|scoop] [--package <pkg>] [--dry-run] [--yes] [--update-index] [--no-sudo]
```

Built-in app catalog:
- `python`
- `neofetch`
- `screenfetch`
- `nasm`
- `qemu`

Custom package names are also supported.

### 6) Hackathon pack

```bash
python3 main.py hackathon-pack <project_path> [--team "..."] [--force]
```

Creates:
- `hackathon/PITCH.md`
- `hackathon/DEMO_SCRIPT.md`
- `hackathon/JUDGE_CHECKLIST.md`

And auto-applies:
- `retro-banner`
- `command-hints`
- `hackathon-demo`

## First boot setup wizard

On first boot, the kernel runs a setup wizard:

1. `username` (max 32 chars, empty -> `guest`)
2. `region` (7 choices: Pacific, Eastern, UTC, Central Europe, Moscow, Singapore, Tokyo)
3. `password` (max 32 chars)

Kernel limits:
- `USER_MAX = 32`
- `PASS_MAX = 32`
- `MAX_INPUT = 255`

## Runtime commands (inside OpenATB shell)

### Core commands

| Command | Syntax | Description |
|---|---|---|
| `help` | `help` | help output + patch status colors |
| `about` | `about` | system/about card |
| `clear` | `clear` | clear screen + redraw banner |
| `cls` | `cls` | alias for `clear` |
| `banner` | `banner [clear\|full]` | redraw/control banner mode |
| `patches` | `patches [raw]` | patch state (`raw` prints 0/1) |
| `sys` | `sys <info\|time\|date\|uptime\|version\|fetch\|patches\|banner>` | multi-tool info command |
| `uptime` | `uptime` | session uptime |
| `time` | `time` | RTC time |
| `date` | `date` | RTC date |
| `version` | `version` | runtime version |
| `fetch` | `fetch` | visual runtime card |
| `echo` | `echo [-n\|-u\|-l] <text>` | print text, upper/lower/no-newline variants |
| `exit` | `exit` | exit VM: QEMU debug-exit + ACPI/APM fallback |
| `reboot` | `reboot` | BIOS reboot |

### Profile commands

| Command | Syntax | Description |
|---|---|---|
| `setname` | `setname [<name>\|reset]` | change active name or reset to `guest` |
| `region` | `region [set]` | show/reconfigure region |
| `passwd` | `passwd` | update password |

### OpenASM-FS commands

| Command | Syntax | Description |
|---|---|---|
| `ls` | `ls` | list files/folders |
| `fsls` | `fsls` | alias for `ls` |
| `cd` | `cd [folder\|/\|..]` | change folder |
| `fsinfo` | `fsinfo` | filesystem summary |
| `touch` | `touch <file.ext>` | create file |
| `mk` | `mk <file.ext>` | alias for `touch` |
| `mkdir` | `mkdir <folder>` | create folder |
| `rmdir` | `rmdir <folder>` | remove empty folder |
| `write` | `write <file> <text>` | overwrite file |
| `fswrite` | `fswrite <file> <text>` | alias for `write` |
| `append` | `append <file> <text>` | append to file |
| `cat` | `cat <file>` | print file contents |
| `nano` | `nano <file>` | built-in full-screen editor |
| `rm` | `rm <file>` | permanent delete (no trash) |

### `nano` details

- full-screen mode (console view is cleared while editing);
- multiline editing;
- commands:
  - `:w` save
  - `:wq` save + exit
  - `:q` exit without save
  - `:h` help
- line limit: `NANO_MAX_LINES = 1000`;
- text size limit: `FS_TEXT_MAX = 3072` bytes per file.

## OpenASM-FS model (current implementation)

Current kernel-level constraints:
- `FS_NAME_MAX = 31`
- `FS_TEXT_MAX = 3072`
- user file slots: 6 (`ufs1..ufs6`)
- one-level folder paths supported (`folder/file.ext`)
- `rmdir` removes only empty folders
- `rm` is file-only (for folders, use `rmdir`)

Storage backend:
- sector-backed store in image (`FS_STORE_LBA = 256`, `FS_STORE_SECTORS = 64`)
- state is saved on `exit` and `reboot`

Persistence note:
- `python3 scripts/run.py` keeps existing `build/openatb.img` state;
- `python3 scripts/run.py --rebuild` rebuilds the image and may reset user state.

## `atbman` and `.atb` apps

`atbman` is present in the base scaffold by default.

Syntax:
- `atbman -e <pkg.atb>` / `atbman --exec <pkg.atb>`
- `atbman -i <pkg.atb> [source] [runtime]` / `--install ...`
- `atbman -u <pkg.atb>` / `--uninstall ...`
- `atbman -l` / `--list`

Current behavior:
- `-e` resolves from installed registry and local OpenASM-FS;
- user registry capacity is limited to 3 package slots;
- package metadata includes `name`, `source`, `runtime`;
- runtime bridge may print lines such as:
  - `[bridge] host runtime: python :: cmd=...`
  - `[bridge] host runtime: c :: cmd=...`

`customize` patch adds:
- `c.atb`
- `customization.yaml`
- OpenACT full-screen mode

## OATB DevKit (currently supported runtime)

### Syntax

- separator: `::`
- assignment/action: `=>`
- comments: `<...>`
- statement chaining: `;`

### Supported constructs

1. Output:
- `oatb.system.output => "text"`
- `output() => "text"`
- `output(expr)`

2. Variables:
- `var name :: str => "..."`
- `var :: a :: int => input()`
- `var :: user_choice :: str => input()`

3. Conditions:
- `if <lhs> == <rhs> => <inline_stmt>`
- `else => <inline_stmt>`

4. System/menu actions:
- `oatb.system.clear`
- `oatb.system.run => "cmd ..."`
- `oatb.system.run("cmd ...")`
- `oatb.menu.title => "..."`
- `oatb.menu.item => "..."`
- `oatb.menu.input => var_name`

5. File writes:
- `oatb.fs.write => "file.ext :: content"`

### Minimal Hello World

```text
oatb.system.output => "hello world!"
```

### Minimal menu + host bridge

```text
oatb.system.clear
oatb.menu.title => "Demo"
oatb.menu.item => "1) Python bridge"
oatb.menu.item => "2) Skip"
oatb.menu.input => user_choice
if user_choice == 1 => oatb.system.run("python3 app.py")
else => output() => "Skipped"
```

## `customize` patch in detail

After `patch apply <project> customize`:
- OpenACT is unlocked (`atbman -e c.atb`);
- `c.atb` and `customization.yaml` are created;
- `.atb` execution/runtime path is expanded;
- runtime bridge behavior is extended;
- `commands.map` gains an `atbman` entry.

## Build, run, flash

### Build

```bash
python3 scripts/build.py
```

### Run

```bash
# run without rebuild (keep current image state)
python3 scripts/run.py

# run with forced rebuild
python3 scripts/run.py --rebuild
```

### USB flash (destructive)

Linux:

```bash
sudo python3 scripts/flash.py --device /dev/sdX --yes
```

macOS:

```bash
sudo python3 scripts/flash.py --device /dev/diskN --yes
```

Windows:
- direct raw flashing is not implemented in `flash.py`;
- use Rufus or balenaEtcher with `build/openatb.img`.

## Troubleshooting

1. `python3 ../main.py ...` fails with `FileNotFoundError`.
- Use an up-to-date version that includes `_sanitize_bootstrap_sys_path()`.
- Recommended invocation: run from repo root or use an absolute path to `main.py`.

2. State resets after reboot.
- Verify you are not using `--rebuild`.
- Use plain `python3 scripts/run.py` to preserve current image state.

3. Bootloader freeze.
- Re-apply a patch (this also syncs boot/kernel sector constants) and rebuild:

```bash
python3 main.py patch apply . command-hints
python3 scripts/build.py
```

4. `atbman -e file.atb` does not run as expected.
- Confirm the file exists in `ls`.
- Check DevKit syntax (`=>`, not `->`).
- For host runtime commands, expect bridge output instead of native ASM execution.

## Security note

`passwd` is stored in an obfuscated/encrypted runtime form (transform + hex encoding), but this is not a production-grade cryptographic security model.

Do not treat OpenATB as a secure secret vault.

## Authorship

OpenATB is tied to Roman Masovskiy authorship.

Runtime banners/about credits keep author attribution.

