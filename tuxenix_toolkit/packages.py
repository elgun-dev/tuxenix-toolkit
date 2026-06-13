from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


DEFAULT_PACKAGE_ROOT = Path.home() / "Projects" / "pkg-sources" / "os" / "1-lts"


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    arch: str
    path: Path
    depends: tuple[str, ...]
    comment: str
    has_build_script: bool
    source_archives: tuple[Path, ...]
    dist_archives: tuple[Path, ...]

    @property
    def is_built(self) -> bool:
        return bool(self.dist_archives)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_package_yml(path: Path) -> dict[str, object]:
    data: dict[str, object] = {}
    current_list: str | None = None

    for raw_line in path.read_text(errors="replace").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        stripped = raw_line.strip()
        if current_list and stripped.startswith("- "):
            data.setdefault(current_list, [])
            assert isinstance(data[current_list], list)
            data[current_list].append(_strip_quotes(stripped[2:]))
            continue

        if not raw_line.startswith((" ", "\t")):
            current_list = None

        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "[]":
            data[key] = []
        elif value:
            data[key] = _strip_quotes(value)
        else:
            data[key] = []
            current_list = key

    return data


def find_source_archives(package_dir: Path) -> tuple[Path, ...]:
    src = package_dir / "src"
    if not src.exists():
        return ()
    return tuple(sorted(p for p in src.iterdir() if p.is_file()))


def find_dist_archives(package_dir: Path) -> tuple[Path, ...]:
    dist = package_dir / "dist"
    if not dist.exists():
        return ()
    patterns = ("*.txpk.tar.bz2", "*.txpk.tar.gz", "*.txpk.tar.xz")
    found: list[Path] = []
    for pattern in patterns:
        found.extend(dist.glob(pattern))
    return tuple(sorted(found))


def load_packages(package_root: Path = DEFAULT_PACKAGE_ROOT) -> dict[str, Package]:
    packages: dict[str, Package] = {}
    for package_yml in sorted(package_root.glob("*/package.yml")):
        package_dir = package_yml.parent
        meta = parse_package_yml(package_yml)
        name = str(meta.get("name") or package_dir.name)
        depends = tuple(str(dep) for dep in meta.get("depends", []) if str(dep))
        packages[name] = Package(
            name=name,
            version=str(meta.get("version") or ""),
            arch=str(meta.get("arch") or ""),
            path=package_dir,
            depends=depends,
            comment=str(meta.get("comment") or ""),
            has_build_script=(package_dir / "build.sh").is_file(),
            source_archives=find_source_archives(package_dir),
            dist_archives=find_dist_archives(package_dir),
        )
    return packages


def reverse_dependencies(packages: dict[str, Package]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {name: set() for name in packages}
    for package in packages.values():
        for dep in package.depends:
            reverse.setdefault(dep, set()).add(package.name)
    return reverse


def transitive_dependencies(packages: dict[str, Package], package_name: str) -> set[str]:
    seen: set[str] = set()
    stack = list(packages.get(package_name, Package(package_name, "", "", Path(), (), "", False, (), ())).depends)
    while stack:
        dep = stack.pop()
        if dep in seen:
            continue
        seen.add(dep)
        if dep in packages:
            stack.extend(packages[dep].depends)
    return seen


def dependency_path(packages: dict[str, Package], start: str, target: str) -> list[str] | None:
    queue: list[tuple[str, list[str]]] = [(start, [start])]
    seen = {start}
    while queue:
        current, path = queue.pop(0)
        for dep in packages.get(current, Package(current, "", "", Path(), (), "", False, (), ())).depends:
            if dep == target:
                return path + [target]
            if dep not in seen:
                seen.add(dep)
                queue.append((dep, path + [dep]))
    return None


def valid_version(version: str) -> bool:
    return bool(re.fullmatch(r"[0-9][0-9A-Za-z.+_~-]*", version))


def iter_package_files(package_root: Path = DEFAULT_PACKAGE_ROOT) -> Iterable[Path]:
    yield from sorted(package_root.glob("*/package.yml"))
