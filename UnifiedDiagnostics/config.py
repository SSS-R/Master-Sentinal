"""
Central configuration for Master Sentinal.

All tuneable constants live here so they can be changed in one place.
"""

# Monitoring
# Fast metrics (CPU, RAM, per-core, disk usage) are cheap psutil reads and
# refresh on this interval.
UPDATE_INTERVAL_SEC: int = 2

# Deep diagnostics (the PowerShell/WMI collectors: Windows Update, Event Log,
# Reliability, Network, Storage, Security, Startup, form factor + SMART) are
# expensive and slow-changing, so they refresh on a much slower cadence in the
# background. They can always be refreshed on demand from each tab.
DEEP_REFRESH_INTERVAL_SEC: int = 300

# Temperature alerts
TEMP_ALERT_THRESHOLD_C: int = 90

# Appearance
APPEARANCE_MODE: str = "Dark"
COLOR_THEME: str = "blue"

# Window
APP_VERSION: str = "1.3.0"
WINDOW_TITLE: str = "Master Sentinal"
WINDOW_GEOMETRY: str = "1100x700"

# Project links (shown in the System tab's About section)
REPO_URL: str = "https://github.com/SSS-R/Master-Sentinal"
# Optional donations link. Master Sentinal is free and open source; donations
# are entirely optional. Point this at GitHub Sponsors / Ko-fi / etc. when ready
# (falls back to the repo's README so the button always works).
DONATE_URL: str = "https://github.com/SSS-R/Master-Sentinal#support"
