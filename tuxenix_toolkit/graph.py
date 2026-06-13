from __future__ import annotations

from pathlib import Path

from .packages import Package, dependency_path, reverse_dependencies, transitive_dependencies


def _node(name: str) -> str:
    return name.replace("-", "_").replace("+", "plus").replace(".", "_")


def write_mermaid_graph(packages: dict[str, Package], output: Path) -> None:
    lines = ["flowchart LR"]
    for package in sorted(packages.values(), key=lambda item: item.name):
        if not package.depends:
            lines.append(f'  {_node(package.name)}["{package.name}"]')
            continue
        for dep in sorted(package.depends):
            lines.append(f'  {_node(package.name)}["{package.name}"] --> {_node(dep)}["{dep}"]')
    output.write_text("\n".join(lines) + "\n")


def write_systemd_report(packages: dict[str, Package], output: Path) -> None:
    direct = sorted(name for name, package in packages.items() if "systemd" in package.depends)
    transitive = sorted(name for name in packages if "systemd" in transitive_dependencies(packages, name))
    reverse = reverse_dependencies(packages)
    leaf = sorted(name for name in packages if not reverse.get(name))

    lines = [
        "# Tuxenix Dependency Report",
        "",
        f"Packages scanned: {len(packages)}",
        f"Direct systemd deps: {len(direct)}",
        f"Transitive systemd deps: {len(transitive)}",
        f"Leaf packages: {len(leaf)}",
        "",
        "## Direct systemd dependencies",
        "",
    ]
    lines.extend(f"- {name}" for name in direct)
    lines.extend(["", "## Transitive systemd paths", ""])
    for name in transitive:
        path = dependency_path(packages, name, "systemd")
        if path:
            lines.append(f"- {' -> '.join(path)}")
    lines.extend(["", "## Leaf packages", ""])
    lines.extend(f"- {name}" for name in leaf)
    output.write_text("\n".join(lines) + "\n")
