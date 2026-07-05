# Storage Depth Action Plan

Source: two council reviews (2026-07-05) of Master Sentinal's storage credibility and
the v1.4.0 roadmap. Tiers 0–2 shipped in the v1.3.x honesty pass. This file now tracks
what remains: the v1.4.0 "Real SMART" release, its pre-ship gates, and the docs it
touches.

**Positioning (current):** complement framing — "one dashboard for your whole PC's
health, in plain English." The "replaces vendor tools" claim stays retired until
smartmontools-grade SMART depth ships and is verified. Even then, prefer "you may never
need to open those tools" over "delete them."

---

## Done (v1.3.x honesty pass — do not redo)

- [x] **Tier 0** — Renamed "SMART Health Status" → "Drive Status (Windows-reported)";
  added capability note; fixed finding titles and report wording. No mislabeled SMART
  claims remain.
- [x] **Tier 1** — Surfaced `Wear` and `ReadErrorsUncorrected` from the existing
  `Get-StorageReliabilityCounter` query, with alert rules and graceful blank handling.
  Hardware recon confirmed `ReadErrorsUncorrected` returns blank on consumer NVMe.
- [x] **Tier 2** — Retired "replaces vendor tools" from README/marketing; reframed as
  complement.

---

## v1.4.0 — "Real SMART" (the release that closes the NVMe blind spot)

Council ruling: this is a single focused storage-depth release. The NVMe/WMI blind spot
(blank data on consumer NVMe) is *the* credibility gap — no polish substitutes for it.
Breadth is fatal for a solo maintainer, so unrelated features are cut (see Rejected).

### Gate 0 — Feasibility spike (DO THIS FIRST, ~2 hours, before any app code)

- [ ] Download the official smartmontools Windows build.
- [ ] Run elevated on the maintainer's own mixed-drive machine:
  - `smartctl --scan`
  - `smartctl -a -j <each NVMe and SATA device>`
- [ ] Record exactly what returns: full attributes, partial, or blanks — and whether the
  NVMe sits behind Intel VMD/RST.
- [ ] **Decision gate:** if smartctl cannot read the maintainer's own drives, the entire
  v1.4.0 thesis fails here — stop and reconsider before spending weeks.

### Gate 1 — Distribution survival check (pre-ship, empirical)

Bundling a GPLv2 raw-disk-I/O binary permanently changes the exe's AV/SmartScreen
profile. This is a KPI-level risk (adoption is the only KPI), not a chore.

- [ ] Upload the exact `smartctl.exe` to be bundled to VirusTotal; record detections.
- [ ] Upload a test Master Sentinal build containing it; record detections.
- [ ] **Decision gate:** if the bundled build spikes past ~3–4 engines, pause and pursue
  code-signing (even an OV cert) or download-on-first-run distribution before release.
- [ ] Review GSmartControl (the canonical smartctl-on-Windows redistributor): check its
  issue tracker for AV false-positive history and GPL-compliance approach.

### Build scope (in order)

- [ ] **Bundle unmodified official `smartctl.exe`**, invoked via subprocess with `-j`
  (JSON output — removes most custom-parser work). Ship GPLv2 license text, a written
  source offer, and a NOTICE file. Aggregation of an unmodified binary via subprocess is
  not derivation (GSmartControl precedent), but document it correctly.
- [ ] **Raw SMART / NVMe attribute table** — every attribute smartctl returns, with
  plain-English tooltips (e.g. "Reallocated Sectors: spots the drive gave up on and
  remapped"). Raw smartctl output always inspectable beside any interpretation. Closes
  the NVMe gap: media errors, available spare, percentage used, error-log entries.
- [ ] **Degraded-mode UI, treated as a feature** — explicit per-drive "SMART data
  unavailable — [reason]" states (unsupported controller, RAID/VMD, elevation denied,
  quarantined binary). Never silent, never green on missing data.
- [ ] **Attribute trending** via existing `snapshot_history.py` — per-attribute
  sparklines and 30-day deltas for the top predictors: reallocated / pending /
  uncorrectable (SATA); media errors / available spare / percentage used (NVMe).
- [ ] **Asymmetric warnings only** — threshold- and velocity-based "Warning / back up
  now" that fire ONLY on positively-read, positively-bad values (e.g. "reallocated
  sectors rising 5 → 9 in 30 days — back up this drive"). Clean-data state says "No
  issues detected in N of N readable attributes" (a statement about the data, not a
  health guarantee).

