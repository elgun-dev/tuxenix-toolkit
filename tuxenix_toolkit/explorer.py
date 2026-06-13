from __future__ import annotations

from html import escape
from pathlib import Path

from .packages import Package, reverse_dependencies


STYLE = """
body { font-family: system-ui, sans-serif; margin: 0; color: #172026; background: #f7f8fa; }
header { background: #15191f; color: white; padding: 24px 32px; }
main { padding: 24px 32px; }
table { border-collapse: collapse; width: 100%; background: white; }
th, td { border-bottom: 1px solid #d8dde3; padding: 10px; text-align: left; vertical-align: top; }
th { background: #eef1f5; position: sticky; top: 0; }
.pill { display: inline-block; background: #e7f0ff; color: #17457a; padding: 2px 6px; border-radius: 6px; margin: 1px; }
.muted { color: #64717d; }
input { width: 100%; max-width: 520px; padding: 10px; margin-bottom: 16px; border: 1px solid #b8c0c8; }
"""


SCRIPT = """
const search = document.querySelector("#search");
const rows = [...document.querySelectorAll("tbody tr")];
search.addEventListener("input", () => {
  const q = search.value.toLowerCase();
  for (const row of rows) {
    row.style.display = row.innerText.toLowerCase().includes(q) ? "" : "none";
  }
});
"""


def write_explorer(packages: dict[str, Package], output: Path) -> None:
    reverse = reverse_dependencies(packages)
    rows = []
    for package in sorted(packages.values(), key=lambda item: item.name):
        deps = " ".join(f'<span class="pill">{escape(dep)}</span>' for dep in package.depends) or '<span class="muted">none</span>'
        rdeps = " ".join(f'<span class="pill">{escape(dep)}</span>' for dep in sorted(reverse.get(package.name, []))) or '<span class="muted">none</span>'
        rows.append(
            "<tr>"
            f"<td><strong>{escape(package.name)}</strong><br><span class=\"muted\">{escape(str(package.path))}</span></td>"
            f"<td>{escape(package.version)}</td>"
            f"<td>{deps}</td>"
            f"<td>{rdeps}</td>"
            f"<td>{escape(package.comment)}</td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Tuxenix Package Explorer</title>
<style>{STYLE}</style>
<header>
  <h1>Tuxenix Package Explorer</h1>
  <p>{len(packages)} package recipes indexed from package.yml metadata.</p>
</header>
<main>
  <input id="search" placeholder="Search package, dependency, path, or comment">
  <table>
    <thead><tr><th>Package</th><th>Version</th><th>Deps</th><th>Reverse Deps</th><th>Purpose</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</main>
<script>{SCRIPT}</script>
</html>
"""
    output.write_text(html)
