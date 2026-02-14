"""
Central configuration for Master Sentinal.

All tuneable constants live here so they can be changed in one place.
"""

# Monitoring
UPDATE_INTERVAL_SEC: int = 2

# Temperature alerts
TEMP_ALERT_THRESHOLD_C: int = 90

# Appearance
APPEARANCE_MODE: str = "Dark"
COLOR_THEME: str = "blue"

# Window
WINDOW_TITLE: str = "Master Sentinal"
WINDOW_GEOMETRY: str = "1100x700"
