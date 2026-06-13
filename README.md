# Tuxenix Toolkit

Practical tooling for Tuxenix package work, dependency analysis, build visibility, and QEMU boot testing.

This repo turns the day-to-day distro work into reusable tools:

- package recipe linter
- dependency graph generator
- package explorer HTML report
- build dashboard HTML report
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
