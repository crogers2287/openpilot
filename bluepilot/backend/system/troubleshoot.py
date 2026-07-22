"""Troubleshoot report: what you changed, and what the car is complaining about.

Two independent halves, deliberately in one payload so a bug report is a single
copy-paste:

  settings  - every settings-UI param whose current value differs from its
              registered default. Answers "what did I change?" without
              scrolling nine panels.
  vehicle   - live fault flags from carState (see vehicle_status.py).

Defaults come from Params.get_default_value(), i.e. the third field of the
params_keys.h entry, so they track the device rather than a copy in the portal.
"""
from __future__ import annotations

import logging
from typing import Any

from bluepilot.backend import settings_schema
from bluepilot.backend.system.vehicle_status import get_vehicle_status

logger = logging.getLogger(__name__)


def _coerce(value: Any) -> Any:
  """bytes -> str so the result is JSON-serialisable."""
  if isinstance(value, bytes):
    try:
      return value.decode('utf-8', errors='replace')
    except Exception:
      return repr(value)
  return value


def _same(current: Any, default: Any) -> bool:
  """Compare loosely: params round-trip through strings and bools inconsistently."""
  if current is None and default is None:
    return True
  if current is None or default is None:
    return False
  if isinstance(current, bool) or isinstance(default, bool):
    def truthy(v: Any) -> bool:
      if isinstance(v, bool):
        return v
      return str(v).strip().lower() in ('1', 'true', 'yes', 'on')
    return truthy(current) == truthy(default)
  # Numeric-ish values may differ only in formatting ("5" vs "5.0").
  try:
    return float(current) == float(default)
  except (TypeError, ValueError):
    pass
  return str(current).strip() == str(default).strip()


def get_settings_diff(params=None) -> dict[str, Any]:
  """Current-vs-default for every settings-UI param."""
  try:
    from openpilot.common.params import Params
  except Exception as e:  # pragma: no cover - device-only import
    logger.debug('troubleshoot: Params unavailable: %s', e)
    return {'available': False, 'reason': 'params unavailable', 'items': [], 'changedCount': 0}

  p = params or Params()
  items: list[dict] = []
  changed = 0

  for entry in settings_schema.iter_params():
    key = entry['key']
    try:
      current = _coerce(p.get(key, return_default=True))
    except Exception:
      # Param not registered on this build (schema is shared across forks).
      continue
    try:
      default = _coerce(p.get_default_value(key))
    except Exception:
      default = None

    is_changed = not _same(current, default)
    if is_changed:
      changed += 1
    items.append({**entry, 'current': current, 'default': default, 'changed': is_changed})

  return {'available': True, 'items': items, 'changedCount': changed, 'total': len(items)}


def get_troubleshoot_report(params=None) -> dict[str, Any]:
  return {
    'settings': get_settings_diff(params),
    'vehicle': get_vehicle_status(),
  }
