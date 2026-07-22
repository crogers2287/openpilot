# Blue Dragon — Changelog

Personal comma 3X (TIZI) fork. `bd-2.0` and later are built on **BluePilot 7.0**;
`bd-1.x` was built on **BluePilot 6.0** (sunnypilot / openpilot lineage).
Install any version with: `installer.comma.ai/crogers2287/<branch>`

> **Install repo:** the comma installer always clones `github.com/<owner>/openpilot.git`,
> so every branch here must be pushed to **`crogers2287/openpilot`**. Pushing only to
> `crogers2287/bluedragon` publishes nothing the device can see.

All branches are **source** branches — the 3X compiles them on first boot. From bp-7.0
onward the build also fetches deps from `commaai/dependencies` at build time, so the
**first boot after switching needs working internet**, not just the car.

| Branch | What's in it |
|--------|--------------|
| `comma3x` | Rolling latest |
| `bd-2.0` | **bp-7.0 base** + all bd-1.7 Blue Dragon features re-ported |
| `bd-1.7` | **Real boot/reboot fix** — Passive/Off is now pure DM logic, zero manager coupling |
| `bd-1.6` | ⚠️ reboots on Passive — use `bd-1.7`. (device logo = dragon) |
| `bd-1.5` | ⚠️ reboots on Passive — use `bd-1.7`. (loggerd revert, kept uploader gate = still bad) |
| `bd-1.4` | ⚠️ BOOT HANG on Passive/Off — use `bd-1.7`. (branding) |
| `bd-1.3` | ⚠️ BOOT HANG on Passive/Off — use `bd-1.7`. (Passive/Off cut logging/athena) |
| `bd-1.2` | `bd-1.1` + DM mode (Passive/Off), pre-calibration phone threshold, mute nag sound |
| `bd-1.1` | `bd-1.0` + user-tunable Driver Monitoring options |
| `bd-1.0` | BluePilot 6.0 + DragonPilot calibrated phone detection |

---

## bd-2.0 — Rebase onto BluePilot 7.0

`bd-1.x` was built on bp-6.0. bp-7.0 landed upstream as a separate lineage that never
carried the Blue Dragon commits, so every BD feature was re-ported onto the new base
rather than merged.

**Ported:** the 5 `BPDm*` params, DM sensitivity preset, DM Mode (Standard/Passive/Off),
passive wheel-touch timeout, low-speed relaxation, mute-nag sound gate, and the
boot-splash / loading-logo branding.

**Adaptations required by bp-7.0:**
- `selfdrive/monitoring/helpers.py` → **`policy.py`** (renamed in 6.1).
- `distracted_types` changed from a list of enums to a **string-keyed dict**.
- `_set_timers(bool)` → **`_set_policy(MonitoringPolicy.…)`**. Passive now forces
  `MonitoringPolicy.wheeltouch` instead of passing `False`.
- The single `_AWARENESS_TIME` became a **3-stage ladder**
  (`_WHEELTOUCH_POLICY_ALERT_{1,2,3}_TIMEOUT` = 15/24/30s). `BPDmPassiveTimer` now sets the
  terminal timeout and scales stages 1 and 2 by the stock 0.5 / 0.8 ratios.
- The dragonpilot calibrated-phone-detection work (bd-1.0) was **already present** on the
  bp-7.0 line, so it was not re-applied — only the sensitivity scaling on top of it.
- Settings UI moved to collapsible sections; DM controls are now a
  `_section(tr("Driver Monitoring"), …)` group.

**Unchanged by design:** `system/manager/process_config.py` and
`system/athena/manage_athenad.py` remain **fully stock**. See bd-1.7 below — any DM-param
read in a manager process-gating callback bricks the device. That rule still holds.

**Not carried over:** the bd-1.4 README branding. bp-7.0 rewrote the README substantially
and clobbering it would drop upstream docs.

⚠️ Verified by `py_compile` only. DM unit tests cannot run off-device (`params_pyx` is not
compiled). Confirm Passive and Off on-device before trusting this branch.

---

## bd-1.7 — Real fix: Passive/Off no longer reboots the device
bd-1.5's loggerd revert wasn't enough — bd-1.5/1.6 still **rebooted instantly** when DM
was set to Passive. Root cause: the **uploader gating** I kept in
`system/manager/process_config.py` read `BPDmMode` **live, every manager cycle**. The
moment the param flipped, the manager re-evaluated it and that path took the manager down →
instant reboot → and on restart it re-evaluated at boot → stuck at the splash.

Fix: **`process_config.py` is reverted to fully stock** (and `manage_athenad` already was).
There is now **zero** manager/process coupling to DM mode. Passive/Off is purely a
driver-monitoring behavior change read once by `dmonitoringd` at start (`helpers.py`):
- Passive = wheel-touch (steering) timer only, no camera DM
- Off = DM disabled
- plus the sensitivity / low-speed-relax / mute-nag options from 1.1–1.2

**Dropped:** the automatic "cut comma uploads in Passive/Off" feature — that was the unsafe
part. If you want those drives off comma, disable uploads / comma-connect manually.

---

## bd-1.6 — Branding fix: device loading logo
The device loading spinner was wrongly using the GitHub repo emblem
(`bluedragon_logo.png`). Swapped it to the **dragon** (a square crop of the splash,
no wordmark) so the device shows device branding and the emblem stays GitHub-only.
- Device boot splash: `img_bluepilot_boot.jpg` = full splash (unchanged)
- Device loading spinner: `spinner_sunnypilot.png` = dragon crop (`branding/bluedragon_device_logo.png`)
- GitHub README logo: `bluedragon_logo.png` emblem (unchanged)

---

