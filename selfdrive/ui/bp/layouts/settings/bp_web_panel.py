import pyray as rl
import subprocess
import threading
import time
import json
import urllib.request

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import FontWeight, MousePos
from openpilot.system.ui.widgets.label import gui_label
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets.list_view import toggle_item
from openpilot.system.ui.lib.multilang import tr
from openpilot.selfdrive.ui.ui_state import ui_state

try:
  import qrcode
  import numpy as np
  _HAS_QR = True
except ImportError:
  _HAS_QR = False


PADDING = 30
BLUE = rl.Color(33, 150, 243, 255)
GREEN = rl.Color(76, 175, 80, 255)
GRAY = rl.Color(128, 128, 128, 255)
LIGHT_GRAY = rl.Color(170, 170, 170, 255)
INSET_BG = rl.Color(28, 28, 28, 255)


class _QRCodeSection(Widget):
  """Displays server status, QR code, and URL when server is enabled."""

  QR_SIZE = 320

  def __init__(self, params: Params):
    super().__init__()
    self._params = params
    self._qr_texture: rl.Texture | None = None
    self._last_url = ""
    # Height: status(50) + spacing(20) + QR(320) + spacing(15) + URL(48) + hint(38) + padding
    self.set_rect(rl.Rectangle(0, 0, 0, 530))

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _get_wifi_ip(self) -> str:
    """Get WiFi interface IP address."""
    try:
      result = subprocess.run(['ip', 'addr', 'show', 'wlan0'],
                              capture_output=True, text=True, timeout=2)
      for line in result.stdout.split('\n'):
        if 'inet ' in line:
          ip = line.strip().split()[1].split('/')[0]
          if ip and not ip.startswith('127.'):
            return ip
    except Exception:
      pass
    try:
      for iface in ['wlan1', 'wlan2']:
        result = subprocess.run(['ip', 'addr', 'show', iface],
                                capture_output=True, text=True, timeout=2)
        for line in result.stdout.split('\n'):
          if 'inet ' in line:
            ip = line.strip().split()[1].split('/')[0]
            if ip and not ip.startswith('127.'):
              return ip
    except Exception:
      pass
    return ""

  def get_server_url(self) -> str:
    """Build server URL from WiFi IP and port param."""
    ip = self._get_wifi_ip()
    if not ip:
      return ""
    port = self._params.get("BPPortalPort") or "8088"
    return f"http://{ip}:{port}"

  def _generate_qr(self):
    """Generate QR code texture from server URL."""
    if not _HAS_QR:
      return
    url = self.get_server_url()
    if not url:
      self._qr_texture = None
      return
    if url == self._last_url and self._qr_texture:
      return
    self._last_url = url
    try:
      qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
      qr.add_data(url)
      qr.make(fit=True)
      pil_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
      img_array = np.array(pil_img, dtype=np.uint8)
      if self._qr_texture and self._qr_texture.id != 0:
        rl.unload_texture(self._qr_texture)
      rl_image = rl.Image()
      rl_image.data = rl.ffi.cast("void *", img_array.ctypes.data)
      rl_image.width = pil_img.width
      rl_image.height = pil_img.height
      rl_image.mipmaps = 1
      rl_image.format = rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8
      self._qr_texture = rl.load_texture_from_image(rl_image)
    except Exception as e:
      cloudlog.warning(f"QR code generation failed: {e}")
      self._qr_texture = None

  def _render(self, rect):
    enabled = self._params.get_bool("EnableWebRoutesServer")
    if not enabled:
      gui_label(
        rl.Rectangle(rect.x + PADDING, rect.y + 20, rect.width - 2 * PADDING, 60),
        "Enable the server above to access BluePilot Portal",
        font_size=42, color=GRAY, font_weight=FontWeight.NORMAL,
      )
      return

    self._generate_qr()
    url = self.get_server_url()
    y = rect.y + 15

    # Status dot + text
    rl.draw_circle(int(rect.x + PADDING + 8), int(y + 20), 8, GREEN)
    gui_label(
      rl.Rectangle(rect.x + PADDING + 30, y, rect.width - 2 * PADDING - 30, 40),
      "Server Enabled", font_size=40, color=LIGHT_GRAY, font_weight=FontWeight.NORMAL,
    )
    y += 55

    # QR code centered
    qr_x = rect.x + (rect.width - self.QR_SIZE) / 2
    if self._qr_texture:
      src = rl.Rectangle(0, 0, self._qr_texture.width, self._qr_texture.height)
      dst = rl.Rectangle(qr_x, y, self.QR_SIZE, self.QR_SIZE)
      rl.draw_texture_pro(self._qr_texture, src, dst, rl.Vector2(0, 0), 0, rl.WHITE)
    else:
      ph = rl.Rectangle(qr_x, y, self.QR_SIZE, self.QR_SIZE)
      rl.draw_rectangle_rounded(ph, 0.05, 20, rl.Color(40, 40, 40, 255))
      msg = "No WiFi Connection" if not url else "QR Code Error"
      gui_label(
        rl.Rectangle(qr_x, y + self.QR_SIZE / 2 - 20, self.QR_SIZE, 40),
        msg, font_size=35, color=GRAY, font_weight=FontWeight.NORMAL,
      )
    y += self.QR_SIZE + 15

    # URL display
    if url:
      gui_label(
        rl.Rectangle(rect.x + PADDING, y, rect.width - 2 * PADDING, 48),
        url, font_size=44, color=BLUE, font_weight=FontWeight.MEDIUM,
      )
      y += 52
      gui_label(
        rl.Rectangle(rect.x + PADDING, y, rect.width - 2 * PADDING, 38),
        "Scan QR code or enter URL in your browser",
        font_size=35, color=GRAY, font_weight=FontWeight.NORMAL,
      )

  def __del__(self):
    if hasattr(self, '_qr_texture') and self._qr_texture and self._qr_texture.id != 0:
      rl.unload_texture(self._qr_texture)


