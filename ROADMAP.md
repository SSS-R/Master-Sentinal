# Master Sentinal - Product Roadmap

This document outlines future enhancements and improvements planned for Master Sentinal.

## Version 1.1.0 - Enhanced Monitoring

### Background Monitoring
- [ ] System health history tracking with persistent storage
- [ ] Time-series graphs for CPU, memory, GPU, and disk usage
- [ ] Configurable monitoring intervals (1min, 5min, 15min, 1hour)
- [ ] Export monitoring history to CSV/JSON

### Health Alerts
- [ ] Configurable temperature thresholds with visual warnings
- [ ] Low disk space alerts with configurable percentage
- [ ] High memory usage notifications
- [ ] Optional system tray notifications

## Version 1.2.0 - Scan Improvements

### Scan Presets
- [ ] Quick Scan (5 min) - essential health checks only
- [ ] Standard Scan (15 min) - recommended for routine use
- [ ] Deep Scan (45 min) - comprehensive system analysis
- [ ] Advanced Scan - full diagnostics with risky tools

### Smart Diagnostics
- [ ] Automatic detection of laptop vs desktop for context-aware findings
- [ ] SSD vs HDD-aware storage recommendations
- [ ] Gaming PC vs workstation optimization suggestions
- [ ] Detection of transient vs persistent issues

## Version 1.3.0 - Reporting & Export

### Report Enhancements
- [ ] PDF export format
- [ ] Customizable report templates
- [ ] Include screenshots in reports
- [ ] One-click issue bundle for GitHub/bug reports

### Comparison Features
- [ ] Compare current scan with previous scans
- [ ] Trend analysis for recurring issues
- [ ] Before/after comparison for repairs

## Version 1.4.0 - Community & Support

### Issue Bundle Export
- [ ] Portable diagnostic bundle for community debugging
- [ ] Anonymized export option (strip sensitive data)
- [ ] Direct upload to support forums or GitHub

### Plugin Architecture
- [ ] Community-contributed diagnostic modules
- [ ] Plugin marketplace or registry
- [ ] Safe sandboxing for third-party diagnostics

## Version 2.0.0 - Platform Expansion

### Cross-Platform Support
- [ ] Linux support (Ubuntu, Fedora, Arch)
- [ ] macOS support (Intel and Apple Silicon)
- [ ] Unified codebase with platform-specific modules

### Advanced Features
- [ ] Driver update recommendations (safe sources only)
- [ ] Startup program impact scoring
- [ ] Network troubleshooting wizard
- [ ] Windows Update troubleshooter integration

## Contributing

Ideas and contributions are welcome! Please:

1. Open a [GitHub Issue](https://github.com/SSS-R/Master-Sentinal/issues) to discuss features
2. Review [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines
3. Check existing issues to avoid duplicates

## Prioritization

Features are prioritized based on:
- User feedback and requests
- Community contribution availability
- Technical feasibility and safety
- Alignment with the project's core diagnostics mission

## Not Planned

The following are explicitly out of scope:

- Antivirus or security software (use Windows Defender)
- Registry cleaning or "system optimization" tools
- Driver downloading or automatic driver updates
- Any modifications that could compromise system stability without clear warnings
