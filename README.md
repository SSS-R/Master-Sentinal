# Master Sentinal

[![Tests](https://github.com/SSS-R/Master-Sentinal/actions/workflows/tests.yml/badge.svg)](https://github.com/SSS-R/Master-Sentinal/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](https://www.python.org/)
[![Version 1.1.0](https://img.shields.io/badge/Version-1.1.0-blueviolet.svg)](CHANGELOG.md)

**Master Sentinal** is a free, open source Windows diagnostics hub. It gives you a
live system dashboard, a guided health scan with real repair tools, and shareable
reports — all in one app, with no telemetry and no upsell.

It is built for the moment something feels *off* with a PC and you want a clear,
honest answer: what's wrong, how serious it is, and what to do next — in plain
language, not jargon.

## Highlights

- **Live dashboard** — CPU, memory, GPU, disk, and motherboard metrics that refresh
  in real time, split into fast (2-second) and deep (background) tiers so the app
  stays responsive even on busy or heavily-protected machines.
- **Plain-language health overview** — findings are scored by severity and
  persistence, then translated into everyday terms with concrete next steps.
- **Guided health scan** — runs routine Windows repair checks (SFC, DISM, CHKDSK,
  power & battery diagnostics) together, with honest time estimates.
- **Advanced tools, handled safely** — Driver Verifier and Windows Memory
  Diagnostic are kept separate and always ask for confirmation before they run.
- **Real GPU temperature alerts** — warns at 85 °C and flags critical at 92 °C.
- **Shareable reports** — export the current snapshot to CSV, HTML, or JSON.
- **Anonymized diagnostic bundles** — one click scrubs your username, PC name, and
  hardware serials so you can safely attach a bundle to a public bug report.

## Screenshots

| Live Dashboard | Guided Health Scan |
| --- | --- |
| ![Dashboard overview](docs/screenshots/dashboard-overview.png) | ![Health scan view](docs/screenshots/full-scan.png) |

## Download And Run

You do **not** need Python to use the packaged app.

1. Open the [Releases](https://github.com/SSS-R/Master-Sentinal/releases) page.
2. Download the latest `Master Sentinal.exe`.
3. Launch it and approve the Windows elevation prompt when shown.

The packaged build requests administrator rights because several Windows
diagnostics require elevation. Read-only dashboard metrics work without it.

## Run From Source

### Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- PowerShell

### Setup

```powershell
git clone https://github.com/SSS-R/Master-Sentinal.git
cd "Master-Sentinal"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

> Just running the app? Use `requirements-runtime.txt` instead of
> `requirements-dev.txt` to skip the test and build tooling.

### Start The App

```powershell
python .\UnifiedDiagnostics\main.py
```

### Run Tests

```powershell
python -m pytest
```

### Build The Executable

```powershell
python .\build_app.py
```

The packaged executable is written to `dist\Master Sentinal.exe`.

## How It Works

Master Sentinal collects system state through native Windows interfaces — `psutil`,
WMI, and targeted PowerShell/`wmic` queries — and feeds it through a health
analyzer that assigns each finding a severity and a persistence flag (is this a
one-off blip or a recurring problem?).

Live monitoring runs in two tiers:

- **Fast tier (every ~2 s):** cheap metrics — CPU, RAM, per-core load, disk usage.
- **Deep tier (startup + background/manual refresh):** the expensive checks —
  Windows Update, Event Log, Reliability, Network, Storage SMART, Security,
  Startup impact, and form-factor detection — collected concurrently so total time
  is roughly the slowest single call rather than the sum of all of them.

All PowerShell diagnostics force UTF-8 on both ends so localized (non-English)
Windows device and event names decode correctly.

## Permissions And Diagnostic Safety

Master Sentinal mixes safe read-only checks with a few tools that can change system
state or require a reboot. Nothing risky runs without an explicit confirmation.

| Area | Requires admin | Notes |
| --- | --- | --- |
| Live dashboard metrics | Usually no | Some Security and BitLocker details are limited without elevation |
| Routine health scan | Yes | SFC, DISM, CHKDSK, and power diagnostics need admin access |
| Driver Verifier | Yes | Advanced troubleshooting; can make a system unstable — asks first |
| Memory Diagnostic | Yes | Schedules a reboot-based memory test — asks first |
| Report / bundle export | No | Exports the current snapshot to CSV, HTML, or JSON |

See [docs/diagnostics-and-permissions.md](docs/diagnostics-and-permissions.md) for a
fuller command safety guide.

## Supported Windows Versions

- Windows 10
- Windows 11

Most live metrics work on current Windows 10 and 11 installs. Some deeper
diagnostics depend on local Windows components, available services, hardware
support, or admin access.

## Project Layout

- `UnifiedDiagnostics/` — application code (UI, services, models, modules)
- `tests/` — automated tests
- `packaging/` — Windows version metadata and packaging assets
- `docs/` — diagnostic/permission docs and screenshots
- `.github/` — CI workflows and repository templates

## Support

Master Sentinal is free and open source, and it will always be free. If it helped
you, the best ways to support the project are:

- ⭐ Star the repository on GitHub so more people find it
- 🐛 Report bugs or suggest features via [Issues](https://github.com/SSS-R/Master-Sentinal/issues)
- 🔧 Contribute code — see [CONTRIBUTING.md](CONTRIBUTING.md)
- ❤️ Optional donations are welcome but never required

When reporting a bug, attach a diagnostic bundle (Dashboard → **Export Diagnostic
Bundle**). Choose **Anonymize** when prompted to automatically remove your Windows
username, PC name, and hardware serial numbers before sharing.

## Roadmap & Changelog

- See [CHANGELOG.md](CHANGELOG.md) for what shipped in each release.
- See [ROADMAP.md](ROADMAP.md) for what's planned next.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

This project is licensed under the [MIT License](LICENSE).