class _TailnetSection(Widget):
  """Join this device to a Tailscale tailnet, with a sign-in QR you scan here.

  The whole point is not having to open the portal on another machine first:
  press Connect, scan the code off the device screen with the phone that is
  already signed in to the tailnet, approve, done.

  Everything that touches the network runs on a background thread -- this is the
  UI thread, and blocking it freezes the device screen. Texture upload is a GL
  call, so that stays on the render thread.
  """

  QR_SIZE = 320
  POLL_S = 2.5
  BASE_H = 250

  def __init__(self):
    super().__init__()
    self._status: dict = {}
    self._loading = False
    self._busy_label = ""
    self._last_poll = 0.0
    self._qr_texture: rl.Texture | None = None
    self._qr_value = ""
    self._unavailable = False
    self.set_rect(rl.Rectangle(0, 0, 0, self.BASE_H))

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  # -- state -------------------------------------------------------------

  def _ts(self):
    """Import lazily and defensively: a broken import here must not take the
    settings UI down with it."""
    from bluepilot.backend.network import tailscale
    return tailscale

  def _refresh(self):
    if self._loading:
      return
    self._loading = True

    def _fetch():
      try:
        self._status = self._ts().status()
        self._unavailable = False
      except Exception as e:
        cloudlog.warning(f"tailnet status failed: {e}")
        self._unavailable = True
      finally:
        self._loading = False
        self._last_poll = time.monotonic()
        self._update_height()

    threading.Thread(target=_fetch, daemon=True, name='tailnet-status').start()

  def _update_height(self):
    self._rect.height = self.BASE_H + (self.QR_SIZE + 40 if self._auth_url() else 0)

  def _auth_url(self) -> str:
    return self._status.get('auth_url') or ""

  def _action(self, fn, label: str):
    """Run install/up/down off the UI thread."""
    if self._busy_label:
      return
    self._busy_label = label

    def _run():
      try:
        fn()
      except Exception as e:
        cloudlog.warning(f"tailnet action failed: {e}")
      finally:
        self._busy_label = ""
        self._last_poll = 0.0  # force an immediate refresh

    threading.Thread(target=_run, daemon=True, name='tailnet-action').start()

  # -- qr ----------------------------------------------------------------

  def _ensure_qr(self, value: str):
    """Build the QR texture when the sign-in URL first appears. Cheap enough to
    do inline, and it must be here anyway -- texture upload needs the GL
    context that lives on this thread."""
    if not _HAS_QR or value == self._qr_value:
      return
    self._qr_value = value
    if self._qr_texture and self._qr_texture.id != 0:
      rl.unload_texture(self._qr_texture)
      self._qr_texture = None
    if not value:
      return
    try:
      qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                         box_size=10, border=4)
      qr.add_data(value)
      qr.make(fit=True)
      pil_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
      img_array = np.array(pil_img, dtype=np.uint8)
      rl_image = rl.Image()
      rl_image.data = rl.ffi.cast("void *", img_array.ctypes.data)
      rl_image.width = pil_img.width
      rl_image.height = pil_img.height
      rl_image.mipmaps = 1
      rl_image.format = rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8
      self._qr_texture = rl.load_texture_from_image(rl_image)
    except Exception as e:
      cloudlog.warning(f"tailnet QR generation failed: {e}")
      self._qr_texture = None

  # -- layout ------------------------------------------------------------

  def _btn_rect(self) -> rl.Rectangle:
    w = self._rect.width - 2 * PADDING
    btn_w, btn_h = 320, 55
    return rl.Rectangle(self._rect.x + PADDING + (w - btn_w) / 2,
                        self._rect.y + 15 + 65 + 60, btn_w, btn_h)

  def _button(self) -> tuple[str, str] | None:
    """(label, action) for the current state, or None if there is nothing to do."""
    if self._unavailable or not self._status:
      return None
    if self._status.get('install', {}).get('running'):
      return None
    if not self._status.get('installed'):
      return ("Install Tailscale", 'install')
    if self._status.get('backend_state') == 'Running':
      return ("Disconnect", 'down')
    if self._auth_url():
      return None  # waiting on the scan
    return ("Connect", 'up')

  def _status_line(self) -> tuple[str, rl.Color]:
    if self._unavailable:
      return ("Tailnet support unavailable", GRAY)
    if not self._status:
      return ("Checking...", GRAY)
    inst = self._status.get('install', {})
    if inst.get('running'):
      return (f"Installing... {inst.get('percent', 0)}%", BLUE)
    if inst.get('error'):
      return (f"Install failed: {inst['error']}"[:60], rl.Color(244, 67, 54, 255))
    if not self._status.get('installed'):
      return ("Not installed", GRAY)
    state = self._status.get('backend_state')
    if state == 'Running':
      ips = self._status.get('ips') or []
      return (f"Connected  {ips[0] if ips else ''}".strip(), GREEN)
    if self._auth_url():
      return ("Scan to add this device to your tailnet", BLUE)
    return ("Not connected", GRAY)

  # -- render ------------------------------------------------------------

  def _render(self, rect):
    if time.monotonic() - self._last_poll > self.POLL_S:
      self._refresh()

    y = rect.y + 15
    x = rect.x + PADDING
    w = rect.width - 2 * PADDING

    gui_label(rl.Rectangle(x, y, w, 50), "Tailnet",
              font_size=46, color=BLUE, font_weight=FontWeight.BOLD)
    y += 65

    text, color = self._status_line()
    gui_label(rl.Rectangle(x, y, w, 50), text,
              font_size=34, color=color, font_weight=FontWeight.NORMAL)
    y += 60

    btn = self._button()
    if btn or self._busy_label:
      br = self._btn_rect()
      idle = not self._busy_label
      rl.draw_rectangle_rounded(br, 0.5, 10,
                                rl.Color(50, 50, 50, 255) if idle else rl.Color(35, 35, 35, 255))
      gui_label(br, self._busy_label or btn[0], font_size=36, color=LIGHT_GRAY,
                font_weight=FontWeight.MEDIUM)
    y += 70

    auth = self._auth_url()
    self._ensure_qr(auth)
    if auth and self._qr_texture:
      qr_x = rect.x + (rect.width - self.QR_SIZE) / 2
      src = rl.Rectangle(0, 0, self._qr_texture.width, self._qr_texture.height)
      dst = rl.Rectangle(qr_x, y, self.QR_SIZE, self.QR_SIZE)
      rl.draw_texture_pro(self._qr_texture, src, dst, rl.Vector2(0, 0), 0, rl.WHITE)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    btn = self._button()
    if not btn or self._busy_label:
      return
    if not rl.check_collision_point_rec(mouse_pos, self._btn_rect()):
      return
    _label, action = btn
    if action == 'install':
      self._action(lambda: self._ts().start_install(), "Starting...")
    elif action == 'up':
      # No auth key from the device UI -- this is the flow that produces the
      # sign-in URL we render as a QR.
      self._action(lambda: self._ts().up(), "Connecting...")
    elif action == 'down':
      self._action(lambda: self._ts().down(), "Disconnecting...")

  def __del__(self):
    if hasattr(self, '_qr_texture') and self._qr_texture and self._qr_texture.id != 0:
      rl.unload_texture(self._qr_texture)


