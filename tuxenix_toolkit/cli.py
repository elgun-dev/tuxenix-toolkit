from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .dashboard import repo_archives, write_dashboard
from .explorer import write_explorer
from .graph import write_mermaid_graph, write_systemd_report
from .installer import (
    BOOTLOADER_CHOICES,
    INSTALLER_PROFILES,
    build_installer_plan,
    describe_plan,
    write_installer_script,
)
from .iso import build_iso
from .lint import lint_packages
from .packages import DEFAULT_PACKAGE_ROOT, load_packages
from .vm import vm_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tuxenix-toolkit")
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_ROOT)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="lint package recipes")
    lint.add_argument("--strict", action="store_true", help="treat warnings as errors")

    graph = sub.add_parser("graph", help="write dependency graph outputs")
    graph.add_argument("--output", type=Path, default=Path("tuxenix-deps.mmd"))
    graph.add_argument("--systemd-report", type=Path, default=Path("systemd-report.md"))

    explorer = sub.add_parser("explorer", help="write package explorer HTML")
    explorer.add_argument("--output", type=Path, default=Path("package-explorer.html"))

    dashboard = sub.add_parser("dashboard", help="write build dashboard HTML")
    dashboard.add_argument("--output", type=Path, default=Path("build-dashboard.html"))
    dashboard.add_argument("--repo-root", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "repo" / "1-lts")

    installer = sub.add_parser("installer", help="write a Tuxenix rootfs installer script")
    installer.add_argument("--profile", choices=sorted(INSTALLER_PROFILES), default="minimal")
    installer.add_argument("--output", type=Path, default=Path("tuxenix-install-rootfs.sh"))
    installer.add_argument("--repo-root", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "repo" / "1-lts")
    installer.add_argument("--target-root", type=Path, default=Path("/mnt/tuxenix"))
    installer.add_argument("--txpk-config", type=Path, default=Path("/etc/txpk"))
    installer.add_argument("--bootloader", choices=[*sorted(BOOTLOADER_CHOICES), "ask"], default="ask")
    installer.add_argument("--add-package", action="append", default=[], help="include an additional package")
    installer.add_argument("--skip-missing", action="store_true", help="generate a script without packages that lack archives")
    installer.add_argument("--plan", action="store_true", help="print the installer package plan without writing a script")

    vm = sub.add_parser("vm", help="print QEMU and image-maintenance commands")
    vm.add_argument("action", choices=["boot", "serial", "mount", "inject-modules", "snapshot"])
    vm.add_argument("--workspace", type=Path, default=Path.home() / "Projects" / "anysolo-test")
    vm.add_argument("--kernel-version", default="")

    iso = sub.add_parser("iso", help="build a bootable Tuxenix installer ISO")
    iso.add_argument("--profile", choices=sorted(INSTALLER_PROFILES), default="rescue")
    iso.add_argument("--repo-root", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "repo" / "1-lts")
    iso.add_argument("--output", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "iso-out" / "tuxenix-installer.iso")
    iso.add_argument("--work-dir", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "iso-out" / "work")

    summary = sub.add_parser("summary", help="print package summary")
    summary.add_argument("--repo-root", type=Path, default=Path.home() / "Projects" / "anysolo-test" / "repo" / "1-lts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "vm":
        print(vm_command(args.action, args.workspace, args.kernel_version))
        return 0

    packages = load_packages(args.package_root)

    if args.command == "summary":
        built = sum(1 for package in packages.values() if package.is_built or repo_archives(args.repo_root, package))
        print(f"packages: {len(packages)}")
        print(f"built artifacts present: {built}")
        print(f"unbuilt/no dist archive: {len(packages) - built}")
        return 0

    if args.command == "lint":
        issues = lint_packages(packages)
        for issue in issues:
            print(f"{issue.level}: {issue.package}: {issue.message}")
        errors = [issue for issue in issues if issue.level == "error"]
        warnings = [issue for issue in issues if issue.level == "warning"]
        print(f"lint: {len(errors)} errors, {len(warnings)} warnings")
        return 1 if errors or (args.strict and warnings) else 0

    if args.command == "graph":
        write_mermaid_graph(packages, args.output)
        write_systemd_report(packages, args.systemd_report)
        print(f"wrote {args.output}")
        print(f"wrote {args.systemd_report}")
        return 0

    if args.command == "explorer":
        write_explorer(packages, args.output)
        print(f"wrote {args.output}")
        return 0

    if args.command == "dashboard":
        write_dashboard(packages, args.output, args.repo_root)
        print(f"wrote {args.output}")
        return 0

    if args.command == "iso":
        result = build_iso(packages, args.repo_root, args.output, args.work_dir, args.profile)
        print(f"wrote {result.iso_path}")
        print(f"initramfs: {result.initramfs_path}")
        print(f"staging: {result.staging_dir}")
        print(f"installer packages: {result.installer_entries}")
        print(f"live packages: {result.live_entries}")
        return 0

    if args.command == "installer":
        bootloaders = tuple(
            name
            for name in BOOTLOADER_CHOICES
            if name != "none"
        ) if args.bootloader == "ask" else (args.bootloader,)
        plan = build_installer_plan(
            packages,
            args.repo_root,
            args.profile,
            tuple(args.add_package),
            bootloaders,
            args.skip_missing,
        )
        print(describe_plan(plan))
        if plan.missing_recipes:
            return 1
        if plan.missing_archives and not args.skip_missing:
            print("use --skip-missing to generate a partial installer")
            return 1
        if args.plan:
            for entry in plan.entries:
                print(f"{entry.package.name} {entry.package.version} {entry.archive}")
            return 0
        write_installer_script(plan, args.output, args.target_root, args.txpk_config, args.bootloader)
        print(f"wrote {args.output}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
