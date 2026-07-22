"""Adapt sunnypilot's generated settings schema into the portal's panel format.

Why this exists: bp_portal's /api/panels endpoints were written against
selfdrive/ui/bluepilot/menus/bp_*_panel.json, produced by BluePilot's old Qt
settings UI. That directory does not exist anywhere in this lineage any more --
not on bd-1.7, not on bp-7.0, not upstream -- so the glob silently matched
nothing and the portal's Settings tab rendered empty.

Rather than hand-author replacement JSON that would immediately drift from the
device UI, we read sunnypilot/sunnylink/settings_ui.json. That file is
generated from sunnypilot/sunnylink/settings_ui_src/pages/*.yaml, is already
maintained in-tree, and is the same schema sunnylink ships to its remote
frontend -- so the portal and the device stay in sync for free.

Known limitation: the source schema carries a rich `enablement` / `visibility`
condition grammar (param equality, offroad_only, capability checks, and
and/or/not combinators). This adapter does NOT translate it. Controls are
emitted unconditionally, so the portal may show a setting the device UI would
grey out. The device remains the authority -- it validates on write -- but
treat the device UI as the source of truth for what actually applies to a given
car. Translating the grammar is the obvious next step.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# bluepilot/backend/settings_schema.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_UI_JSON = _REPO_ROOT / 'sunnypilot' / 'sunnylink' / 'settings_ui.json'

# Params sunnypilot refuses to expose to remote callers (settings_ui.json
# "blocked": true). bp_portal has no authentication of any kind, so these must
# not be reachable from the web UI either -- they grant shell/ADB access.
_ALWAYS_OMIT = {'AdbEnabled', 'SshEnabled'}


def _panel_public_id(raw_id: str) -> str:
  """'steering' -> 'bp_steering_panel', matching bp_portal's existing ordering."""
  return f'bp_{raw_id}_panel'


def _raw_id_from_public(public_id: str) -> str:
  return public_id[3:-6] if public_id.startswith('bp_') and public_id.endswith('_panel') else public_id


def _is_integral(*vals: Any) -> bool:
  try:
    return all(float(v) == int(float(v)) for v in vals if v is not None)
  except (TypeError, ValueError):
    return False


def _convert_options(options: list[dict]) -> list[dict]:
  out = []
  for opt in options or []:
    label = str(opt.get('label', opt.get('value', '')))
    out.append({
      'name': label,
      'label': label,
      # The portal stores param values as strings; the source uses ints.
      'value': str(opt.get('value')),
    })
  return out


def _convert_item(item: dict) -> dict | None:
  """settings_ui.json item -> portal PanelControl. Returns None if unsupported."""
  key = item.get('key')
  widget = item.get('widget')
  title = item.get('title', key or '')
  desc = item.get('description', '') or ''

  if key in _ALWAYS_OMIT:
    return None

  # A change that only takes effect after an onroad cycle is worth surfacing,
  # since the portal gives no other signal that nothing appeared to happen.
  if item.get('needs_onroad_cycle'):
    note = 'Takes effect after the next onroad cycle.'
    desc = f'{desc} {note}'.strip()

  base = {'title': title, 'desc': desc}

  if widget == 'toggle':
    return {**base, 'type': 'toggle', 'param': key}

  if widget == 'multiple_button':
    opts = _convert_options(item.get('options', []))
    if not opts:
      return None
    return {**base, 'type': 'segmented_control', 'param': key, 'options': opts}

  if widget == 'option':
    opts = item.get('options')
    if opts:
      converted = _convert_options(opts)
      if not converted:
        return None
      ctrl = {**base, 'type': 'selection', 'param': key, 'options': converted}
      if item.get('unit'):
        ctrl['unit'] = item['unit']
      return ctrl

    lo, hi, step = item.get('min'), item.get('max'), item.get('step')
    if lo is None or hi is None:
      return None
    numeric_type = 'integer' if _is_integral(lo, hi, step) else 'float'
    ctrl = {
      **base,
      'type': numeric_type,
      'param': key,
      'min': lo,
      'max': hi,
      'increment': step if step is not None else 1,
    }
    if item.get('unit'):
      ctrl['unit'] = item['unit']
    return ctrl

  if widget == 'info':
    return {**base, 'type': 'static_text'}

  logger.warning('settings_schema: unsupported widget %r for key %r', widget, key)
  return None