class _HelpSection(Widget):
  """Shows BluePilot Portal feature descriptions."""

  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, 0, 420))

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _render(self, rect):
    y = rect.y + 15
    x = rect.x + PADDING
    w = rect.width - 2 * PADDING

    gui_label(
      rl.Rectangle(x, y, w, 50),
      "BluePilot Portal Features",
      font_size=46, color=BLUE, font_weight=FontWeight.BOLD,
    )
    y += 65

    features = [
      ("Dashboard:", "Device status, system health, driving statistics"),
      ("Routes:", "Browse drives, multi-camera video, preserve favorites, export"),
      ("Settings:", "Manage settings with favorites, search, backup/restore"),
      ("Parameters:", "View and edit all system parameters with live sync"),
      ("Logs:", "Live system diagnostics with real-time streaming"),
    ]
    for name, desc in features:
      gui_label(
        rl.Rectangle(x + 15, y, w - 15, 40),
        f"  {name}  {desc}",
        font_size=36, color=LIGHT_GRAY, font_weight=FontWeight.NORMAL,
      )
      y += 48

    y += 10
    gui_label(
      rl.Rectangle(x, y, w, 40),
      "Open on any device browser. Can be added to home screen as an app.",
      font_size=34, color=GRAY, font_weight=FontWeight.NORMAL,
    )
    y += 42
    gui_label(
      rl.Rectangle(x, y, w, 40),
      "Safety: Full interface locked while driving.",
      font_size=34, color=GRAY, font_weight=FontWeight.NORMAL,
    )


