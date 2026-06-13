# Tuxenix Boot Lab

This is the repeatable boot/testing flow for the current Tuxenix VM.

## Current Shape

Tuxenix userspace is LFS/BLFS based. For fast testing, QEMU boots with the host Arch kernel and initramfs:

```text
/boot/vmlinuz-linux
/boot/initramfs-linux.img
```

That means the guest root filesystem must contain matching kernel modules under:

```text
/usr/lib/modules/$(uname -r)
```

If those modules are missing, Xorg can fail with:

```text
Fatal server error:
no screens found
```

The usual cause is `virtio_gpu` not loading, which leaves no `/dev/dri/card0`.

## Boot

```sh
cd ~/Projects/anysolo-test

qemu-system-x86_64 \
  -enable-kvm \
  -m 4096 \
  -smp 4 \
  -cpu host \
  -drive file=tuxenix.img,format=raw,if=virtio \
  -kernel /boot/vmlinuz-linux \
  -initrd /boot/initramfs-linux.img \
  -append "root=/dev/vda1 rw init=/usr/lib/systemd/systemd systemd.unit=multi-user.target console=ttyS0" \
  -device virtio-vga \
  -netdev user,id=net0 \
  -device virtio-net-pci,netdev=net0 \
  -display gtk \
  -serial mon:stdio
```

Or ask the helper:

```sh
./tuxenix-toolkit vm boot
```

## Xorg Bring-up Checks

Inside Tuxenix:

```sh
uname -r
ls /usr/lib/modules/$(uname -r)
modprobe virtio_gpu
ls -l /dev/dri
startx
```

Expected:

```text
/dev/dri/card0
```

## Inject Matching Kernel Modules

If the guest is missing host kernel modules, shut the VM down first. Then from the host:

```sh
sudo env TMPDIR=/tmp LIBGUESTFS_CACHEDIR=/tmp/guestfs-cache XDG_RUNTIME_DIR=/tmp/runtime-elgun \
  virt-copy-in -a ~/Projects/anysolo-test/tuxenix.img -m /dev/sda1 /usr/lib/modules/$(uname -r) /usr/lib/modules
```

The toolkit can print that command:

```sh
./tuxenix-toolkit vm inject-modules
```

## Locale / Terminal Rendering

If terminal apps show `â` characters instead of box drawing, verify:

```sh
locale
echo "$LANG"
```

The VM should use a generated UTF-8 locale, currently:

```text
LANG=en_US.UTF-8
```

`/root/.xinitrc` should launch `uxterm`, not plain `xterm`.

## Safe Package Testing

Avoid testing core runtime package replacement live unless the package database is seeded and known good.

Do not casually live-install:

```text
glibc
zlib
bash
systemd
```

Use leaf packages for smoke tests:

```text
tty-clock
btop
tree
ncdu
vifm
```
