# Diagnostics And Permissions

This guide describes which parts of Master Sentinal are read-only, which require
administrator rights, and which can trigger follow-up system actions.

## Supported Environment

- Windows 10
- Windows 11
- PowerShell available
- Administrator rights for repair and advanced troubleshooting features

## Read-Only Diagnostics

These features collect information without intentionally changing system state:

- CPU, memory, GPU, storage, and motherboard inventory
- health scoring and finding generation
- Windows Update, firewall, Defender, service, network, and event-log summaries
- report export to CSV, HTML, and JSON

Some of these checks may still fail or return partial results if Windows blocks
access to WMI, CIM, security tooling, or BitLocker APIs.

## Routine Repair Checks

These are included in the default Full Scan and require elevation:

| Tool | Command family | Risk |
| --- | --- | --- |
| System File Checker | `sfc /scannow` | Low |
| DISM Image Repair | `DISM /Online /Cleanup-Image /RestoreHealth` | Low to medium |
| Disk Check (Scan) | `chkdsk C: /scan` | Low |
| Quick Disk Check | `chkdsk C: /scan /perf` | Low |
| Power Monitor | `powercfg /energy` | Low |
| Battery Health | `powercfg /batteryreport` | Low |

These commands are intended to be routine checks, but they can still take time,
stress disk activity, or reveal issues that require later manual remediation.

## Advanced Tools

These actions need stronger user intent:

| Tool | Behavior | Extra caution |
| --- | --- | --- |
| Driver Verifier | Launches the Windows Driver Verifier UI | Can destabilize a system if enabled carelessly |
| Memory Diagnostic | Launches `mdsched.exe` | Schedules a reboot-driven memory test |

## Permissions Summary

| Feature | Standard user | Administrator |
| --- | --- | --- |
| Dashboard | Mostly yes | Full detail |
| Health findings | Mostly yes | Best coverage |
| Full Scan routine checks | No | Yes |
| Advanced troubleshooting tools | No | Yes |
| Export reports | Yes | Yes |

## Logs And Reports

- application log: `logs/master_sentinal.log`
- export formats: CSV, HTML, JSON
- reports can contain device names, OS version, timestamps, and diagnostic results

If you share a report publicly, review it first for anything you consider sensitive.
