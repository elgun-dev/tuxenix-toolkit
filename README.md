# Tuxenix Toolkit

Practical tooling for Tuxenix package work, dependency analysis, build visibility, and QEMU boot testing.

This repo turns the day-to-day distro work into reusable tools:

- package recipe linter
- dependency graph generator
- package explorer HTML report
- build dashboard HTML report
- root filesystem installer script generator
- bootable installer ISO builder
- QEMU command helper
- LFS/Tuxenix boot lab notes

It is built for the package tree at:

```text
~/Projects/pkg-sources/os/1-lts
```

## Quick Start

```sh
cd ~/Projects/tuxenix-toolkit
chmod +x tuxenix-toolkit

./tuxenix-toolkit summary
./tuxenix-toolkit lint
./tuxenix-toolkit graph --output deps.mmd --systemd-report systemd-report.md
./tuxenix-toolkit explorer --output package-explorer.html
./tuxenix-toolkit dashboard --output build-dashboard.html
./tuxenix-toolkit installer --plan
./tuxenix-toolkit iso
./tuxenix-toolkit vm boot
```

Use another package tree with:

```sh
./tuxenix-toolkit --package-root /path/to/os/1-lts summary
```

## What The Tools Do

### Linter

Checks the recipe mistakes that matter for Tuxenix:

- missing `comment`
- bad version strings
- missing `build.sh`
- missing source archives
- `make install` or `ninja install` without `DESTDIR`
- `build.sh` not mentioning `TXPK_PACKAGE_BUILD_DIST_DIR`
- generated `dist/` directories present
- likely build-only tools listed as runtime dependencies

### Dependency Graph

Writes a Mermaid graph and a systemd impact report:

```sh
./tuxenix-toolkit graph
```

The report shows direct and transitive systemd dependency paths.

### Package Explorer

Writes a searchable static HTML page with:

- package name
- version
- dependencies
- reverse dependencies
- practical package comment

### Build Dashboard

Writes a static HTML page showing:

- total packages
- packages with built artifacts
- missing source archives
- missing build scripts
- dist archive names

### Installer

Writes a shell installer for creating a Tuxenix root filesystem from local
`.txpk` archives:

```sh
./tuxenix-toolkit installer --profile minimal --output tuxenix-install-rootfs.sh
sudo ./tuxenix-install-rootfs.sh --target-root /mnt/tuxenix
```

This is intentionally the rootfs stage, not a full guided disk installer. It
does not partition disks or format filesystems. The generated installer can ask
for a bootloader choice and install the selected bootloader package into the
target root:

```sh
sudo ./tuxenix-install-rootfs.sh --target-root /mnt/tuxenix --bootloader ask
```

Supported bootloader choices are `none`, `grub-bios`, `grub-efi`, and `limine`.
The script prints the final bootloader commands instead of running them blindly,
because those commands depend on the final disk, EFI partition, kernel paths,
and `/etc/fstab`.

The generated script can also guide the disk/filesystem choices:

```sh
sudo ./tuxenix-install-rootfs.sh \
  --partition-mode auto \
  --disk /dev/sdX \
  --filesystem ext4 \
  --swap swapfile \
  --boot-mode efi \
  --bootloader grub-efi
```

Automatic partitioning only prints a disk plan unless `--apply-disk-layout` is
also passed. That flag is intentionally separate because it erases and formats
the selected disk.

### Installer ISO

Builds a GRUB-bootable Tuxenix installer ISO:

```sh
./tuxenix-toolkit iso
```

The ISO contains a small live initramfs, the generated rootfs installer script,
the Tuxenix kernel, and a static `txpk` repo under `/repo/1-lts`. See
[docs/download.md](docs/download.md) for the current download, laptop install,
home-lab package mirror, and milestone notes.

### VM Helper

Prints known-good commands for the current Tuxenix QEMU image:

```sh
./tuxenix-toolkit vm boot
./tuxenix-toolkit vm serial
./tuxenix-toolkit vm inject-modules --kernel-version 7.0.12-arch1-1
./tuxenix-toolkit vm snapshot
```

## Status

First working cut. The tools are intentionally simple and use only the Python standard library so they can run in a minimal development environment.
