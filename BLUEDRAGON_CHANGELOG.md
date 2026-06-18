# Blue Dragon — Changelog

Personal comma 3X (TIZI) fork built on **BluePilot 6.0** (sunnypilot / openpilot lineage).
Install any version with: `installer.comma.ai/crogers2287/<branch>`

All branches are **source** branches — the 3X compiles them on first boot.

| Branch | What's in it |
|--------|--------------|
| `comma3x` | Rolling latest (currently = `bd-1.4`) |
| `bd-1.4` | `bd-1.3` + Blue Dragon branding (boot splash, loading-screen logo, README) |
| `bd-1.3` | `bd-1.2` + Passive/Off DM auto-cuts the comma connection (logging/upload/athena) |
| `bd-1.2` | `bd-1.1` + DM mode (Passive/Off), pre-calibration phone threshold, mute nag sound |
| `bd-1.1` | `bd-1.0` + user-tunable Driver Monitoring options |
| `bd-1.0` | BluePilot 6.0 + DragonPilot calibrated phone detection |

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
