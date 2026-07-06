from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

from .installer import (
    BOOTLOADER_CHOICES,
    InstallerEntry,
    InstallerPlan,
    archive_for_package,
    build_installer_plan,
    write_installer_script,
)
from .packages import Package


ISO_LABEL = "TUXENIX_ISO"
ISO_REPO_ROOT = Path("/run/iso/repo/1-lts")

SHELL_LIVE_PACKAGES: tuple[str, ...] = (
    "glibc",
    "bash",
    "coreutils",
    "grep",
    "sed",
    "gzip",
    "tar",
    "bzip2",
    "zlib",
    "xz",
    "zstd",
    "lz4",
    "ncurses",
    "readline",
    "util-linux",
    "systemd",
    "libcap",
    "libxcrypt",
    "kmod",
    "linux-tuxenix",
    "gcc",
    "txpk",
    "yaml-cpp",
    "argh",
    "curl",
    "libpsl",
    "libunistring",
    "libidn2",
    "openssl",
    "nghttp2",
    "libarchive",
    "acl",
    "attr",
    "expat",
    "sqlitecpp",
    "sqlite",
    "shadow",
    "e2fsprogs",
    "parted",
    "lzo",
    "dosfstools",
    "btrfs-progs",
    "gptfdisk",
    "dhcpcd",
    "iproute2",
    "iputils",
    "procps-ng",
    "kbd",
    "less",
    "vim",
)

CALAMARES_LIVE_PACKAGES: tuple[str, ...] = (
    *SHELL_LIVE_PACKAGES,
    "dbus",
    "fontconfig",
    "fonts-liberation",
    "libinput",
    "mesa",
    "networkmanager",
    "xauth",
    "xinit",
    "xkeyboard-config",
    "xmessage",
    "xorg-server",
    "xterm",
    "xf86-input-libinput",
    "icewm",
    "calamares",
    "tuxenix-calamares-config",
)

LIVE_PACKAGE_SETS: dict[str, tuple[str, ...]] = {
    "shell": SHELL_LIVE_PACKAGES,
    "calamares": CALAMARES_LIVE_PACKAGES,
}


@dataclass(frozen=True)
class IsoBuildResult:
    iso_path: Path
    initramfs_path: Path
    staging_dir: Path
    installer_entries: int
    live_entries: int
    installer_ui: str


def _run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _package_entries(
    packages: dict[str, Package],
    repo_root: Path,
    requested: tuple[str, ...],
    resolve_dependencies: bool = True,
) -> tuple[InstallerEntry, ...]:
    ordered: list[Package] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            return
        package = packages.get(name)
        if package is None:
            raise ValueError(f"missing package recipe: {name}")

        visiting.add(name)
        if resolve_dependencies:
            for dependency in package.depends:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(package)

    for name in requested:
        visit(name)

    entries: list[InstallerEntry] = []
    missing: list[str] = []
    for package in ordered:
        archive = archive_for_package(repo_root, package)
        if archive is None:
            missing.append(package.name)
            continue
        entries.append(InstallerEntry(package, archive))

    if missing:
        raise ValueError("missing package archives: " + ", ".join(dict.fromkeys(missing)))

    return tuple(entries)