class _StatsSection(Widget):
  """Shows route statistics fetched from the portal API."""

  def __init__(self, params: Params, qr_section: _QRCodeSection):
    super().__init__()
    self._params = params
    self._qr_section = qr_section
    self._route_count = "..."
    self._total_size = "..."
    self._newest_route = "..."
    self._loading = False
    # Height: title(50) + spacing(15) + stats row(55) + spacing(15) + refresh btn(55) + padding
    self.set_rect(rl.Rectangle(0, 0, 0, 250))

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def refresh_stats(self):
    """Fetch route statistics from the portal API in a background thread."""
    if self._loading:
      return
    self._loading = True
    self._route_count = "Loading..."
    self._total_size = "..."
    self._newest_route = "..."

    def _fetch():
      try:
        url = self._qr_section.get_server_url()
        if not url:
          self._route_count = "No WiFi"
          self._total_size = "-"
          self._newest_route = "-"
          return
        req = urllib.request.Request(f"{url}/api/routes")
        with urllib.request.urlopen(req, timeout=5) as resp:
          data = json.loads(resp.read())
          if data.get("success"):
            routes = data.get("routes", [])
            self._route_count = str(len(routes))
            total_bytes = sum(r.get("sizeBytes", 0) for r in routes)
            self._total_size = f"{total_bytes / (1024 ** 3):.1f} GB"
            if routes:
              first = routes[0]
              dt = first.get("displayTime", "")
              dd = first.get("displayDate", "").split(" - ")[0] if first.get("displayDate") else ""
              self._newest_route = f"{dt} {dd}".strip() or "Unknown"
            else:
              self._newest_route = "None"
          else:
            self._route_count = "Error"
            self._total_size = "-"
            self._newest_route = "-"
      except Exception as e:
        cloudlog.debug(f"Stats fetch failed: {e}")
        self._route_count = "Not responding"
        self._total_size = "-"
        self._newest_route = "-"
      finally:
        self._loading = False

    threading.Thread(target=_fetch, daemon=True).start()

  def _get_btn_rect(self) -> rl.Rectangle:
    """Calculate the refresh button rect based on current widget position."""
    w = self._rect.width - 2 * PADDING
    btn_w, btn_h = 280, 55
    btn_y = self._rect.y + 15 + 65 + 70  # title + stats row + spacing
    return rl.Rectangle(self._rect.x + PADDING + (w - btn_w) / 2, btn_y, btn_w, btn_h)

  def _render(self, rect):
    if not self._params.get_bool("EnableWebRoutesServer"):
      return

    y = rect.y + 15
    x = rect.x + PADDING
    w = rect.width - 2 * PADDING

    gui_label(
      rl.Rectangle(x, y, w, 50),
      "Routes Overview",
      font_size=46, color=BLUE, font_weight=FontWeight.BOLD,
    )
    y += 65

    # Stats in a row with inset backgrounds
    col_w = w // 3
    for i, text in enumerate([
      f"Routes: {self._route_count}",
      f"Size: {self._total_size}",
      f"Newest: {self._newest_route}",
    ]):
      sr = rl.Rectangle(x + i * col_w + 5, y, col_w - 10, 55)
      rl.draw_rectangle_rounded(sr, 0.3, 10, INSET_BG)
      gui_label(sr, text, font_size=33, color=rl.WHITE, font_weight=FontWeight.NORMAL)
    y += 70

    # Refresh button
    btn_rect = self._get_btn_rect()
    btn_color = rl.Color(35, 35, 35, 255) if self._loading else rl.Color(50, 50, 50, 255)
    rl.draw_rectangle_rounded(btn_rect, 0.5, 10, btn_color)
    btn_text = "Loading..." if self._loading else "Refresh Stats"
    gui_label(btn_rect, btn_text, font_size=36, color=LIGHT_GRAY, font_weight=FontWeight.MEDIUM)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._loading or not self._params.get_bool("EnableWebRoutesServer"):
      return
    if rl.check_collision_point_rec(mouse_pos, self._get_btn_rect()):
      self.refresh_stats()


