# Changelog

All notable changes to Master Sentinal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-06-26

### Fixed
- **Scans now produce a readable report, not a raw Windows file.** The Power
  Efficiency check used to drop the user into Windows' raw `powercfg /energy`
  HTML, where harmless, deliberate settings (High Performance power plan, USB
  selective suspend, an app keeping the PC awake during the test) are styled as
  red "Errors." That was misleading. The raw report is now parsed into a plain-
  language summary that correctly frames those entries as power-saving
  *suggestions*, not faults — and the raw file is written to a temp location
  instead of the app folder so it is no longer mistaken for the app's own report.

### Added
- **Automatic scan report.** When a health scan finishes, Master Sentinal now
  generates its own plain-language HTML report (health summary, findings, and
  per-check results) under `Documents\Master Sentinal Reports\` and opens it
  automatically. A **View Scan Report** button on the Full Scan screen reopens
  the latest one.

## [1.1.0] - 2026-06-20

### Performance
- **Major: split live monitoring into fast and deep tiers.** Cheap metrics
  (CPU, RAM, per-core, disk usage) continue to refresh every 2 seconds, while
  the expensive PowerShell/WMI diagnostics (Windows Update, Event Log,
  Reliability, Network, Storage, Security, Startup, form factor, SMART) now
  collect once at startup and then on a slow background timer or manual refresh.
  Previously every one of these ran on the 2-second loop, which made the app
  slow to a crawl on machines with many services, large event logs, or
  aggressive antivirus — even though it felt fast on a clean developer PC.
- The deep diagnostics now run concurrently (thread pool) instead of serially,
  turning total collection time from the sum of all calls into roughly the
  slowest single call.
- Cached the GPU WMI fallback so machines without `nvidia-smi` no longer rebuild
  a WMI connection on every tick.

### Fixed
- **Cross-device reliability:** all PowerShell diagnostics now force UTF-8 on
  both ends. Previously output containing non-ASCII text (localized service or
  device names, event messages) could fail to decode on non-English Windows,
  silently breaking that diagnostic on other people's machines.
- **Safety:** Deep Scan now confirms before launching advanced tools (Driver
  Verifier, Memory Diagnostic) instead of running them silently as part of the
  batch.
- Corrected misleading scan time estimates (e.g. "Quick Scan 2 min" actually
  runs a full `sfc /scannow`).
- Monitoring alerts no longer fire exactly once and then go silent forever; a
  sustained condition now re-alerts at most once per 5 minutes.
- `GPUDevice` gained a numeric `temperature_c`, fixing a latent crash path where
  snapshot history referenced a non-existent attribute and silently failed.

### Added
- **Real GPU temperature alerts:** the monitoring service now warns when a GPU
  runs hot (warn 85°C, critical 92°C). Previously the temperature check was a
  no-op placeholder that never fired. CPU/fan/voltage sensors are deferred until
  a signed build can ship the sensor driver without antivirus flags.
- **Anonymized diagnostic bundle:** export now offers to scrub your Windows
  username, PC name, and hardware serial numbers so bundles are safe to share
  publicly (e.g. on GitHub issues). The bundle README states its redaction
  status.
- Plain-language "What's going on with your PC" summary at the top of HTML
  reports, translating the health findings into everyday terms with clear
  next steps.
- About & Support section (version, license, GitHub link, optional donations).

### Changed
- Issue bundle export now runs on a background thread so the UI stays responsive.
- Removed personal working-directory path from report metadata.
- Removed ~1,000 lines of dead, duplicated diagnostic modules and the unused
  `GPUtil` dependency.

## [1.0.0] - 2026-04-22

### Added

#### Core Application
- Main application window with CustomTkinter modern UI
- Live dashboard showing real-time system metrics
- Full system health scan with guided repair tools
- Report export functionality (CSV, HTML, JSON)

#### Diagnostic Modules
- CPU diagnostics with health analysis
- GPU diagnostics with SMART status
- Disk diagnostics with partition and SMART data
- RAM diagnostics and memory health
- Motherboard/board diagnostics
- Security status (Defender, firewall, BitLocker)
- Network diagnostics (adapter state, DNS, gateway)
- Storage health with temperature monitoring
- Windows Update health checks
- Event Viewer critical error summary
- Startup impact and background service checks
- Driver diagnostics and verification tools

#### Services
- `LiveSnapshotService` - real-time system metric collection
- `HealthAnalyzer` - severity scoring and recommendations
- `FullScanService` - comprehensive system health scans
- `ReportExporter` - multi-format report generation
- `IssueBundleExporter` - diagnostic data bundling
- `DiagnosticRuntime` - safe diagnostic execution with timeouts
- `AppLogging` - structured logging throughout the app
- `SnapshotHistory` - historical snapshot storage
- `MonitoringAlerts` - threshold-based alerting foundation
- `ScanPresets` - configurable scan profiles

#### Data Models
- Typed data models for all diagnostic categories
- `DiagnosticResult` - standardized result format
- `HealthFinding` - severity, persistence, recommendations
- `SystemSnapshot` - complete system health state
- `GPUDevice`, `DiskPartition`, `SmartDriveStatus` - hardware models
- `CPUInfo`, `BoardInfo` - system information models

#### UI Components
- Dashboard with live metric cards
- Full scan view with progress tracking
- Report export dialog
- Component sections for each diagnostic category
- Loading states and empty states

#### Developer Experience
- GitHub Actions CI for automated testing
- Comprehensive test suite (12+ test files)
- Type hints throughout the codebase
- Structured project layout
- Development and production dependency separation

#### Documentation
- README with setup and usage instructions
- CONTRIBUTING.md with contribution guidelines
- CODE_OF_CONDUCT.md
- Pull request template
- Diagnostic permissions and safety documentation
- Screenshots and visual guides

#### Packaging
- PyInstaller single-executable build
- Windows version metadata
- Application icon and branding
- Administrator manifest for elevation

### Changed
- Refactored from dict-based to typed data models throughout
- Improved diagnostics reliability with better error handling
- Enhanced WMI fallback mechanisms
- Streamlined legacy compatibility wrappers

### Fixed
- README encoding issues
- Machine-specific build assumptions
- Virtual environment portability
- UI text artifacts and alignment issues

## [0.1.0] - 2026-02-03

### Added
- Initial diagnostic framework
- Core modules for disk, GPU, CPU, and RAM
- Basic health analyzer
- Full system scan functionality
- Unit test foundation

---

## Migration Guide

### From 0.x to 1.0.0

The 1.0.0 release includes a major refactor to typed data models. If you have existing code or plugins:

- All diagnostic results now use typed models instead of dictionaries
- Access properties via attributes, not string keys: `result.cpu.usage` not `result['cpu']['usage']`
- Legacy dict access is available via `.to_dict()` compatibility method on models
