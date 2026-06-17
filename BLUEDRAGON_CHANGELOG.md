# Blue Dragon — Changelog

Personal comma 3X (TIZI) fork built on **BluePilot 6.0** (sunnypilot / openpilot lineage).
Install any version with: `installer.comma.ai/crogers2287/<branch>`

All branches are **source** branches — the 3X compiles them on first boot.

| Branch | What's in it |
|--------|--------------|
| `comma3x` | Rolling latest (currently = `bd-1.1`) |
| `bd-1.1` | `bd-1.0` + user-tunable Driver Monitoring options |
| `bd-1.0` | BluePilot 6.0 + DragonPilot calibrated phone detection |

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