class BPWebPanel(Widget):
  """BluePilot Web Portal settings panel - ported from BP 5.0 QT panel.

  Provides server control, QR code access, feature descriptions,
  and route statistics display.
  """

  def __init__(self):
    super().__init__()
    self._params = Params()

    # Server enable/disable toggle
    self._server_toggle = toggle_item(
      lambda: tr("Enable Web Routes Server"),
      lambda: tr("Enable the web server for viewing logs and videos over WiFi."),
      initial_state=self._params.get_bool("EnableWebRoutesServer"),
      callback=self._on_toggle,
    )

    # QR code & URL display section
    self._qr_section = _QRCodeSection(self._params)

    # Tailnet (Tailscale) join + sign-in QR
    self._tailnet_section = _TailnetSection()

    # Feature help text section
    self._help_section = _HelpSection()

    # Route statistics section
    self._stats_section = _StatsSection(self._params, self._qr_section)

    # Scrollable layout with all sections
    self._scroller = Scroller(
      [self._server_toggle, self._qr_section, self._tailnet_section, self._help_section, self._stats_section],
      line_separator=True, spacing=0,
    )

    ui_state.add_offroad_transition_callback(self._refresh_state)

  def _on_toggle(self, state: bool):
    """Handle server toggle state change."""
    self._params.put_bool("EnableWebRoutesServer", state)
    if state:
      self._stats_section.refresh_stats()

  def _refresh_state(self):
    """Sync toggle state from params (handles external changes)."""
    ui_state.update_params()
    self._server_toggle.action_item.set_state(
      ui_state.params.get_bool("EnableWebRoutesServer")
    )

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
    self._refresh_state()
    if self._params.get_bool("EnableWebRoutesServer"):
      self._stats_section.refresh_stats()

  def _render(self, rect):
    self._scroller.render(rect)