def _convert_items(items: list[dict]) -> list[dict]:
  return [c for c in (_convert_item(i) for i in items or []) if c is not None]


def _titleize(raw_id: str) -> str:
  """'core_cruise_features' -> 'Core Cruise Features'."""
  return ' '.join(word.capitalize() for word in raw_id.replace('-', '_').split('_') if word)


def _convert_section(section: dict) -> list[dict]:
  """One source section -> one or more portal groups.

  The portal has no nested-panel concept, so each sub_panel is flattened into
  its own sibling group rather than dropped.
  """
  groups = []
  controls = _convert_items(section.get('items'))
  if controls:
    section_id = section.get('id', '')
    groups.append({
      'groupName': section_id,
      # A few sections carry no title; the portal renders that as a blank
      # header, so fall back to the section id.
      'title': section.get('title') or _titleize(section_id),
      'controls': controls,
    })

  for sub in section.get('sub_panels') or []:
    sub_controls = _convert_items(sub.get('items'))
    if sub_controls:
      groups.append({
        'groupName': f"{section.get('id', '')}_{sub.get('id', '')}",
        'title': sub.get('label', section.get('title', '')),
        'controls': sub_controls,
      })
  return groups


def _load_schema() -> dict | None:
  try:
    with open(SETTINGS_UI_JSON) as f:
      return json.load(f)
  except FileNotFoundError:
    logger.error('settings_schema: %s not found', SETTINGS_UI_JSON)
  except (OSError, json.JSONDecodeError) as e:
    logger.error('settings_schema: failed to read %s: %s', SETTINGS_UI_JSON, e)
  return None


def list_panels() -> list[dict]:
  """[{id, name, description, icon}], ordered by the schema's own `order`."""
  schema = _load_schema()
  if not schema:
    return []

  panels = []
  for p in sorted(schema.get('panels', []), key=lambda x: x.get('order', 9999)):
    raw_id = p.get('id')
    if not raw_id:
      continue
    # Skip panels with nothing the portal can render.
    if not any(_convert_section(s) for s in p.get('sections', [])):
      continue
    panels.append({
      'id': _panel_public_id(raw_id),
      'name': p.get('label', raw_id),
      'description': p.get('description', ''),
      'icon': p.get('icon', ''),
    })
  return panels


def iter_params() -> list[dict]:
  """Every param the settings UI exposes, with where it lives.

  [{key, title, panel, panelLabel, group}] -- used by the troubleshoot report
  to diff current values against defaults. Omits the same blocked keys as the
  panel endpoints.
  """
  schema = _load_schema()
  if not schema:
    return []

  out: list[dict] = []
  seen: set[str] = set()
  for p in sorted(schema.get('panels', []), key=lambda x: x.get('order', 9999)):
    panel_label = p.get('label', p.get('id', ''))
    for section in p.get('sections', []):
      for group in _convert_section(section):
        for ctrl in group['controls']:
          key = ctrl.get('param')
          # static_text controls carry no param.
          if not key or key in seen:
            continue
          seen.add(key)
          out.append({
            'key': key,
            'title': ctrl.get('title', key),
            'panel': _panel_public_id(p.get('id', '')),
            'panelLabel': panel_label,
            'group': group.get('title', ''),
          })
  return out


def get_panel(public_id: str) -> dict | None:
  """Full PanelConfig for one panel, or None if unknown."""
  schema = _load_schema()
  if not schema:
    return None

  raw_id = _raw_id_from_public(public_id)
  for p in schema.get('panels', []):
    if p.get('id') != raw_id:
      continue
    groups: list[dict] = []
    for section in p.get('sections', []):
      groups.extend(_convert_section(section))
    return {
      'menuName': p.get('label', raw_id),
      'menuIcon': p.get('icon', ''),
      'menuDescription': p.get('description', ''),
      'groups': groups,
    }
  return None
