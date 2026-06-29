# Tuxenix Download And Install Guide

This guide records the first laptop-bootable Tuxenix ISO milestone, the current
home-lab package mirror workflow, and the remaining work needed before the ISO
is a polished public download.

Current status:

- ISO boots on a Lenovo laptop in UEFI mode.
- The ISO is a real bootable image that can be flashed with Rufus, `dd`, or
  Balena Etcher.
- The current ISO is a stage-1 installer: it boots into the Tuxenix installer
  shell and can install the base/rootfs flow.
- The full compiled package set is served by the home-lab HTTP mirror after the
  installed system boots.
- Package repo currently has 425 package names and 429 package archives.
- Public download is not finished yet. The `192.168.1.80` URLs only work on the
  local LAN until a Cloudflare Tunnel, Tailscale Funnel, GitHub Release, or
  object storage mirror is added.

## Download

Current home-lab mirror, LAN only:

```text
http://192.168.1.80:8088/
```

Current installer ISO, versioned:

```text
http://192.168.1.80:8088/iso/tuxenix-installer-2026-06-29.iso
```

Current installer ISO, stable latest link:

```text
http://192.168.1.80:8088/iso/tuxenix-installer-latest.iso
```

Checksum:

```text
http://192.168.1.80:8088/iso/tuxenix-installer-2026-06-29.iso.sha256
```

Package repository:

```text
http://192.168.1.80:8088/1-lts/
```

Install-all helper:

```text
http://192.168.1.80:8088/tuxenix-install-all-packages.sh
```

Download from Linux:

```sh
mkdir -p ~/Downloads/tuxenix
cd ~/Downloads/tuxenix

curl -O http://192.168.1.80:8088/iso/tuxenix-installer-2026-06-29.iso
curl -O http://192.168.1.80:8088/iso/tuxenix-installer-2026-06-29.iso.sha256

sha256sum -c tuxenix-installer-2026-06-29.iso.sha256
```

Expected SHA256:

```text
1a6edc0051982a3131dc00d873d38c62ba8d36372609536b01e979ecf69c51a1
```

## Write The USB

Find the USB device:

```sh
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS
```

Write the ISO. Replace `/dev/sdX` with the whole USB disk, not a partition:

```sh
sudo dd if=tuxenix-installer-2026-06-29.iso of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

Boot the laptop from the USB. The installer drops to a root shell and mounts
the ISO at `/run/iso`.

For Windows, download `tuxenix-installer-latest.iso`, open Rufus, select the
USB drive, select the ISO, and write it in ISO/DD mode. Rufus should use the
whole USB drive, not an existing partition on the USB.

## Install To An Existing Partition

This is the known-good flow used for the laptop install. It assumes the root
partition already exists and should be formatted as ext4.

Check disks:

```sh
lsblk -o NAME,MAJ:MIN,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS
```

Format and mount the target root partition. Replace `/dev/nvme0n1p4` if your
Tuxenix partition is different:

```sh
mkfs.ext4 -F -L TUXENIXHD /dev/nvme0n1p4
mount /dev/nvme0n1p4 /mnt/tuxenix
```

Install the root filesystem without installing a bootloader:

```sh
/usr/bin/bash /run/iso/tuxenix-install-rootfs.sh \
  --target-root /mnt/tuxenix \
  --partition-mode manual \
  --bootloader none \
  --swap none \
  --yes
```

Set a root password:

```sh
mount --bind /dev /mnt/tuxenix/dev
mount --bind /proc /mnt/tuxenix/proc
mount --bind /sys /mnt/tuxenix/sys
chroot /mnt/tuxenix /usr/bin/passwd root
sync
umount -R /mnt/tuxenix
```

## Add Tuxenix To An Existing GRUB

From the existing Linux install, find the Tuxenix root partition:

```sh
lsblk -o NAME,MAJ:MIN,SIZE,FSTYPE,LABEL,UUID
sudo blkid /dev/nvme0n1p4
```

For the first laptop install, `/dev/nvme0n1p4` appeared as `259:4`, and this
kernel root form booted successfully. The `root=259:4` form was used because
the early boot path did not reliably resolve UUID/device-name root arguments on
that laptop yet:

```grub
menuentry "Tuxenix" {
    insmod part_gpt
    insmod ext2
    search --no-floppy --fs-uuid --set=root YOUR_TUXENIX_ROOT_UUID
    linux /boot/vmlinuz-7.0.11-tuxenix root=259:4 rootfstype=ext4 rw rootwait init=/usr/lib/systemd/systemd
}
```

Add that to `/etc/grub.d/40_custom`, replacing `YOUR_TUXENIX_ROOT_UUID` with
the UUID from `blkid`. Then rebuild GRUB:

```sh
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

