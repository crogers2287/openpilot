"""One-shot read of live vehicle fault state from carState.

These are the flags you actually chase when lateral or ACC drops out mid-drive
-- steerFaultTemporary, steerFaultPermanent, accFaulted, canValid/canTimeout --
and until now they were visible nowhere in the portal.

carState is only published while openpilot is running, so offroad this reports
available=False rather than inventing values. The socket is opened per call and
closed immediately: this is polled at human speed from a settings page, not a
hot path, and holding a subscription open would keep a msgq reader alive for
the life of the portal process.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# carState arrives at 100Hz onroad, so a short timeout is plenty. Offroad it
# never arrives and we fall through to unavailable.
_RECV_TIMEOUT_MS = 300


def _empty(reason: str) -> dict[str, Any]:
  return {'available': False, 'reason': reason}


def get_vehicle_status() -> dict[str, Any]:
  """Live fault/health flags from carState, or available=False."""
  try:
    import cereal.messaging as messaging
  except Exception as e:  # pragma: no cover - device-only import
    logger.debug('vehicle_status: cereal unavailable: %s', e)
    return _empty('cereal messaging unavailable')

  sock = None
  try:
    sock = messaging.sub_sock('carState', timeout=_RECV_TIMEOUT_MS, conflate=True)
    msg = messaging.recv_one_or_none(sock)
    if msg is None:
      return _empty('no carState (offroad or openpilot not running)')

    cs = msg.carState
    cruise = cs.cruiseState

    faults = {
      'steerFaultTemporary': bool(cs.steerFaultTemporary),
      'steerFaultPermanent': bool(cs.steerFaultPermanent),
      'accFaulted': bool(cs.accFaulted),
      'canTimeout': bool(cs.canTimeout),
      # canValid is inverted relative to the others: True is healthy. Kept
      # under its own key so the UI doesn't have to special-case polarity.
      'canValid': bool(cs.canValid),
    }

    return {
      'available': True,
      'faults': faults,
      # Anything the driver would want to correlate a dropout against.
      'canErrorCounter': int(cs.canErrorCounter),
      'cruise': {
        'available': bool(cruise.available),
        'enabled': bool(cruise.enabled),
        'standstill': bool(cruise.standstill),
        'nonAdaptive': bool(cruise.nonAdaptive),
      },
      'vEgo': float(cs.vEgo),
      'standstill': bool(cs.standstill),
      'gearShifter': str(cs.gearShifter),
      # True when any genuine fault is set; canValid=False counts as a fault.
      'healthy': not any([
        faults['steerFaultTemporary'],
        faults['steerFaultPermanent'],
        faults['accFaulted'],
        faults['canTimeout'],
        not faults['canValid'],
      ]),
    }
  except Exception as e:
    logger.warning('vehicle_status: read failed: %s', e)
    return _empty(f'read failed: {e}')
  finally:
    if sock is not None:
      try:
        sock.close()
      except Exception:
        pass
