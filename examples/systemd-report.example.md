# Tuxenix Dependency Report

Example output shape from:

```sh
./tuxenix-toolkit graph --systemd-report systemd-report.md
```

```text
Packages scanned: 419
Direct systemd deps: 7
Transitive systemd deps: 13
```

The report lists paths such as:

```text
pcmanfm -> gtk3 -> at-spi2-core -> dbus -> systemd
```
