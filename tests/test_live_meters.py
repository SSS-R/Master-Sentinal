"""Unit tests for the live network meter and speed-test helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.live_meters import (
    NetworkSpeedMeter,
    SpeedTestResult,
    format_rate,
)


class TestFormatRate:
    def test_bytes(self):
        assert format_rate(512) == "512 B/s"

    def test_kilobytes(self):
        assert format_rate(2048) == "2.0 KB/s"

    def test_megabytes(self):
        assert format_rate(5 * 1024 * 1024) == "5.0 MB/s"

    def test_negative_clamped(self):
        assert format_rate(-100) == "0 B/s"


class TestNetworkSpeedMeter:
    def test_first_sample_is_zero(self):
        meter = NetworkSpeedMeter()
        with patch("services.live_meters.psutil.net_io_counters") as counters:
            counters.return_value = MagicMock(bytes_sent=1000, bytes_recv=2000)
            rate = meter.sample()
        assert rate.download_bps == 0.0
        assert rate.upload_bps == 0.0

    def test_second_sample_computes_delta(self):
        meter = NetworkSpeedMeter()
        with patch("services.live_meters.psutil.net_io_counters") as counters, \
             patch("services.live_meters.time.monotonic") as clock:
            counters.return_value = MagicMock(bytes_sent=1000, bytes_recv=2000)
            clock.return_value = 100.0
            meter.sample()
            counters.return_value = MagicMock(bytes_sent=1000 + 500, bytes_recv=2000 + 4000)
            clock.return_value = 102.0  # 2 seconds later
            rate = meter.sample()
        assert rate.download_bps == 2000.0  # 4000 bytes / 2s
        assert rate.upload_bps == 250.0  # 500 bytes / 2s

    def test_counter_reset_clamps_to_zero(self):
        meter = NetworkSpeedMeter()
        with patch("services.live_meters.psutil.net_io_counters") as counters, \
             patch("services.live_meters.time.monotonic") as clock:
            counters.return_value = MagicMock(bytes_sent=5000, bytes_recv=9000)
            clock.return_value = 10.0
            meter.sample()
            # Adapter reconnect resets counters lower than before.
            counters.return_value = MagicMock(bytes_sent=10, bytes_recv=20)
            clock.return_value = 11.0
            rate = meter.sample()
        assert rate.download_bps == 0.0
        assert rate.upload_bps == 0.0


class TestSpeedTestResult:
    def test_success_summary(self):
        result = SpeedTestResult(success=True, download_mbps=120.5, upload_mbps=33.2)
        assert "120.5" in result.summary
        assert "33.2" in result.summary

    def test_failure_summary(self):
        result = SpeedTestResult(success=False, error="no connection")
        assert "failed" in result.summary.lower()
        assert "no connection" in result.summary
