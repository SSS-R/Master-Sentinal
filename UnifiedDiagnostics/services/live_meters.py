"""Live network throughput meter and an on-demand internet speed test.

Two distinct things live here, both about "internet speed":

* :class:`NetworkSpeedMeter` — a cheap, always-on *throughput* meter. It reads
  psutil's cumulative byte counters and divides the delta by the elapsed wall
  time, giving the live up/down rate (what Task Manager's network graph shows).
  Safe to call on the fast monitor loop; it holds no resources.

* :class:`SpeedTester` — an on-demand *capacity* test. It downloads and uploads
  a fixed payload against Cloudflare's public speed endpoints and reports the
  achieved Mbps. This is a deliberate, ~10-20s operation, not a live metric, so
  it runs only when the user asks. It uses ``urllib`` (standard library) so the
  packaged build gains no extra dependency.
"""

from __future__ import annotations

import ssl
import time
import urllib.request
from dataclasses import dataclass

import psutil

from services.app_logging import get_logger

LOGGER = get_logger(__name__)


def format_rate(bytes_per_sec: float) -> str:
    """Format a byte/second rate into a compact human-readable string."""
    if bytes_per_sec < 0:
        bytes_per_sec = 0.0
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    value = float(bytes_per_sec)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{value:.0f} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


@dataclass(frozen=True)
class NetworkRate:
    """Instantaneous network throughput in bytes per second."""

    download_bps: float = 0.0
    upload_bps: float = 0.0

    @property
    def download_text(self) -> str:
        return format_rate(self.download_bps)

    @property
    def upload_text(self) -> str:
        return format_rate(self.upload_bps)


class NetworkSpeedMeter:
    """Computes live up/down throughput from psutil's cumulative counters.

    The first reading establishes a baseline and returns a zero rate; every
    reading after that returns the delta since the previous call divided by the
    elapsed time. Thread-confined to the caller (the fast monitor loop).
    """

    def __init__(self) -> None:
        self._last_sent: int | None = None
        self._last_recv: int | None = None
        self._last_time: float | None = None

    def sample(self) -> NetworkRate:
        """Return the throughput since the previous :meth:`sample` call."""
        try:
            counters = psutil.net_io_counters()
        except Exception as exc:  # pragma: no cover - platform dependent
            LOGGER.debug("net_io_counters failed: %s", exc)
            return NetworkRate()

        now = time.monotonic()
        sent = int(counters.bytes_sent)
        recv = int(counters.bytes_recv)

        if self._last_time is None or self._last_sent is None or self._last_recv is None:
            self._last_sent, self._last_recv, self._last_time = sent, recv, now
            return NetworkRate()

        elapsed = now - self._last_time
        if elapsed <= 0:
            return NetworkRate()

        # Counters can reset (adapter reconnect, counter rollover); clamp to 0.
        down = max(0, recv - self._last_recv) / elapsed
        up = max(0, sent - self._last_sent) / elapsed

        self._last_sent, self._last_recv, self._last_time = sent, recv, now
        return NetworkRate(download_bps=down, upload_bps=up)


@dataclass(frozen=True)
class SpeedTestResult:
    """Result of an on-demand internet capacity test."""

    success: bool
    download_mbps: float = 0.0
    upload_mbps: float = 0.0
    error: str = ""

    @property
    def summary(self) -> str:
        if not self.success:
            return f"Speed test failed: {self.error or 'unknown error'}"
        return f"Download {self.download_mbps:.1f} Mbps  |  Upload {self.upload_mbps:.1f} Mbps"


class SpeedTester:
    """On-demand download/upload capacity test via Cloudflare speed endpoints."""

    DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes={bytes}"
    UPLOAD_URL = "https://speed.cloudflare.com/__up"
    DOWNLOAD_BYTES = 10_000_000  # 10 MB
    UPLOAD_BYTES = 5_000_000  # 5 MB
    TIMEOUT_SEC = 30

    def run(self) -> SpeedTestResult:
        """Run a download then an upload test and return achieved Mbps."""
        try:
            download_mbps = self._measure_download()
            upload_mbps = self._measure_upload()
        except Exception as exc:
            LOGGER.warning("Speed test failed: %s", exc)
            return SpeedTestResult(success=False, error=str(exc))
        return SpeedTestResult(
            success=True,
            download_mbps=download_mbps,
            upload_mbps=upload_mbps,
        )

    def _context(self) -> ssl.SSLContext:
        return ssl.create_default_context()

    def _measure_download(self) -> float:
        url = self.DOWNLOAD_URL.format(bytes=self.DOWNLOAD_BYTES)
        request = urllib.request.Request(url, headers={"User-Agent": "MasterSentinal/SpeedTest"})
        start = time.monotonic()
        total = 0
        with urllib.request.urlopen(request, timeout=self.TIMEOUT_SEC, context=self._context()) as response:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
        elapsed = max(time.monotonic() - start, 1e-6)
        return (total * 8) / elapsed / 1_000_000

    def _measure_upload(self) -> float:
        payload = b"\x00" * self.UPLOAD_BYTES
        request = urllib.request.Request(
            self.UPLOAD_URL,
            data=payload,
            headers={
                "User-Agent": "MasterSentinal/SpeedTest",
                "Content-Type": "application/octet-stream",
            },
            method="POST",
        )
        start = time.monotonic()
        with urllib.request.urlopen(request, timeout=self.TIMEOUT_SEC, context=self._context()) as response:
            response.read()
        elapsed = max(time.monotonic() - start, 1e-6)
        return (len(payload) * 8) / elapsed / 1_000_000
