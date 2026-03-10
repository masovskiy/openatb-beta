# masovskiyos

Generated with Open Assembly ToolBox.

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
  - DevKit runtime supports: `var :: name :: int|str => input()`, `output() => ...`, `output(expr)`, `if ...` + `else => ...`, `oatb.system.output => ...`, `oatb.system.clear`, `oatb.menu.title/item/input => ...`, `oatb.system.run("cmd")`, `oatb.fs.write => "file :: text"`, `oatb.fs.append => "file :: text"`, `oatb.fs.read => "file"`; chain statements with `;`
- after `customize` patch: `c.atb` + `customization.yaml` appear and OpenACT is unlocked

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
