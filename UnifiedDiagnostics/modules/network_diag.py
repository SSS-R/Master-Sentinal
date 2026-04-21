"""Network diagnostics - adapter status, DNS, gateway, and connectivity checks."""

from __future__ import annotations

import socket
import subprocess
from typing import Any

import wmi

from models.diagnostic_models import NetworkAdapterStatus, NetworkHealth
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class NetworkDiagnostic:
    """Gathers network health: adapter status, DNS, gateway, and connectivity."""

    def get_network_health(self) -> NetworkHealth:
        """Return structured network health state."""
        try:
            adapters_result = self._get_adapter_statuses()
            dns_result = self._get_dns_servers()
            gateway_result = self._get_gateways()
            connectivity_result = self._check_connectivity()

            # Aggregate errors
            errors = []
            if adapters_result.get("error"):
                errors.append(adapters_result["error"])
            if dns_result.get("error"):
                errors.append(dns_result["error"])
            if gateway_result.get("error"):
                errors.append(gateway_result["error"])
            if connectivity_result.get("error"):
                errors.append(connectivity_result["error"])

            error_message = "; ".join(errors) if errors else None

            return NetworkHealth(
                adapters=adapters_result.get("adapters", []),
                dns_servers=dns_result.get("servers", []),
                gateway_addresses=gateway_result.get("gateways", []),
                dns_resolution_ok=connectivity_result.get("dns_ok"),
                internet_reachable=connectivity_result.get("internet_ok"),
                error_message=error_message,
            )

        except Exception as e:
            LOGGER.exception("Network diagnostics failed: %s", e)
            return NetworkHealth(error_message=friendly_exception_message(e, "Network diagnostics"))

    def _get_adapter_statuses(self) -> dict[str, Any]:
        """Get status of all network adapters."""
        try:
            adapters = []
            c = wmi.WMI()

            for adapter in c.Win32_NetworkAdapter():
                if adapter.NetEnabled is True:
                    status = adapter.NetConnectionStatus
                    status_text = self._map_adapter_status(status)
                    link_speed = getattr(adapter, "Speed", None)
                    speed_text = f"{link_speed / 1_000_000:.1f} Mbps" if link_speed else "N/A"

                    adapters.append(
                        NetworkAdapterStatus(
                            name=adapter.Name or "Unknown",
                            status=status_text,
                            link_speed=speed_text,
                        )
                    )

            return {"adapters": adapters, "error": None}

        except Exception as e:
            LOGGER.warning("Adapter status check failed: %s", e)
            return {
                "adapters": [],
                "error": friendly_exception_message(e, "Adapter status"),
            }

    @staticmethod
    def _map_adapter_status(status_code: int | None) -> str:
        """Map WMI NetConnectionStatus code to human-readable text."""
        status_map = {
            0: "Disconnected",
            1: "Connecting",
            2: "Connected",
            3: "Disconnecting",
            4: "Hardware Not Present",
            5: "Hardware Disabled",
            6: "Hardware Malfunction",
            7: "Media Disconnected",
            8: "Authenticating",
            9: "Authentication Succeeded",
            10: "Authentication Failed",
            11: "Invalid Address",
            12: "Credentials Required",
        }
        return status_map.get(status_code, "Unknown")

    def _get_dns_servers(self) -> dict[str, Any]:
        """Get configured DNS servers."""
        try:
            servers = []
            c = wmi.WMI()

            for adapter in c.Win32_NetworkAdapterConfiguration():
                if adapter.NetEnabled is True and adapter.DNSServerSearchOrder:
                    for dns in adapter.DNSServerSearchOrder:
                        if dns and dns not in servers:
                            servers.append(dns)

            # Fallback: Use ipconfig
            if not servers:
                result = subprocess.run(
                    ["ipconfig", "/all"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "DNS Servers" in line:
                            dns = line.split(":")[-1].strip()
                            if dns and dns not in servers:
                                servers.append(dns)

            return {"servers": servers, "error": None}

        except subprocess.TimeoutExpired:
            LOGGER.warning("DNS server check timed out")
            return {"servers": [], "error": "DNS server check timed out"}
        except Exception as e:
            LOGGER.warning("DNS server check failed: %s", e)
            return {"servers": [], "error": friendly_exception_message(e, "DNS server check")}

    def _get_gateways(self) -> dict[str, Any]:
        """Get configured gateway addresses."""
        try:
            gateways = []
            c = wmi.WMI()

            for adapter in c.Win32_NetworkAdapterConfiguration():
                if adapter.NetEnabled is True and adapter.DefaultIPGateway:
                    for gw in adapter.DefaultIPGateway:
                        if gw and gw not in gateways:
                            gateways.append(gw)

            # Fallback: Use route print
            if not gateways:
                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "0.0.0.0" in line and "0.0.0.0" in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                gw = parts[2]
                                if gw and gw not in gateways:
                                    gateways.append(gw)

            return {"gateways": gateways, "error": None}

        except subprocess.TimeoutExpired:
            LOGGER.warning("Gateway check timed out")
            return {"gateways": [], "error": "Gateway check timed out"}
        except Exception as e:
            LOGGER.warning("Gateway check failed: %s", e)
            return {"gateways": [], "error": friendly_exception_message(e, "Gateway check")}

    def _check_connectivity(self) -> dict[str, Any]:
        """Check DNS resolution and internet connectivity."""
        result = {"dns_ok": None, "internet_ok": None, "error": None}

        # Check DNS resolution
        try:
            socket.gethostbyname("www.google.com")
            result["dns_ok"] = True
        except socket.gaierror:
            result["dns_ok"] = False
        except Exception as e:
            LOGGER.warning("DNS resolution check failed: %s", e)
            result["dns_ok"] = False

        # Check internet connectivity
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            result["internet_ok"] = True
        except (socket.timeout, socket.error):
            result["internet_ok"] = False
        except Exception as e:
            LOGGER.warning("Internet connectivity check failed: %s", e)
            result["internet_ok"] = False

        return result
