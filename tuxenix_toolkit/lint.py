from __future__ import annotations

from dataclasses import dataclass
import re

from .packages import Package, valid_version


BUILD_ONLY_DEPS = {
    "autoconf",
    "automake",
    "binutils",
    "bison",
    "cmake",
    "dejagnu",
    "flex",
    "gawk",
    "gcc",
    "gettext",
    "gperf",
    "help2man",
    "make",
    "meson",
    "ninja",
    "pkgconf",
    "texinfo",
}


@dataclass(frozen=True)
class Issue:
    level: str
    package: str
    message: str


def lint_packages(packages: dict[str, Package]) -> list[Issue]:
    issues: list[Issue] = []
    known = set(packages)

    for package in sorted(packages.values(), key=lambda item: item.name):
        if not package.version:
            issues.append(Issue("error", package.name, "missing version"))
        elif not valid_version(package.version):
            issues.append(Issue("error", package.name, f"version is not numeric-ish: {package.version}"))

        if not package.comment:
            issues.append(Issue("warning", package.name, "missing practical comment field"))

        if not package.has_build_script:
            issues.append(Issue("error", package.name, "missing build.sh"))

        if not package.source_archives:
            issues.append(Issue("warning", package.name, "missing source archive in src/"))

        build_script = package.path / "build.sh"
        if build_script.exists():
            text = build_script.read_text(errors="replace")
            if re.search(r"(^|\s)(make|ninja)\s+install(\s|$)", text) and "DESTDIR" not in text:
                issues.append(Issue("error", package.name, "build.sh appears to install without DESTDIR"))
            if "TXPK_PACKAGE_BUILD_DIST_DIR" not in text:
                issues.append(Issue("warning", package.name, "build.sh does not mention TXPK_PACKAGE_BUILD_DIST_DIR"))

        if (package.path / "dist").exists():
            issues.append(Issue("warning", package.name, "generated dist/ directory is present"))

        for dep in package.depends:
            if dep not in known:
                issues.append(Issue("warning", package.name, f"depends on unknown package: {dep}"))
            if dep in BUILD_ONLY_DEPS:
                issues.append(Issue("warning", package.name, f"runtime deps include likely build-only tool: {dep}"))

    return issues