def _extract_txpk(archive: Path, root: Path) -> None:
    _run(["tar", "-xf", str(archive), "-C", str(root), "--strip-components=2", "./files"])


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _write_init(root: Path, installer_ui: str) -> None:
    init = root / "init"
    calamares_autostart = ""
    if installer_ui == "calamares":
        calamares_autostart = """
if [ -x /usr/bin/localedef ] && [ ! -e /usr/lib/locale/C.UTF-8 ]; then
    mkdir -p /usr/lib/locale
    /usr/bin/localedef -i en_US -f UTF-8 C.UTF-8 2>/dev/null || true
fi
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

if [ -x /usr/bin/startx ]; then
    echo "Starting Tuxenix graphical installer session..."
    /usr/bin/startx /usr/local/bin/tuxenix-calamares-session -- :0 vt1 || true
    echo
    echo "Graphical installer exited or failed. Dropping to installer shell."
fi
"""

    text = """#!/usr/bin/bash
set -eu

export PATH=/usr/bin:/usr/sbin:/bin:/sbin
export TERM=linux
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t tmpfs tmpfs /run 2>/dev/null || true
mount -t tmpfs tmpfs /tmp 2>/dev/null || true
mkdir -p /run/iso /mnt/tuxenix /var/lib/txpk /var/cache/txpk /etc/txpk

cat >/etc/txpk/pkg.yml <<'EOF'
database: "/var/lib/txpk/txpk.db"
pkgRepoUrl: "file:///run/iso/repo"
pkgRepoCachePath: "/var/cache/txpk"
shareDir: "/usr/share/txpk"
EOF

mount_iso() {
    try_mount_iso() {
        dev="$1"
        [ -b "$dev" ] || return 1
        mount -o ro "$dev" /run/iso 2>/dev/null || mount -t iso9660 -o ro "$dev" /run/iso 2>/dev/null || return 1
        if [ -f /run/iso/tuxenix-install-rootfs.sh ]; then
            return 0
        fi
        umount /run/iso 2>/dev/null || true
        return 1
    }

    for try in 1 2 3 4 5 6 7 8 9 10; do
        label_dev="$(blkid -L TUXENIX_ISO 2>/dev/null || true)"
        if [ -n "$label_dev" ] && [ -b "$label_dev" ]; then
            try_mount_iso "$label_dev" && return 0
        fi

        for dev in \
            /dev/disk/by-label/TUXENIX_ISO \
            /dev/sr* /dev/cdrom \
            /dev/vd* /dev/sd* \
            /dev/nvme*n* /dev/mmcblk*; do
            try_mount_iso "$dev" && return 0
        done
        sleep 1
    done
    return 1
}

clear || true
echo "Tuxenix installer ISO"
echo
if mount_iso; then
    echo "Mounted install media at /run/iso"
else
    echo "WARNING: could not mount install media automatically."
fi
echo
echo "Useful commands:"
echo "  lsblk"
echo "  /run/iso/tuxenix-install-rootfs.sh --help"
echo "  /run/iso/tuxenix-install-rootfs.sh --partition-mode auto --disk /dev/sda --bootloader ask"
echo
echo "Nothing will erase a disk unless you pass --apply-disk-layout."
__CALAMARES_AUTOSTART__
echo
exec /usr/bin/bash -l
"""
    init.write_text(text.replace("__CALAMARES_AUTOSTART__", calamares_autostart.rstrip()))
    init.chmod(0o755)


def _write_calamares_session(root: Path) -> None:
    local_bin = root / "usr/local/bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    session = local_bin / "tuxenix-calamares-session"
    session.write_text("""#!/usr/bin/bash
set -u

export PATH=/usr/bin:/usr/sbin:/bin:/sbin
export HOME=/root
export XDG_RUNTIME_DIR=/run
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

mkdir -p /run/dbus /root
dbus-daemon --system --fork 2>/dev/null || true

xsetroot -solid '#263238' 2>/dev/null || true

if [ -x /usr/bin/calamares ] && [ -f /etc/calamares/settings.conf ]; then
    /usr/bin/calamares &
else
    xterm -T "Tuxenix installer" -geometry 96x28+40+60 -e /usr/local/bin/tuxenix-calamares-missing &
fi

if command -v icewm-session >/dev/null 2>&1; then
    exec icewm-session
fi

if command -v icewm >/dev/null 2>&1; then
    exec icewm
fi

exec xterm
""")
    session.chmod(0o755)

    missing = local_bin / "tuxenix-calamares-missing"
    missing.write_text("""#!/usr/bin/bash
cat <<'EOF'
Tuxenix graphical installer session is running.

Calamares is not ready yet because the live root does not contain:

  /etc/calamares/settings.conf

Build and install the Tuxenix calamares package/config, then rebuild this ISO
with:

  ./tuxenix-toolkit iso --installer-ui calamares

For the current shell installer, use:

  /run/iso/tuxenix-install-rootfs.sh --help
EOF
exec /usr/bin/bash -l
""")
    missing.chmod(0o755)


