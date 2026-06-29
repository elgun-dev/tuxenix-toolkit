from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dashboard import repo_archives
from .packages import Package


INSTALLER_PROFILES: dict[str, tuple[str, ...]] = {
    "minimal": (
        "glibc",
        "bash",
        "coreutils",
        "grep",
        "sed",
        "gzip",
        "tar",
        "xz",
        "zlib",
        "ncurses",
        "readline",
        "util-linux",
        "systemd",
        "kmod",
        "linux-tuxenix",
        "linux-firmware",
        "txpk",
        "shadow",
        "e2fsprogs",
        "dhcpcd",
        "openssh",
        "iproute2",
        "iputils",
        "procps-ng",
        "iana-etc",
        "kbd",
        "make-ca",
        "resolv-conf",
        "tuxenix-networking",
        "less",
        "vim",
    ),
    "rescue": (
        "minimal",
        "btrfs-progs",
        "dosfstools",
        "efibootmgr",
        "efivar",
        "gptfdisk",
        "grub",
        "grub-efi",
        "lvm2",
        "parted",
        "pciutils",
        "smartmontools",
        "usbutils",
        "wget",
    ),
}


BOOTLOADER_CHOICES: dict[str, tuple[str, ...]] = {
    "none": (),
    "grub-bios": ("grub",),
    "grub-efi": ("grub-efi",),
    "limine": ("limine",),
}


@dataclass(frozen=True)
class InstallerEntry:
    package: Package
    archive: Path


@dataclass(frozen=True)
class InstallerPlan:
    entries: tuple[InstallerEntry, ...]
    requested: tuple[str, ...]
    missing_recipes: tuple[str, ...]
    missing_archives: tuple[str, ...]
    skipped_packages: tuple[str, ...]


def expand_profile(name: str) -> tuple[str, ...]:
    if name not in INSTALLER_PROFILES:
        raise ValueError(f"unknown installer profile: {name}")

    expanded: list[str] = []
    for item in INSTALLER_PROFILES[name]:
        if item in INSTALLER_PROFILES:
            expanded.extend(expand_profile(item))
        else:
            expanded.append(item)
    return tuple(dict.fromkeys(expanded))


def archive_for_package(repo_root: Path, package: Package) -> Path | None:
    archives = package.dist_archives or repo_archives(repo_root, package)
    if not archives:
        return None

    exact = [path for path in archives if path.parent.name == package.version]
    return sorted(exact or archives)[-1]


def build_installer_plan(
    packages: dict[str, Package],
    repo_root: Path,
    profile: str,
    extra_packages: tuple[str, ...] = (),
    bootloaders: tuple[str, ...] = (),
    skip_missing: bool = False,
) -> InstallerPlan:
    bootloader_packages = tuple(
        package
        for bootloader in bootloaders
        for package in BOOTLOADER_CHOICES[bootloader]
    )
    requested = tuple(dict.fromkeys((*expand_profile(profile), *extra_packages, *bootloader_packages)))
    missing_recipes: list[str] = []
    missing_archives: list[str] = []
    ordered: list[Package] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError(f"dependency cycle includes {name}")

        package = packages.get(name)
        if package is None:
            missing_recipes.append(name)
            return

        visiting.add(name)
        for dependency in package.depends:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(package)

    for name in requested:
        visit(name)

    archive_map: dict[str, Path] = {}
    for package in ordered:
        archive = archive_for_package(repo_root, package)
        if archive is None:
            missing_archives.append(package.name)
            continue
        archive_map[package.name] = archive

    entries: list[InstallerEntry] = []
    skipped_packages: list[str] = []
    installable_names: set[str] = set()
    for package in ordered:
        archive = archive_map.get(package.name)
        if archive is None:
            if skip_missing:
                skipped_packages.append(package.name)
            continue

        missing_dependencies = [
            dependency
            for dependency in package.depends
            if dependency in packages and dependency not in installable_names
        ]
        if skip_missing and missing_dependencies:
            skipped_packages.append(package.name)
            continue

        entries.append(InstallerEntry(package, archive))
        installable_names.add(package.name)

    return InstallerPlan(
        entries=tuple(entries),
        requested=requested,
        missing_recipes=tuple(dict.fromkeys(missing_recipes)),
        missing_archives=tuple(dict.fromkeys(missing_archives)),
        skipped_packages=tuple(dict.fromkeys(skipped_packages)),
    )