## bd-1.5 — Boot-hang fix (supersedes 1.3/1.4)
`bd-1.3`/`bd-1.4` hung at the boot logo as soon as DM was set to Passive or Off. Cause:
those versions gated **`loggerd`** off and restructured **`manage_athenad`** when DM was
relaxed. On a comma device `loggerd` must keep running — turning it off is an unsupported
state and stalled startup.

Fix:
- **Reverted** the `loggerd` gate (`process_config.logging`) and the `manage_athenad` loop
  changes — both back to stock, so boot is never affected by DM mode.
- **Kept** the safe privacy mechanism: Passive/Off still gate the **uploader** (comma +
  sunnylink) via `bd_dm_relaxed`, so those drives are not uploaded to comma. Local logging
  and comma-connect/athena are left alone.
- Recovery for a stuck 1.3/1.4 device (no reflash): over SSH set `BPDmMode=0` and reboot.

All DM tuning (low-speed relax, sensitivity, passive timer, mute nag) and the branding from
1.1–1.4 are retained.

---

## bd-1.4 — Blue Dragon branding
On-device and repo branding (no behavior change):
- **Boot splash** — `selfdrive/assets/img_bluepilot_boot.jpg` (2160x1080, 3X/tizi) and
  `img_bluepilot_boot_mici.jpg` (536x240) replaced with the Blue Dragon splash. Applied to
  the device via `scripts/boot_logo.sh` (copies to `/usr/comma/bg.jpg`).
- **Loading-screen logo** — `sunnypilot/selfdrive/assets/images/spinner_sunnypilot.png`
  (1024x1024) replaced with the Blue Dragon emblem (shown on the boot/compile spinner).
- **README** — Blue Dragon header (splash + logo + install table).
- Source art kept in `branding/` (`bluedragon_splash.png`, `bluedragon_logo.png`).

---

## bd-1.3 — Passive/Off DM cuts the comma connection
When **Driver Monitoring Mode** is **Passive or Off** (`BPDmMode != 0`), the device
automatically stops talking to comma's servers, so those drives are never recorded or
sent and can't be used to flag the account:

- **logging** (`loggerd`) — off, so no route logs/video are even recorded for the drive
  (prevents later upload when you switch back to Standard).
- **upload** (`uploader` + sunnylink `sunnylink_uploader`) — off, nothing sent to comma/sunnypilot.
- **athena** (`manage_athenad`) — the live remote connection is kept down (and terminated
  mid-drive if you switch to Passive/Off), so no remote pull either.

Switching back to **Standard** restores all of them. Gating lives in
`system/manager/process_config.py` (`bd_dm_relaxed`) and `system/athena/manage_athenad.py`.
Trade-off: in Passive/Off you get no comma connect / remote SSH / route review for those drives.

---

## bd-1.2 — DM mode, more tuning (DragonPilot-inspired)
Extends the Settings → BluePilot → **Driver Monitoring** section.

- **Driver Monitoring Mode** (`BPDmMode`, default Standard)
  - *Standard* — normal camera DM.
  - *Passive* — camera DM off; falls back to a wheel-touch (steering) timer only.
  - *Off* — camera DM disabled entirely (awareness pinned, no DM events).
  - ⚠️ Passive/Off **weaken a safety feature**. comma can detect this from uploaded
    driving data and may flag/de-list the account from comma servers. Use a fork-only
    posture (disable data upload / don't pair comma prime) if that matters to you.
- **Passive Steering Timeout** (`BPDmPassiveTimer`, default 70 s; presets 70/120/180/360 s)
  Wheel-touch timeout used in Passive mode. Clamped to DragonPilot's 70–360 s range.
- **DM Sensitivity** now also scales the **pre-calibration** phone threshold (B1) —
  fewer false phone nags in the first ~60 s of a drive.
- **Mute Driver Monitoring Nag Sound** (`BPDmMuteNag`, default off)
  Silences only the repeating `promptDistracted` chime. Terminal/red and
  collision-warning sounds are never affected (scoped for safety).

Implemented in `helpers.py` (mode/timer/sensitivity), `soundd.py` (mute, via
`should_play_sound`), UI in `bluepilot.py`. All take effect on next drive / reboot.

---

## bd-1.1 — Driver Monitoring options
Adds a **Driver Monitoring** section to Settings → BluePilot.

- **Relax Driver Monitoring at Low Speed** (`BPDmLowSpeedRelax`, default off)
  Stock bp-6.0 only relaxes DM below ~25 mph when **disengaged**. This extends the
  low-speed exemption to the **engaged** case (stop-and-go), which is where the
  constant nagging happens. Suppresses awareness decrement + pre/orange alerts below
  `_ALWAYS_ON_ALERT_MIN_SPEED` (11 m/s); red/terminal still functions.
- **Driver Monitoring Sensitivity** (`BPDmSensitivity`, default Standard)
  Scales pose distraction thresholds: Relaxed = ×1.15 (fewer nags), Standard = ×1.0
  (stock), Strict = ×0.9.

Both read once at start — take effect on next drive / reboot. Implemented in
`selfdrive/monitoring/helpers.py`; UI in `selfdrive/ui/bp/layouts/settings/bluepilot.py`.

## bd-1.0 — Calibrated phone detection
Ports the one DragonPilot DMS tweak missing from BluePilot 6.0: calibrated phone
detection (`_PHONE_THRESH2` / `phone_offsetter` / `phone_prob_calibrated`) — learns
the driver's baseline phone-probability and scales the trigger threshold to cut false
phone-use alerts. The other DragonPilot DMS tweaks (low-speed exemption, 20 s
uncertain-reset, "DM uncertain" offroad alert, RHD non-blocking write) were already
present in BluePilot 6.0.
