"""Typed diagnostic models used by modules and services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CPUInfo:
    """Structured static CPU information with optional collection error."""

    name: str = ""
    cores: int | None = None
    threads: int | None = None
    max_clock_speed_text: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when CPU info collection failed."""
        return self.error_message is not None

    def as_dict(self) -> dict[str, str | int]:
        """Return the legacy dict representation expected by older callers."""
        if self.error_message:
            return {"Error": self.error_message}

        info: dict[str, str | int] = {}
        if self.name:
            info["Name"] = self.name
        if self.cores is not None:
            info["Cores"] = self.cores
        if self.threads is not None:
            info["Threads"] = self.threads
        if self.max_clock_speed_text:
            info["MaxClockSpeed"] = self.max_clock_speed_text
        return info

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        return {key: str(value) for key, value in self.as_dict().items()}


@dataclass(frozen=True)
class BoardInfo:
    """Structured motherboard, BIOS, and OS platform information."""

    system: str = ""
    node_name: str = ""
    release: str = ""
    version: str = ""
    machine: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    bios_version: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when board or BIOS collection hit an error."""
        return self.error_message is not None

    def as_dict(self) -> dict[str, str]:
        """Return the legacy dict representation expected by older callers."""
        info = {
            "System": self.system,
            "Node Name": self.node_name,
            "Release": self.release,
            "Version": self.version,
            "Machine": self.machine,
        }
        if self.manufacturer:
            info["Manufacturer"] = self.manufacturer
        if self.product:
            info["Product"] = self.product
        if self.serial_number:
            info["SerialNumber"] = self.serial_number
        if self.bios_version:
            info["BIOS Version"] = self.bios_version
        if self.error_message:
            info["Error"] = self.error_message
        return info

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        return self.as_dict()


@dataclass(frozen=True)
class ScanResult:
    """Display-ready result for a completed full-scan task."""

    task_name: str
    success: bool
    message: str
    display_text: str
    status_color: str
    log_message: str = ""

    @classmethod
    def from_runner_output(cls, task_name: str, success: bool, output: str) -> ScanResult:
        """Build a scan result from a diagnostic runner tuple."""
        if success:
            display = output if len(output) < 50 else "OK"
            return cls(
                task_name=task_name,
                success=True,
                message=output,
                display_text=display,
                status_color="green",
            )

        if "Not a Laptop" in output:
            return cls(
                task_name=task_name,
                success=False,
                message=output,
                display_text="Skipped (Not a Laptop)",
                status_color="yellow",
            )

        return cls(
            task_name=task_name,
            success=False,
            message=output,
            display_text=output,
            status_color="red",
            log_message=f"[{task_name}] {output}",
        )

    @classmethod
    def from_exception(cls, task_name: str, exc: Exception) -> ScanResult:
        """Build a scan result from a runner exception."""
        message = str(exc)
        return cls(
            task_name=task_name,
            success=False,
            message=message,
            display_text=f"Error: {message[:50]}",
            status_color="red",
            log_message=f"[{task_name}] EXCEPTION: {message}",
        )


@dataclass(frozen=True)
class MemoryStats:
    """Structured RAM statistics."""

    total_gb_text: str
    available_gb_text: str
    used_gb_text: str
    percent_used: float

    def as_dict(self) -> dict[str, str | float]:
        """Return the legacy dict representation expected by older callers."""
        return {
            "Total": self.total_gb_text,
            "Available": self.available_gb_text,
            "Used": self.used_gb_text,
            "Percentage": self.percent_used,
        }

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        return {
            "Total": self.total_gb_text,
            "Available": self.available_gb_text,
            "Used": self.used_gb_text,
            "Percentage": f"{self.percent_used}%",
        }


@dataclass(frozen=True)
class GPUDevice:
    """Structured GPU status with optional collection error."""

    device_id: str = ""
    name: str = ""
    load_text: str = "N/A"
    free_memory_text: str = "N/A"
    used_memory_text: str = "N/A"
    total_memory_text: str = "N/A"
    temperature_text: str = "N/A"
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the GPU entry represents a collection error."""
        return self.error_message is not None

    def as_dict(self) -> dict[str, str]:
        """Return the legacy dict representation expected by older callers."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "DeviceID": self.device_id,
            "Name": self.name,
            "Load": self.load_text,
            "Free Memory": self.free_memory_text,
            "Used Memory": self.used_memory_text,
            "Total Memory": self.total_memory_text,
            "Temperature": self.temperature_text,
        }

    def metric_rows(self) -> dict[str, str]:
        """Return display-ready metric rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Load": self.load_text,
            "Free Memory": self.free_memory_text,
            "Used Memory": self.used_memory_text,
            "Total Memory": self.total_memory_text,
            "Temperature": self.temperature_text,
        }


@dataclass(frozen=True)
class DiskPartition:
    """Structured disk partition usage with optional collection error."""

    device: str = ""
    mountpoint: str = ""
    total_text: str = "N/A"
    used_text: str = "N/A"
    free_text: str = "N/A"
    percent_text: str = "N/A"
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the partition entry represents a collection error."""
        return self.error_message is not None

    def as_dict(self) -> dict[str, str]:
        """Return the legacy dict representation expected by older callers."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Device": self.device,
            "Mountpoint": self.mountpoint,
            "Total": self.total_text,
            "Used": self.used_text,
            "Free": self.free_text,
            "Percent": self.percent_text,
        }

    def metric_rows(self) -> dict[str, str]:
        """Return display-ready metric rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Total": self.total_text,
            "Used": self.used_text,
            "Free": self.free_text,
            "Percent": self.percent_text,
        }


@dataclass(frozen=True)
class SmartDriveStatus:
    """Structured SMART status with optional collection error."""

    key: str = ""
    display_text: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the SMART entry represents a collection error."""
        return self.error_message is not None

    def as_pair(self) -> tuple[str, str]:
        """Return the legacy key/value pair expected by older callers."""
        if self.error_message:
            return "Error", self.error_message
        return self.key, self.display_text

    def label_and_value(self) -> tuple[str, str]:
        """Return display-ready label/value content for the UI."""
        if self.error_message:
            return "Error", self.error_message
        return self.key, self.display_text
