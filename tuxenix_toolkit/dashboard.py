from __future__ import annotations

from html import escape
from pathlib import Path

from .packages import Package


STYLE = """
body { font-family: system-ui, sans-serif; margin: 0; background: #fafafa; color: #20252b; }
header { padding: 24px 32px; background: #22313f; color: white; }
main { padding: 24px 32px; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat { background: white; border: 1px solid #d7dde4; padding: 14px; }
.stat strong { display: block; font-size: 28px; }
table { width: 100%; border-collapse: collapse; background: white; }
th, td { border-bottom: 1px solid #d7dde4; padding: 10px; text-align: left; }
th { background: #eef2f6; }
.ok { color: #0a7b34; font-weight: 700; }
.miss { color: #9a3412; font-weight: 700; }
"""


def repo_archives(repo_root: Path, package: Package) -> tuple[Path, ...]:
    package_repo = repo_root / package.name
    if not package_repo.exists():
        return ()
    patterns = ("*.txpk.tar.bz2", "*.txpk.tar.gz", "*.txpk.tar.xz")
    found: list[Path] = []
    for pattern in patterns:
        found.extend(package_repo.glob(f"*/{pattern}"))
    return tuple(sorted(found))


def write_dashboard(packages: dict[str, Package], output: Path, repo_root: Path | None = None) -> None:
    archive_map = {
        package.name: package.dist_archives or (repo_archives(repo_root, package) if repo_root else ())
        for package in packages.values()
    }
    built = [package for package in packages.values() if archive_map[package.name]]
    missing_build = [package for package in packages.values() if not package.has_build_script]
    missing_src = [package for package in packages.values() if not package.source_archives]
    rows = []
    for package in sorted(packages.values(), key=lambda item: item.name):
        archives = archive_map[package.name]
        status = '<span class="ok">built</span>' if archives else '<span class="miss">no archive</span>'
        src = ", ".join(escape(path.name) for path in package.source_archives) or '<span class="miss">missing</span>'
        dist = ", ".join(escape(path.name) for path in archives) or '<span class="miss">missing</span>'
        rows.append(
            "<tr>"
            f"<td><strong>{escape(package.name)}</strong></td>"
            f"<td>{escape(package.version)}</td>"
            f"<td>{status}</td>"
            f"<td>{src}</td>"
            f"<td>{dist}</td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Tuxenix Build Dashboard</title>
<style>{STYLE}</style>
<header>
  <h1>Tuxenix Build Dashboard</h1>
  <p>Recipe and artifact status from the package source tree.</p>
</header>
<main>
  <section class="stats">
    <div class="stat"><strong>{len(packages)}</strong>packages</div>
    <div class="stat"><strong>{len(built)}</strong>with dist archives</div>
    <div class="stat"><strong>{len(missing_src)}</strong>missing source archive</div>
    <div class="stat"><strong>{len(missing_build)}</strong>missing build.sh</div>
  </section>
  <table>
    <thead><tr><th>Package</th><th>Version</th><th>Status</th><th>Sources</th><th>Dist Archives</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</main>
</html>
"""
    output.write_text(html)
