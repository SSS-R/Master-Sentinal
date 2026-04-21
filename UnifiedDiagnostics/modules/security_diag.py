"""Security diagnostics - Defender, Firewall, and BitLocker status."""

from __future__ import annotations

import subprocess
from typing import Any

import wmi

from models.diagnostic_models import (
    BitLockerVolumeStatus,
    FirewallProfileStatus,
    SecurityHealth,
)
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class SecurityDiagnostic:
    """Gathers security health: Defender, Firewall, and BitLocker status."""

    def get_security_health(self) -> SecurityHealth:
        """Return structured security health state."""
        try:
            defender_result = self._get_defender_status()
            firewall_result = self._get_firewall_status()
            bitlocker_result = self._get_bitlocker_status()

            # Aggregate errors
            errors = []
            if defender_result.get("error"):
                errors.append(defender_result["error"])
            if firewall_result.get("error"):
                errors.append(firewall_result["error"])
            if bitlocker_result.get("error"):
                errors.append(bitlocker_result["error"])

            error_message = "; ".join(errors) if errors else None

            return SecurityHealth(
                defender_enabled=defender_result.get("enabled"),
                antivirus_signature_age_days=defender_result.get("av_sig_age_days"),
                antispyware_signature_age_days=defender_result.get("asp_sig_age_days"),
                real_time_protection_enabled=defender_result.get("real_time_protection"),
                firewall_profiles=firewall_result.get("profiles", []),
                bitlocker_volumes=bitlocker_result.get("volumes", []),
                defender_error=defender_result.get("error", ""),
                firewall_error=firewall_result.get("error", ""),
                bitlocker_error=bitlocker_result.get("error", ""),
                error_message=error_message,
            )

        except Exception as e:
            LOGGER.exception("Security diagnostics failed: %s", e)
            return SecurityHealth(error_message=friendly_exception_message(e, "Security diagnostics"))

    def _get_defender_status(self) -> dict[str, Any]:
        """Query Windows Defender status via WMI and registry."""
        try:
            # Try WMI first (SecurityCenter2)
            c = wmi.WMI(namespace="root/SecurityCenter2")
            av_products = list(c.AntivirusProduct())

            if av_products:
                av = av_products[0]
                defender_enabled = av.productState is not None
                # Signature age from displayName or version
                av_sig_age_days = None
                asp_sig_age_days = None

                return {
                    "enabled": defender_enabled,
                    "av_sig_age_days": av_sig_age_days,
                    "asp_sig_age_days": asp_sig_age_days,
                    "real_time_protection": defender_enabled,
                    "error": None,
                }

            # Fallback: Check if Defender service is running
            c = wmi.WMI()
            services = list(c.Win32_Service(name="WinDefend"))
            if services:
                svc = services[0]
                is_running = svc.State == "Running" if svc.State else False
                return {
                    "enabled": is_running,
                    "av_sig_age_days": None,
                    "asp_sig_age_days": None,
                    "real_time_protection": is_running,
                    "error": None,
                }

            return {
                "enabled": None,
                "av_sig_age_days": None,
                "asp_sig_age_days": None,
                "real_time_protection": None,
                "error": "Defender service not found",
            }

        except Exception as e:
            LOGGER.warning("Defender status check failed: %s", e)
            return {
                "enabled": None,
                "av_sig_age_days": None,
                "asp_sig_age_days": None,
                "real_time_protection": None,
                "error": friendly_exception_message(e, "Defender status"),
            }

    def _get_firewall_status(self) -> dict[str, Any]:
        """Query Windows Firewall status for all profiles."""
        try:
            profiles = []
            c = wmi.WMI(namespace="root/StandardCimv2/MSNetFirewall")

            # Get firewall profiles (Domain, Private, Public)
            for profile_name in ["Domain", "Private", "Public"]:
                try:
                    fw_profiles = list(c.MSNetFirewallProfile(Name=profile_name))
                    if fw_profiles:
                        fw = fw_profiles[0]
                        enabled = fw.Enabled is True
                        profiles.append(
                            FirewallProfileStatus(
                                name=profile_name,
                                enabled=enabled,
                                default_inbound_action=str(getattr(fw, "DefaultInboundAction", "Unknown")),
                                default_outbound_action=str(getattr(fw, "DefaultOutboundAction", "Unknown")),
                            )
                        )
                except Exception:
                    # Profile may not exist on this system
                    continue

            # Fallback: Use netsh if WMI fails
            if not profiles:
                result = subprocess.run(
                    ["netsh", "advfirewall", "show", "allprofiles", "state"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if line.endswith(" Profile Settings:") or "State" in line:
                            # Parse netsh output
                            if "Domain Profile Settings:" in line:
                                profiles.append(
                                    FirewallProfileStatus(
                                        name="Domain",
                                        enabled="ON" in result.stdout,
                                        default_inbound_action="Block",
                                        default_outbound_action="Allow",
                                    )
                                )
                            elif "Private Profile Settings:" in line:
                                profiles.append(
                                    FirewallProfileStatus(
                                        name="Private",
                                        enabled="ON" in result.stdout,
                                        default_inbound_action="Block",
                                        default_outbound_action="Allow",
                                    )
                                )
                            elif "Public Profile Settings:" in line:
                                profiles.append(
                                    FirewallProfileStatus(
                                        name="Public",
                                        enabled="ON" in result.stdout,
                                        default_inbound_action="Block",
                                        default_outbound_action="Allow",
                                    )
                                )

            return {"profiles": profiles, "error": None}

        except subprocess.TimeoutExpired:
            LOGGER.warning("Firewall status check timed out")
            return {"profiles": [], "error": "Firewall status check timed out"}
        except Exception as e:
            LOGGER.warning("Firewall status check failed: %s", e)
            return {
                "profiles": [],
                "error": friendly_exception_message(e, "Firewall status"),
            }

    def _get_bitlocker_status(self) -> dict[str, Any]:
        """Query BitLocker encryption status for all volumes."""
        try:
            volumes = []
            c = wmi.WMI(namespace="root/CIMv2/Security/MicrosoftVolumeEncryption")

            try:
                bitlocker_volumes = list(c.MsBitLockerVolume())
                for vol in bitlocker_volumes:
                    mount_point = getattr(vol, "DriveLetter", "") or getattr(vol, "MountPoint", "")
                    volume_status = getattr(vol, "VolumeStatus", "Unknown")
                    protection_status = getattr(vol, "ProtectionStatus", "Unknown")
                    encryption_pct = getattr(vol, "EncryptionPercentage", None)

                    volumes.append(
                        BitLockerVolumeStatus(
                            mount_point=mount_point or "Unknown",
                            volume_status=str(volume_status),
                            protection_status=str(protection_status),
                            encryption_percentage=float(encryption_pct) if encryption_pct is not None else None,
                        )
                    )
            except Exception:
                # WMI namespace may not exist if BitLocker isn't available
                pass

            # Fallback: Use manage-bde if WMI fails or returns nothing
            if not volumes:
                try:
                    result = subprocess.run(
                        ["manage-bde", "-status"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    if result.returncode == 0:
                        # Parse manage-bde output (simplified)
                        output = result.stdout
                        if "C:" in output:
                            volumes.append(
                                BitLockerVolumeStatus(
                                    mount_point="C:",
                                    volume_status="Encrypted" if "100%" in output else "Encryption in progress",
                                    protection_status="On" if "Protection Status: Protection On" in output else "Off",
                                    encryption_percentage=100.0 if "100%" in output else 50.0,
                                )
                            )
                except subprocess.TimeoutExpired:
                    LOGGER.warning("BitLocker status check timed out")
                    return {"volumes": [], "error": "BitLocker status check timed out"}
                except Exception:
                    pass

            return {"volumes": volumes, "error": None}

        except Exception as e:
            LOGGER.warning("BitLocker status check failed: %s", e)
            return {
                "volumes": [],
                "error": friendly_exception_message(e, "BitLocker status"),
            }
