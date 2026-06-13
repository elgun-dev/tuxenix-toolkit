from __future__ import annotations

from pathlib import Path


def vm_command(action: str, workspace: Path, kernel_version: str = "") -> str:
    image = workspace / "tuxenix.img"
    if action == "boot":
        return f"""cd {workspace}
qemu-system-x86_64 \\
  -enable-kvm \\
  -m 4096 \\
  -smp 4 \\
  -cpu host \\
  -drive file={image.name},format=raw,if=virtio \\
  -kernel /boot/vmlinuz-linux \\
  -initrd /boot/initramfs-linux.img \\
  -append "root=/dev/vda1 rw init=/usr/lib/systemd/systemd systemd.unit=multi-user.target console=ttyS0" \\
  -device virtio-vga \\
  -netdev user,id=net0 \\
  -device virtio-net-pci,netdev=net0 \\
  -display gtk \\
  -serial mon:stdio"""
    if action == "serial":
        return vm_command("boot", workspace).replace("-display gtk", "-display none")
    if action == "mount":
        return f"""sudo mkdir -p /mnt/tuxenix-img
sudo mount -o loop,offset=$((2048*512)) {image} /mnt/tuxenix-img"""
    if action == "inject-modules":
        version = kernel_version or "$(uname -r)"
        return f"""sudo env TMPDIR=/tmp LIBGUESTFS_CACHEDIR=/tmp/guestfs-cache XDG_RUNTIME_DIR=/tmp/runtime-elgun \\
  virt-copy-in -a {image} -m /dev/sda1 /usr/lib/modules/{version} /usr/lib/modules"""
    if action == "snapshot":
        return f"cp -av {image} {workspace}/tuxenix-$(date +%Y%m%d-%H%M%S).img"
    raise ValueError(f"unknown VM action: {action}")