def _prepare_live_root(root: Path, entries: tuple[InstallerEntry, ...], installer_ui: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        _extract_txpk(entry.archive, root)

    for link, target in {
        "bin": "usr/bin",
        "sbin": "usr/sbin",
        "lib": "usr/lib",
        "lib64": "usr/lib",
    }.items():
        path = root / link
        if not path.exists():
            path.symlink_to(target)

    sh = root / "usr/bin/sh"
    if not sh.exists():
        sh.symlink_to("bash")

    for directory in ("dev", "proc", "sys", "run", "tmp", "mnt", "etc", "var/lib/txpk", "var/cache/txpk"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    linux_doc = root / "usr/share/doc/linux-tuxenix-7.0.11"
    if linux_doc.exists():
        shutil.rmtree(linux_doc)

    _prune_live_root(root, keep_python=(installer_ui == "calamares"))
    if installer_ui == "calamares":
        _write_calamares_session(root)
    _make_regular_files_readable(root)
    _write_init(root, installer_ui)


def _make_regular_files_readable(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        mode = path.stat().st_mode & 0o7777
        if mode & 0o400:
            continue
        path.chmod(mode | 0o400)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _prune_live_root(root: Path, keep_python: bool = False) -> None:
    pruned_directories = [
        "boot",
        "usr/include",
        "usr/lib/gcc",
        "usr/libexec/gcc",
        "usr/lib/perl5",
        "usr/share/doc",
        "usr/share/gdb",
        "usr/share/gettext",
        "usr/share/info",
        "usr/share/locale",
        "usr/share/man",
        "usr/share/pkgconfig",
    ]
    if not keep_python:
        pruned_directories.append("usr/lib/python3.14")
        pruned_directories.append("usr/share/i18n")

    for relative in pruned_directories:
        path = root / relative
        if path.exists() or path.is_symlink():
            _remove_path(path)

    pruned_patterns = [
        "usr/lib/*.a",
        "usr/lib/*.la",
        "usr/bin/*gcc*",
        "usr/bin/*g++*",
        "usr/bin/*gcov*",
        "usr/bin/*-c++",
        "usr/bin/*-cpp",
        "usr/bin/as",
        "usr/bin/c++",
        "usr/bin/cc",
        "usr/bin/ccmake",
        "usr/bin/cmake",
        "usr/bin/cpack",
        "usr/bin/cpp",
        "usr/bin/ctest",
        "usr/bin/g++",
        "usr/bin/gcc",
        "usr/bin/gcov",
        "usr/bin/ld",
        "usr/bin/ld.bfd",
        "usr/bin/lto-dump",
        "usr/bin/meson",
        "usr/bin/ninja",
        "usr/bin/perl*",
        "usr/bin/x86_64-pc-linux-gnu-*",
        "usr/lib/libbfd-*",
        "usr/lib/libctf*",
        "usr/lib/libgprofng*",
        "usr/lib/libstdc++*.a",
    ]
    if not keep_python:
        pruned_patterns.extend([
            "usr/bin/python*",
            "usr/lib/libpython*",
        ])

    for pattern in pruned_patterns:
        for path in root.glob(pattern):
            if path.exists() or path.is_symlink():
                _remove_path(path)


def _write_initramfs(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = f"set -o pipefail; find . -print0 | cpio --null -o --format=newc | zstd -19 -T0 -o {output}"
    subprocess.run(["bash", "-lc", command], cwd=root, check=True)


def _copy_iso_repo(staging: Path, repo_root: Path, plan: InstallerPlan) -> None:
    iso_repo = staging / "repo" / "1-lts"
    for entry in plan.entries:
        relative = entry.archive.relative_to(repo_root)
        _link_or_copy(entry.archive, iso_repo / relative)
    _write_directory_indexes(staging / "repo")


def _write_directory_indexes(root: Path) -> None:
    for directory, dirnames, filenames in os.walk(root):
        path = Path(directory)
        entries = [f"{name}/" for name in sorted(dirnames)]
        entries.extend(name for name in sorted(filenames) if name != "index.html")
        index = path / "index.html"
        index.write_text(
            "<html><body>\n"
            + "".join(f'<a href="{entry}">{entry}</a>\n' for entry in entries)
            + "</body></html>\n"
        )


def _write_grub_cfg(staging: Path) -> None:
    grub_dir = staging / "boot/grub"
    grub_dir.mkdir(parents=True, exist_ok=True)
    (grub_dir / "grub.cfg").write_text(f"""set timeout=5
set default=0

menuentry "Tuxenix installer" {{
    linux /boot/vmlinuz-7.0.11-tuxenix console=tty0
    initrd /boot/tuxenix-installer-initramfs.zst
}}
""")


def _write_iso_installer(plan: InstallerPlan, staging: Path, repo_root: Path) -> None:
    installer = staging / "tuxenix-install-rootfs.sh"
    write_installer_script(
        plan,
        installer,
        Path("/mnt/tuxenix"),
        Path("/etc/txpk"),
        "ask",
    )
    text = installer.read_text()
    text = text.replace(str(repo_root.resolve()), str(ISO_REPO_ROOT))
    installer.write_text(text)


def build_iso(
    packages: dict[str, Package],
    repo_root: Path,
    output: Path,
    work_dir: Path,
    profile: str = "rescue",
    installer_ui: str = "shell",
) -> IsoBuildResult:
    if installer_ui not in LIVE_PACKAGE_SETS:
        raise ValueError(f"unknown installer UI: {installer_ui}")

    repo_root = repo_root.resolve()
    output = output.resolve()
    work_dir = work_dir.resolve()
    staging = work_dir / "staging"
    live_root = work_dir / "initramfs-root"
    initramfs = staging / "boot/tuxenix-installer-initramfs.zst"

    if work_dir.exists():
        shutil.rmtree(work_dir)
    staging.mkdir(parents=True)

    bootloaders = tuple(name for name in BOOTLOADER_CHOICES if name != "none")
    installer_plan = build_installer_plan(packages, repo_root, profile, (), bootloaders, False)
    if installer_plan.missing_recipes:
        raise ValueError("missing package recipes: " + ", ".join(installer_plan.missing_recipes))
    if installer_plan.missing_archives:
        raise ValueError("missing package archives: " + ", ".join(installer_plan.missing_archives))

    live_entries = _package_entries(
        packages,
        repo_root,
        LIVE_PACKAGE_SETS[installer_ui],
        resolve_dependencies=(installer_ui != "shell"),
    )
    _prepare_live_root(live_root, live_entries, installer_ui)

    kernel = Path.home() / "Projects/pkg-sources/os/1-lts/linux-tuxenix/dist/files/boot/vmlinuz-7.0.11-tuxenix"
    if not kernel.exists():
        raise ValueError(f"missing kernel: {kernel}")
    boot_dir = staging / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kernel, boot_dir / kernel.name)

    _write_initramfs(live_root, initramfs)
    _write_iso_installer(installer_plan, staging, repo_root)
    _copy_iso_repo(staging, repo_root, installer_plan)
    _write_grub_cfg(staging)

    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "grub-mkrescue",
        "-o",
        str(output),
        "-volid",
        ISO_LABEL,
        str(staging),
    ])

    return IsoBuildResult(
        iso_path=output,
        initramfs_path=initramfs,
        staging_dir=staging,
        installer_entries=len(installer_plan.entries),
        live_entries=len(live_entries),
        installer_ui=installer_ui,
    )