### Cut from v1.4.0 (conceded to the Devil's Advocate / deferred)

- **No positive "Healthy" verdict badge** and **no healthy/watch/act classifier as a
  positive assertion.** The council could not show a tested false-negative rate across
  VMD/RAID/USB/Optane controllers, so an unconditional verdict over possibly-blank data
  is the liability (green checkmark next to a dead drive). Deferred until tested against
  real failing-drive data.
- **No Drive Risk Score** built on current telemetry — it would score confidently on
  blanks exactly where the tool is weakest.

---

## v1.5.0 candidate — Alerts on real data

Peer review rescued this: a tray alert is the moment a user stops opening CrystalDiskInfo
at all (retention). But it must fire on data that actually exists — so it lands *after*
v1.4.0's real SMART, not before.

- [ ] Configurable thresholds + system-tray notifications, driven by the asymmetric
  warning engine from v1.4.0.

---

## Later / hardware-gated

- [ ] Firmware update checks (users may open vendor tools for this — validate demand
  first; see verification below).
- [ ] Only after real SMART ships and is verified: re-evaluate replacement language.
  Preferred framing even then: "you may never need to open those tools."

---

## docs/diagnostics-and-permissions.md — fixes (copy edits)

Verified accurate: all command tables match `full_scan.py`; log path matches
`app_logging.py`; no stale SMART claims. Gaps to close, in priority order:

- [ ] **Add the Anonymize export option** — the doc tells users to manually review
  reports for sensitive data but never mentions the built-in Anonymize prompt
  (`issue_bundle.py` + `redaction.py`) that scrubs username, PC name, and serials. This
  is the app's best privacy feature, missing from the trust document.
- [ ] **Disclose the internet speed test** — the one diagnostic that contacts external
  servers and uses bandwidth. In a "no telemetry" app, state what's contacted, what's
  sent, and that nothing is stored remotely.
- [ ] **Document scan presets** — Quick / Standard / Deep (`scan_presets.py`, since
  v1.2.0) each run a different subset of elevated commands; the doc still implies a
  single default Full Scan.
- [ ] **Cover local data-at-rest** — snapshot history is persisted automatically every
  few minutes and post-reboot results are stored/read back; the doc mentions only the
  log file. Say where this data lives and how to clear it.
- [ ] **When v1.4.0 ships:** add a section disclosing the bundled GPLv2 `smartctl` binary
  and that it performs elevated raw disk I/O — exactly the kind of behavior this doc
  exists to disclose.

---

## Verification / validation

- [ ] **Side-by-side accuracy test** — Master Sentinal vs. CrystalDiskInfo on an aging
  drive with nonzero reallocated sectors. If CDI shows "Caution" while we show clean, the
  false-confidence gap is still open.
- [ ] **Outside-view / base-rate check** — survey 3–5 OSS projects that redistribute
  smartctl on Windows (GSmartControl canonical) for AV false-positive history, GPL
  approach, and how long solo maintainers sustained the parser/mapping layer. If the
  reference class shows ~30% GPL-derailment or multi-month AV damage specifically for
  *subprocess-bundled unmodified binaries*, revisit the bundling mechanism, not the
  feature.
- [ ] **Cheap demand validation** (nobody on the council did this) — ask 5–10 real users
  (r/pcmasterrace or GitHub Discussions, ~1 day) "what do you still open Samsung Magician
  or CrystalDiskInfo for?" If answers cluster on firmware/benchmarks rather than SMART
  depth, the v1.5+ roadmap changes even if v1.4.0 doesn't.

---

## Explicitly rejected (do not relitigate)

- **Scary disclaimer banner** on the storage tab — reads as "this feature is broken."
  Accurate labeling + real data is the fix, not self-sabotage. (Resolved in Tier 0.)
- **Delaying releases until full vendor parity** — depth lands in tiers, not one leap.
- **Positive "Healthy" verdict over unvalidated data** — the green-checkmark-next-to-a-
  dead-drive failure mode. Only asymmetric, positively-triggered warnings ship until a
  verdict layer is tested across messy controllers.
- **Breadth features in v1.4.0** — PDF export, plugin architecture, driver
  recommendations, startup scoring, network wizard. Cut to protect solo-maintainer focus;
  none of them make a user uninstall a vendor tool.