def sh_quote(value: str | Path) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def write_installer_script(
    plan: InstallerPlan,
    output: Path,
    target_root: Path,
    txpk_config: Path,
    bootloader: str,
) -> None:
    install_lines = "\n".join(
        "install_package "
        f"{sh_quote(entry.package.name)} "
        f"{sh_quote(entry.package.version)} "
        f"{sh_quote(entry.archive.resolve())}"
        for entry in plan.entries
    )

    script = f"""#!/bin/sh
set -eu

# Generated by tuxenix-toolkit. This installs a Tuxenix root filesystem from
# local txpk archives; it does not partition disks or install a bootloader.

TARGET_ROOT={sh_quote(target_root)}
DEFAULT_TXPK_CONFIG={sh_quote(txpk_config)}
TXPK_CONFIG="${{TXPK_CONFIG:-$DEFAULT_TXPK_CONFIG}}"
TXPK_BIN="${{TXPK_BIN:-txpk}}"
BOOTLOADER={sh_quote(bootloader)}
BOOT_DISK=""
BOOT_MODE="efi"
EFI_DIRECTORY="/boot/efi"
DISK=""
PARTITION_MODE="manual"
FILESYSTEM="ext4"
SWAP_MODE="none"
ROOT_PARTITION=""
EFI_PARTITION=""
APPLY_DISK_LAYOUT=0
DRY_RUN=0
YES=0

usage() {{
    cat <<'USAGE'
Usage: tuxenix-install-rootfs.sh [options]

Options:
  --target-root <dir>  Install into this mounted root filesystem.
  --config <dir>       txpk config directory. Defaults to TXPK_CONFIG or generator default.
  --txpk-bin <path>    txpk binary. Defaults to TXPK_BIN or txpk.
  --bootloader <name>  none, grub-bios, grub-efi, limine, or ask.
  --boot-mode <name>   efi or bios. Defaults to efi.
  --boot-disk <dev>    Target disk for BIOS bootloader commands, such as /dev/sda.
  --efi-directory <p>  EFI mount path inside target root. Defaults to /boot/efi.
  --disk <dev>         Disk for automatic partitioning, such as /dev/sda.
  --partition-mode <m> manual or auto. Defaults to manual.
  --filesystem <fs>    ext4 or btrfs. Defaults to ext4.
  --swap <mode>        none or swapfile. Defaults to none.
  --apply-disk-layout  Allow partitioning/formatting/mounting the selected disk.
  --dry-run            Print commands without changing the target root.
  --yes                Do not ask for confirmation.
  --help               Show this help.
USAGE
}}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --target-root)
            TARGET_ROOT="$2"
            shift 2
            ;;
        --config)
            TXPK_CONFIG="$2"
            shift 2
            ;;
        --txpk-bin)
            TXPK_BIN="$2"
            shift 2
            ;;
        --bootloader)
            BOOTLOADER="$2"
            shift 2
            ;;
        --boot-mode)
            BOOT_MODE="$2"
            shift 2
            ;;
        --boot-disk)
            BOOT_DISK="$2"
            shift 2
            ;;
        --efi-directory)
            EFI_DIRECTORY="$2"
            shift 2
            ;;
        --disk)
            DISK="$2"
            shift 2
            ;;
        --partition-mode)
            PARTITION_MODE="$2"
            shift 2
            ;;
        --filesystem)
            FILESYSTEM="$2"
            shift 2
            ;;
        --swap)
            SWAP_MODE="$2"
            shift 2
            ;;
        --apply-disk-layout)
            APPLY_DISK_LAYOUT=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --yes)
            YES=1
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -z "$TARGET_ROOT" ] || [ "$TARGET_ROOT" = "/" ]; then
    echo "Refusing to install into an empty target root or /." >&2
    exit 1
fi

case "$BOOTLOADER" in
    none|grub-bios|grub-efi|limine|ask) ;;
    *)
        echo "unsupported bootloader: $BOOTLOADER" >&2
        exit 1
        ;;
esac

case "$BOOT_MODE" in
    efi|bios) ;;
    *)
        echo "unsupported boot mode: $BOOT_MODE" >&2
        exit 1
        ;;
esac

case "$PARTITION_MODE" in
    manual|auto) ;;
    *)
        echo "unsupported partition mode: $PARTITION_MODE" >&2
        exit 1
        ;;
esac

case "$FILESYSTEM" in
    ext4|btrfs) ;;
    *)
        echo "unsupported filesystem: $FILESYSTEM" >&2
        exit 1
        ;;
esac

case "$SWAP_MODE" in
    none|swapfile) ;;
    *)
        echo "unsupported swap mode: $SWAP_MODE" >&2
        exit 1
        ;;
esac

if [ "$DRY_RUN" -eq 0 ] && ! command -v "$TXPK_BIN" >/dev/null 2>&1; then
    echo "txpk binary not found: $TXPK_BIN" >&2
    exit 1
fi

echo "Tuxenix rootfs installer"
echo "target root: $TARGET_ROOT"
echo "txpk config: $TXPK_CONFIG"
echo "bootloader: $BOOTLOADER"
echo "boot mode: $BOOT_MODE"
echo "partition mode: $PARTITION_MODE"
echo "filesystem: $FILESYSTEM"
echo "swap: $SWAP_MODE"
echo "packages: {len(plan.entries)}"

if [ "$YES" -eq 0 ]; then
    if command -v lsblk >/dev/null 2>&1; then
        echo
        echo "Current block devices:"
        lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
        echo
    fi

    if [ "$PARTITION_MODE" = "manual" ]; then
        printf 'Partition mode [manual/auto] (manual): '
        read partition_answer
        [ -z "$partition_answer" ] || PARTITION_MODE="$partition_answer"
    fi

    if [ "$PARTITION_MODE" = "auto" ] && [ -z "$DISK" ]; then
        printf 'Disk to erase and install to, for example /dev/sda: '
        read DISK
    fi

    if [ "$FILESYSTEM" = "ext4" ]; then
        printf 'Filesystem [ext4/btrfs] (ext4): '
        read filesystem_answer
        [ -z "$filesystem_answer" ] || FILESYSTEM="$filesystem_answer"
    fi

    if [ "$SWAP_MODE" = "none" ]; then
        printf 'Swap [none/swapfile] (none): '
        read swap_answer
        [ -z "$swap_answer" ] || SWAP_MODE="$swap_answer"
    fi
fi

if [ "$BOOTLOADER" = "ask" ] && [ "$YES" -eq 0 ]; then
    echo "Choose bootloader:"
    echo "  1) none"
    echo "  2) GRUB BIOS"
    echo "  3) GRUB EFI"
    echo "  4) Limine"
    printf 'Bootloader [1-4]: '
    read boot_answer
    case "$boot_answer" in
        2) BOOTLOADER=grub-bios ;;
        3) BOOTLOADER=grub-efi ;;
        4) BOOTLOADER=limine ;;
        *) BOOTLOADER=none ;;
    esac
elif [ "$BOOTLOADER" = "ask" ]; then
    BOOTLOADER=none
fi

case "$PARTITION_MODE" in manual|auto) ;; *) echo "unsupported partition mode after prompt: $PARTITION_MODE" >&2; exit 1 ;; esac
case "$FILESYSTEM" in ext4|btrfs) ;; *) echo "unsupported filesystem after prompt: $FILESYSTEM" >&2; exit 1 ;; esac
case "$SWAP_MODE" in none|swapfile) ;; *) echo "unsupported swap mode after prompt: $SWAP_MODE" >&2; exit 1 ;; esac

if [ "$YES" -eq 0 ]; then
    if [ "$PARTITION_MODE" = "auto" ]; then
        echo
        echo "WARNING: automatic partitioning will erase $DISK when --apply-disk-layout is used."
        echo "Without --apply-disk-layout this script prints the disk commands and exits before installing."
    fi
    printf 'Continue installing into %s? [y/N] ' "$TARGET_ROOT"
    read answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) echo "aborted"; exit 1 ;;
    esac
fi

run() {{
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '+'
        printf ' %s' "$@"
        printf '\\n'
    else
        "$@"
    fi
}}

need_command() {{
    command -v "$1" >/dev/null 2>&1 || {{
        echo "required command not found: $1" >&2
        exit 1
    }}
}}

partition_path() {{
    case "$1" in
        *[0-9]) printf '%sp%s' "$1" "$2" ;;
        *) printf '%s%s' "$1" "$2" ;;
    esac
}}

print_auto_disk_plan() {{
    echo
    echo "Automatic disk plan:"
    echo "  disk: $DISK"
    echo "  boot mode: $BOOT_MODE"
    echo "  filesystem: $FILESYSTEM"
    echo "  swap: $SWAP_MODE"
    if [ "$BOOT_MODE" = "efi" ]; then
        echo "  partition 1: 1GiB EFI system partition"
        echo "  partition 2: root filesystem"
    else
        echo "  partition 1: root filesystem"
    fi
}}

prepare_auto_disk() {{
    if [ "$PARTITION_MODE" != "auto" ]; then
        return
    fi

    if [ -z "$DISK" ] || [ "$DISK" = "/" ]; then
        echo "automatic partitioning requires --disk <device>" >&2
        exit 1
    fi

    print_auto_disk_plan
    if [ "$APPLY_DISK_LAYOUT" -ne 1 ]; then
        echo
        echo "Disk layout was not applied. Re-run with --apply-disk-layout to partition and format $DISK."
        exit 0
    fi

    need_command parted
    need_command partprobe
    if [ "$FILESYSTEM" = "btrfs" ]; then
        need_command mkfs.btrfs
    else
        need_command mkfs.ext4
    fi
    if [ "$BOOT_MODE" = "efi" ]; then
        need_command mkfs.vfat
    fi

    echo "Erasing and partitioning $DISK"
    run parted -s "$DISK" mklabel gpt

    if [ "$BOOT_MODE" = "efi" ]; then
        run parted -s "$DISK" mkpart ESP fat32 1MiB 1025MiB
        run parted -s "$DISK" set 1 esp on
        run parted -s "$DISK" mkpart primary 1025MiB 100%
        EFI_PARTITION="$(partition_path "$DISK" 1)"
        ROOT_PARTITION="$(partition_path "$DISK" 2)"
    else
        run parted -s "$DISK" mkpart primary 1MiB 100%
        ROOT_PARTITION="$(partition_path "$DISK" 1)"
        BOOT_DISK="$DISK"
    fi

    run partprobe "$DISK"
    run sleep 2

    if [ "$FILESYSTEM" = "btrfs" ]; then
        run mkfs.btrfs -f "$ROOT_PARTITION"
    else
        run mkfs.ext4 -F "$ROOT_PARTITION"
    fi

    run mkdir -p "$TARGET_ROOT"
    run mount "$ROOT_PARTITION" "$TARGET_ROOT"

    if [ "$BOOT_MODE" = "efi" ]; then
        run mkfs.vfat -F 32 "$EFI_PARTITION"
        run mkdir -p "$TARGET_ROOT$EFI_DIRECTORY"
        run mount "$EFI_PARTITION" "$TARGET_ROOT$EFI_DIRECTORY"
    fi
}}

write_fstab() {{
    fstab="$TARGET_ROOT/etc/fstab"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "+ write generated fstab to $fstab"
        return
    fi

    mkdir -p "$TARGET_ROOT/etc"
    : > "$fstab"
    if [ -z "$ROOT_PARTITION" ]; then
        ROOT_PARTITION="$(findmnt -n -o SOURCE --target "$TARGET_ROOT" 2>/dev/null || true)"
    fi
    if [ -n "$ROOT_PARTITION" ]; then
        root_uuid="$(blkid -s UUID -o value "$ROOT_PARTITION" 2>/dev/null || true)"
        if [ -n "$root_uuid" ]; then
            printf 'UUID=%s / %s defaults 0 1\\n' "$root_uuid" "$FILESYSTEM" >> "$fstab"
        else
            printf '%s / %s defaults 0 1\\n' "$ROOT_PARTITION" "$FILESYSTEM" >> "$fstab"
        fi
    fi
    if [ -n "$EFI_PARTITION" ]; then
        efi_uuid="$(blkid -s UUID -o value "$EFI_PARTITION" 2>/dev/null || true)"
        if [ -n "$efi_uuid" ]; then
            printf 'UUID=%s %s vfat umask=0077 0 2\\n' "$efi_uuid" "$EFI_DIRECTORY" >> "$fstab"
        else
            printf '%s %s vfat umask=0077 0 2\\n' "$EFI_PARTITION" "$EFI_DIRECTORY" >> "$fstab"
        fi
    fi
    if [ "$SWAP_MODE" = "swapfile" ]; then
        printf '/swapfile none swap defaults 0 0\\n' >> "$fstab"
    fi
}}

create_swapfile() {{
    if [ "$SWAP_MODE" != "swapfile" ]; then
        return
    fi
    echo "Creating 2GiB swapfile"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "+ create swapfile at $TARGET_ROOT/swapfile"
        return
    fi
    fallocate -l 2G "$TARGET_ROOT/swapfile" || dd if=/dev/zero of="$TARGET_ROOT/swapfile" bs=1M count=2048
    chmod 600 "$TARGET_ROOT/swapfile"
    mkswap "$TARGET_ROOT/swapfile"
}}

install_package() {{
    name="$1"
    version="$2"
    archive="$3"

    if [ ! -f "$archive" ]; then
        echo "missing archive for $name $version: $archive" >&2
        exit 1
    fi

    echo "==> installing $name $version"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf "+ printf 'y\\\\n' | %s -c %s --prefix %s --install --file %s\\n" "$TXPK_BIN" "$TXPK_CONFIG" "$TARGET_ROOT" "$archive"
    else
        printf 'y\\n' | "$TXPK_BIN" -c "$TXPK_CONFIG" --prefix "$TARGET_ROOT" --install --file "$archive"
    fi
}}

print_bootloader_steps() {{
    echo
    echo "Bootloader step selected: $BOOTLOADER"
    case "$BOOTLOADER" in
        none)
            echo "No bootloader selected."
            ;;
        grub-bios)
            echo "Review these commands after /etc/fstab and kernel paths are correct:"
            echo "  mount --bind /dev $TARGET_ROOT/dev"
            echo "  mount --bind /proc $TARGET_ROOT/proc"
            echo "  mount --bind /sys $TARGET_ROOT/sys"
            if [ -n "$BOOT_DISK" ]; then
                echo "  chroot $TARGET_ROOT grub-install --target=i386-pc $BOOT_DISK"
            else
                echo "  chroot $TARGET_ROOT grub-install --target=i386-pc /dev/YOUR_DISK"
            fi
            echo "  chroot $TARGET_ROOT grub-mkconfig -o /boot/grub/grub.cfg"
            ;;
        grub-efi)
            echo "Make sure the EFI system partition is mounted at $TARGET_ROOT$EFI_DIRECTORY."
            echo "Review these commands after /etc/fstab and kernel paths are correct:"
            echo "  mount --bind /dev $TARGET_ROOT/dev"
            echo "  mount --bind /proc $TARGET_ROOT/proc"
            echo "  mount --bind /sys $TARGET_ROOT/sys"
            echo "  chroot $TARGET_ROOT grub-install --target=x86_64-efi --efi-directory=$EFI_DIRECTORY --bootloader-id=Tuxenix"
            echo "  chroot $TARGET_ROOT grub-mkconfig -o /boot/grub/grub.cfg"
            ;;
        limine)
            echo "Limine package is installed in the target root."
            echo "Next step is to create a limine.conf matching the Tuxenix kernel/initramfs paths,"
            echo "then install Limine to the target disk or EFI system partition."
            echo "Do this only after the disk layout and /etc/fstab are final."
            ;;
    esac
}}

run mkdir -p "$TARGET_ROOT"
prepare_auto_disk
run mkdir -p "$TARGET_ROOT/dev" "$TARGET_ROOT/etc" "$TARGET_ROOT/home" "$TARGET_ROOT/proc" "$TARGET_ROOT/root" "$TARGET_ROOT/run" "$TARGET_ROOT/sys" "$TARGET_ROOT/tmp" "$TARGET_ROOT/var"
run chmod 1777 "$TARGET_ROOT/tmp"
if [ "$DRY_RUN" -eq 0 ]; then
    [ -e "$TARGET_ROOT/bin" ] || ln -s usr/bin "$TARGET_ROOT/bin"
    [ -e "$TARGET_ROOT/sbin" ] || ln -s usr/sbin "$TARGET_ROOT/sbin"
    [ -e "$TARGET_ROOT/lib" ] || ln -s usr/lib "$TARGET_ROOT/lib"
    [ -e "$TARGET_ROOT/lib64" ] || ln -s usr/lib "$TARGET_ROOT/lib64"
fi

{install_lines}

if [ "$DRY_RUN" -eq 0 ]; then
    [ -f "$TARGET_ROOT/etc/hostname" ] || printf 'tuxenix\\n' > "$TARGET_ROOT/etc/hostname"
    [ -f "$TARGET_ROOT/etc/hosts" ] || cat > "$TARGET_ROOT/etc/hosts" <<'HOSTS'
127.0.0.1 localhost
::1 localhost
127.0.1.1 tuxenix.localdomain tuxenix
HOSTS
    [ -s "$TARGET_ROOT/etc/passwd" ] || printf 'root:x:0:0:root:/root:/bin/bash\\n' > "$TARGET_ROOT/etc/passwd"
    [ -s "$TARGET_ROOT/etc/group" ] || printf 'root:x:0:\\n' > "$TARGET_ROOT/etc/group"
    [ -e "$TARGET_ROOT/etc/shadow" ] || printf 'root:!:0:0:99999:7:::\\n' > "$TARGET_ROOT/etc/shadow"
    chmod 600 "$TARGET_ROOT/etc/shadow"
fi

create_swapfile
write_fstab

echo "Tuxenix rootfs install complete."
print_bootloader_steps
echo "Next steps: review /etc/fstab and set root/user passwords inside the target root."
"""
    output.write_text(script)
    output.chmod(0o755)


def describe_plan(plan: InstallerPlan) -> str:
    lines = [
        f"requested packages: {len(plan.requested)}",
        f"installable packages: {len(plan.entries)}",
    ]
    if plan.missing_recipes:
        lines.append("missing recipes: " + ", ".join(plan.missing_recipes))
    if plan.missing_archives:
        lines.append("missing archives: " + ", ".join(plan.missing_archives))
    if plan.skipped_packages:
        lines.append("skipped packages: " + ", ".join(plan.skipped_packages))
    return "\n".join(lines)
