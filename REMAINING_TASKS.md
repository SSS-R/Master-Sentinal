# Remaining Tasks

This document tracks the major work still left for `Master Sentinal` before it is polished as a reliable open source PC diagnostics application.

## Current Priorities

### 1. Finish the typed-data refactor

- [x] Make GPU collection use `GPUDevice` as the primary implementation instead of collecting dicts first.
- [x] Make disk collection use `DiskPartition` and `SmartDriveStatus` as the primary implementation instead of converting from dicts.
- [x] Reduce legacy `get_*_info()` dict methods to thin compatibility wrappers only.
- [x] Add typed models for CPU info, board info, and full scan results.
- [ ] Remove remaining string-key assumptions from the UI and services. Live snapshot, dashboard, static CPU/board, and CSV export paths are typed; legacy callers still need review.

### 2. Improve diagnostics depth

- [x] Add Windows Update health checks.
- [x] Add Event Viewer critical error summary.
- [x] Add Reliability Monitor / crash-history summary.
- [x] Add network diagnostics: adapter state, DNS, gateway, internet reachability.
- [x] Add storage diagnostics beyond basic SMART display: warning extraction, temperature if available, drive type.
- [x] Add security diagnostics: Defender status, firewall status, BitLocker status.
- [x] Add startup-impact and background-service checks.

### 3. Turn metrics into clearer diagnosis

- [x] Add a health score or severity rollup for the whole system.
- [x] Add recommended actions for each finding.
- [x] Distinguish between transient load and persistent problems.
- [x] Add unsupported vs error vs warning states more explicitly.
- [x] Detect likely false positives for laptops vs desktops.

## UI Tasks

### Dashboard

- [x] Replace encoded/misaligned text artifacts in the UI.
- [x] Show health findings with badges, icons, or stronger severity styling.
- [x] Add empty states for unavailable diagnostics instead of generic placeholders.
- [x] Add loading states for first snapshot collection.
- [x] Improve spacing and responsiveness for smaller screens.

### Full Scan

- [x] Show scan duration and progress more clearly.
- [x] Add richer scan result messages instead of truncating long output to `OK`.
- [x] Save detailed logs for each scan task.
- [x] Group scan tools by category: system repair, storage, power, advanced tools.
- [x] Add confirmation text for risky tools like Driver Verifier.

### Reports

- [x] Add HTML report export.
- [x] Add JSON export for bug reports and community issue templates.
- [x] Include app version, timestamp, OS version, and privilege level in exports.
- [x] Include health findings and recommended actions in a cleaner format.

## Reliability Tasks

- [x] Add structured logging instead of `print(...)`.
- [x] Add a dedicated error-reporting path for diagnostics that fail.
- [x] Ensure every background task has safe shutdown behavior.
- [x] Add timeout handling around shell-based diagnostics where appropriate.
- [x] Review WMI and subprocess failure handling for clearer user-facing messages.

## Testing Tasks

- [x] Restore a working Python environment for local test runs.
- [x] Add tests for board diagnostics.
- [x] Add more tests for GPU collection paths, including WMI fallback.
- [x] Add tests for typed disk and SMART model conversion.
- [x] Add tests for the Tkinter update path where practical.
- [x] Add regression tests for the health analyzer rules.
- [x] Add CI so pull requests run tests automatically.

## Build And Packaging Tasks

- [x] Fix the broken local virtual environment in the repository.
- [x] Remove machine-specific assumptions from packaging artifacts.
- [x] Clean up the PyInstaller flow so contributors can build on their own machines.
- [x] Separate runtime, development, and build dependencies.
- [x] Remove unused dependencies if they are no longer needed.
- [x] Add an app icon and version metadata to the build output.

## Open Source Readiness

- [x] Clean the README encoding issues.
- [x] Replace placeholder repository/user information in docs.
- [x] Add screenshots or GIFs.
- [x] Add contribution guidelines (`CONTRIBUTING.md`).
- [x] Add an issue template and pull request template.
- [x] Add a code of conduct.
- [x] Document supported Windows versions and permissions requirements.
- [x] Document which diagnostics are safe, risky, or reboot-triggering.

## Nice Next Features

- Background monitoring history graphs.
- Optional health alerts for high temperature or low disk space.
- Scan presets: quick, standard, deep, advanced.
- Save and compare snapshots over time.
- Portable issue bundle export for support/community debugging.

## Known Blockers

- Several diagnostics still rely on legacy dict payloads internally.

## Suggested Order

1. Fix the Python environment and test execution.
2. Finish the typed-data refactor in GPU and disk modules.
3. Clean README/build/package setup for contributor use.
4. Expand diagnostics coverage.
5. Improve report quality and health recommendations.
6. Add CI and open source contribution scaffolding.