For another machine, use the `MAJ:MIN` value shown by `lsblk` for that
machine's Tuxenix root partition in the `root=` kernel argument.

Future ISO/initramfs work should make `root=UUID=...` reliable so this
machine-specific `MAJ:MIN` workaround is no longer needed.

## Configure The Package Repo On The Laptop

After Tuxenix boots, configure `txpk` to use the home-lab mirror:

```sh
mkdir -p /etc/txpk /var/lib/txpk /var/cache/txpk

cat > /etc/txpk/pkg.yml <<'EOF'
database: "/var/lib/txpk/txpk.db"
pkgRepoUrl: "http://192.168.1.80:8088"
pkgRepoCachePath: "/var/cache/txpk"
shareDir: "/usr/share/txpk"
EOF

txpk --init-database --list
```

Install a single package:

```sh
printf 'y\n' | txpk --install htop
```

Install the full compiled package set:

```sh
curl -fsSLO http://192.168.1.80:8088/tuxenix-install-all-packages.sh
chmod +x tuxenix-install-all-packages.sh
./tuxenix-install-all-packages.sh
```

The helper downloads `package-list.txt` from the mirror and runs
`txpk --install` for each package name. Failed package names are written to:

```text
/tmp/tuxenix-package-install-failed.txt
```

Retry failures with:

```sh
while read p; do printf 'y\n' | txpk --install "$p"; done < /tmp/tuxenix-package-install-failed.txt
```

If pasting commands directly on the laptop is painful, enable SSH on the laptop
after networking is up, then run these commands from another machine over SSH.

## How The ISO Works

The ISO is built by:

```sh
./tuxenix-toolkit iso
```

The build creates a GRUB-bootable ISO with these main pieces:

- `/boot/vmlinuz-7.0.11-tuxenix`: Tuxenix kernel.
- `/boot/tuxenix-installer-initramfs.zst`: live installer initramfs.
- `/tuxenix-install-rootfs.sh`: generated root filesystem installer.
- `/repo/1-lts/`: static txpk package repository used by the installer.

The initramfs is a small Tuxenix live root built from package archives. Its
`/init` script mounts `/dev`, `/proc`, `/sys`, `/run`, and `/tmp`, finds the
ISO by label `TUXENIX_ISO`, mounts it at `/run/iso`, writes a temporary txpk
config that points at `file:///run/iso/repo`, and opens an interactive shell.

The generated installer then installs packages into `/mnt/tuxenix` using txpk
with a target prefix. It creates the root filesystem directories, top-level
`/bin`, `/sbin`, `/lib`, and `/lib64` symlinks, `/etc/fstab`, hostname/hosts
files, and minimal account files if they do not exist.

The package repo is static HTTP content. Each directory has an `index.html`
because the txpk fetcher reads package, version, and archive names from simple
directory listings. The home-lab mirror is the same structure served by nginx.

The home-lab website root now has a human-readable download page with direct
links to:

```text
/iso/tuxenix-installer-latest.iso
/iso/tuxenix-installer-latest.iso.sha256
/1-lts/
/package-list.txt
/tuxenix-install-all-packages.sh
```

## Milestone Notes

The first working laptop ISO required fixes in several places:

- The ISO GRUB entry now uses the laptop console instead of forcing serial.
- The initramfs has `/usr/bin/sh -> bash`.
- Required live libraries such as zlib, libxcrypt, systemd/libudev, libcap, and
  lz4 are included in the live root.
- ISO repo directory indexes are generated automatically.
- Manual partition installs now write `/etc/fstab` from the mounted target root.
- Target roots get the standard top-level usr-merge symlinks.
- Minimal root account files are created so a password can be set after install.
- The home-lab repo now hosts the ISO under `/iso/` as both a versioned file and
  `tuxenix-installer-latest.iso`.
- The package helper `tuxenix-install-all-packages.sh` installs every package
  name listed in `package-list.txt` from the home-lab mirror.

## Future Public Download Work

The current mirror is LAN-only. A friend outside the house cannot use
`http://192.168.1.80:8088/`. Public download should move to one of these:

- Cloudflare R2 or another static object host for ISO and package archives.
- Cloudflare Tunnel in front of the home-lab nginx server.
- A GitHub release for ISO artifacts plus a separate package mirror.

Fast temporary public option, run on the server:

```sh
cloudflared tunnel --url http://localhost:8088
```

That prints a `https://...trycloudflare.com` URL. With the current layout, the
friend-facing ISO URL would be:

```text
https://THE-TUNNEL.trycloudflare.com/iso/tuxenix-installer-latest.iso
```

The public mirror should keep the same layout:

```text
/iso/tuxenix-installer-latest.iso
/iso/tuxenix-installer-latest.iso.sha256
/1-lts/
/package-list.txt
/tuxenix-install-all-packages.sh
```
