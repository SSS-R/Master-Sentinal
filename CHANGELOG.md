# Changelog

All notable changes to Master Sentinal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
