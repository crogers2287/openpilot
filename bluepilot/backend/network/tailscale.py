"""Tailnet (Tailscale) support for the portal.

Why the portal supervises tailscaled instead of the manager:
selfdrived raises EventName.processNotRunning for ANY managed process that
`shouldBeRunning` but isn't, and that event is a NO_ENTRY + SOFT_DISABLE -- it
refuses to engage and drops you out mid-drive (this is exactly what a crashed
dmonitoringd did). A convenience VPN must never be able to do that, so tailscaled
is started and stopped by the portal process, which is itself optional and
outside the driving path. If tailscale dies, nothing about driving changes.

Everything lives under /data/tailscale so it survives both openpilot updates
(which replace /data/openpilot) and AGNOS reflashes (which replace the
read-only root filesystem). Nothing is written outside /data.

Note on trust: bp_portal has no authentication, so anyone who can reach the
portal can drive these endpoints. That is the portal's existing posture (it
already exposes param read/write). Auth keys are treated as secrets regardless:
never logged, never persisted, never returned by the status endpoint.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

TS_DIR = Path('/data/tailscale')
BIN_DIR = TS_DIR / 'bin'
TAILSCALE = BIN_DIR / 'tailscale'
TAILSCALED = BIN_DIR / 'tailscaled'
STATE_FILE = TS_DIR / 'tailscaled.state'
SOCKET = TS_DIR / 'tailscaled.sock'
DAEMON_LOG = TS_DIR / 'tailscaled.log'
CONFIG = TS_DIR / 'portal.json'

PKGS_INDEX = 'https://pkgs.tailscale.com/stable/?mode=json'
PKGS_BASE = 'https://pkgs.tailscale.com/stable/'

# Progress record for the background install, read by the status endpoint.
_install_lock = threading.Lock()
_install_state: dict = {'running': False, 'stage': None, 'percent': 0, 'error': None}


# ---------------------------------------------------------------- helpers

def _arch() -> str:
  """Map uname machine -> tailscale's tarball arch. comma 3X is aarch64."""
  m = platform.machine().lower()
  return {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'amd64', 'amd64': 'amd64'}.get(m, m)


def _read_config() -> dict:
  try:
    with open(CONFIG) as f:
      return json.load(f)
  except (OSError, json.JSONDecodeError):
    return {}


def _write_config(**kwargs) -> None:
  cfg = _read_config()
  cfg.update(kwargs)
  try:
    TS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
      json.dump(cfg, f)
    os.replace(tmp, CONFIG)  # atomic; a half-written config must never win
  except OSError as e:
    logger.error(f'tailscale: could not write config: {e}')


def default_hostname() -> str:
  cfg = _read_config()
  if cfg.get('hostname'):
    return str(cfg['hostname'])
  return 'bluedragon'


def is_installed() -> bool:
  return TAILSCALE.is_file() and TAILSCALED.is_file() and os.access(TAILSCALED, os.X_OK)


def _run(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
  """Run a tailscale CLI command. Never raises."""
  try:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()
  except subprocess.TimeoutExpired:
    return 124, '', f'timed out after {timeout}s'
  except OSError as e:
    return 1, '', str(e)


def _cli(*args: str, timeout: int = 30) -> tuple[int, str, str]:
  return _run([str(TAILSCALE), '--socket', str(SOCKET), *args], timeout=timeout)


# ---------------------------------------------------------------- install

def _download(url: str, dest: Path, on_progress=None) -> None:
  with urllib.request.urlopen(url, timeout=60) as r:
    total = int(r.headers.get('Content-Length') or 0)
    done = 0
    with open(dest, 'wb') as f:
      while True:
        chunk = r.read(256 * 1024)
        if not chunk:
          break
        f.write(chunk)
        done += len(chunk)
        if on_progress and total:
          on_progress(int(done * 100 / total))


def _do_install() -> None:
  def stage(name, percent=None):
    with _install_lock:
      _install_state['stage'] = name
      if percent is not None:
        _install_state['percent'] = percent
    logger.info(f'tailscale install: {name}')

  try:
    stage('finding latest release', 0)
    with urllib.request.urlopen(PKGS_INDEX, timeout=30) as r:
      index = json.load(r)

    arch = _arch()
    tarball = (index.get('Tarballs') or {}).get(arch)
    if not tarball:
      raise RuntimeError(f'no tailscale static build for arch {arch!r}')

    TS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(TS_DIR)) as td:
      tgz = Path(td) / tarball
      stage(f'downloading {index.get("TarballsVersion", "")}'.strip(), 0)
      _download(PKGS_BASE + tarball, tgz, on_progress=_set_percent)

      stage('extracting', 100)
      with tarfile.open(tgz) as tf:
        wanted = {}
        for member in tf.getmembers():
          base = os.path.basename(member.name)
          if member.isfile() and base in ('tailscale', 'tailscaled'):
            wanted[base] = member
        if len(wanted) != 2:
          raise RuntimeError('tarball did not contain both tailscale and tailscaled')

        staging = Path(td) / 'bin'
        staging.mkdir()
        for base, member in wanted.items():
          src = tf.extractfile(member)
          if src is None:
            raise RuntimeError(f'could not read {base} from tarball')
          out = staging / base
          with open(out, 'wb') as f:
            shutil.copyfileobj(src, f)
          out.chmod(0o755)

        # Swap in only once both binaries are present and executable.
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        for base in wanted:
          os.replace(staging / base, BIN_DIR / base)

    _write_config(version=index.get('TarballsVersion'))
    stage('done', 100)
    with _install_lock:
      _install_state.update(running=False, error=None)
    logger.info('tailscale: install complete')
  except Exception as e:
    logger.error(f'tailscale: install failed: {e}', exc_info=True)
    with _install_lock:
      _install_state.update(running=False, stage='failed', error=str(e))


def _set_percent(p: int) -> None:
  with _install_lock:
    _install_state['percent'] = p


def start_install() -> dict:
  """Kick off the download in the background; poll /api/tailscale/status."""
  with _install_lock:
    if _install_state['running']:
      return {'success': True, 'already_running': True}
    _install_state.update(running=True, stage='starting', percent=0, error=None)
  threading.Thread(target=_do_install, daemon=True, name='tailscale-install').start()
  return {'success': True}


def install_progress() -> dict:
  with _install_lock:
    return dict(_install_state)


# ---------------------------------------------------------------- daemon

def _daemon_pid() -> int | None:
  """PID of our tailscaled (matched by our own binary path), if running."""
  try:
    out = subprocess.run(['pgrep', '-f', str(TAILSCALED)], capture_output=True,
                         text=True, timeout=10).stdout.split()
    return int(out[0]) if out else None
  except (OSError, ValueError, subprocess.TimeoutExpired):
    return None


def daemon_running() -> bool:
  return _daemon_pid() is not None


def _tun_available() -> bool:
  return Path('/dev/net/tun').exists()


def start_daemon() -> tuple[bool, str]:
  """Start tailscaled if it isn't already up. Returns (ok, message)."""
  if not is_installed():
    return False, 'tailscale is not installed'
  if daemon_running():
    return True, 'already running'

  TS_DIR.mkdir(parents=True, exist_ok=True)
  cmd = [str(TAILSCALED),
         '--state', str(STATE_FILE),
         '--socket', str(SOCKET)]
  # AGNOS may not expose /dev/net/tun. Userspace networking still gives full
  # tailnet reachability (inbound is proxied to localhost services), it just
  # can't act as a subnet router -- the right trade for a device like this.
  if not _tun_available():
    cmd += ['--tun', 'userspace-networking']

  try:
    log = open(DAEMON_LOG, 'ab')
    subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True)  # survive portal restarts
  except OSError as e:
    return False, f'could not start tailscaled: {e}'

  # Wait for the control socket to appear so callers can act immediately.
  for _ in range(50):
    if SOCKET.exists() and daemon_running():
      return True, 'started'
    time.sleep(0.1)
  return daemon_running(), 'started (socket slow to appear)'


def stop_daemon() -> tuple[bool, str]:
  pid = _daemon_pid()
  if pid is None:
    return True, 'not running'
  try:
    os.kill(pid, 15)
    for _ in range(50):
      if not daemon_running():
        return True, 'stopped'
      time.sleep(0.1)
    return False, 'tailscaled did not exit'
  except OSError as e:
    return False, str(e)


# ---------------------------------------------------------------- up/down

def up(authkey: str | None = None, hostname: str | None = None) -> dict:
  """Join the tailnet.

  With an auth key this completes synchronously. Without one, tailscaled enters
  NeedsLogin and reports an AuthURL, which status() surfaces for the user to
  open on their phone -- the easier path, since it needs no key generated up
  front.
  """
  ok, msg = start_daemon()
  if not ok:
    return {'success': False, 'error': msg}

  hostname = (hostname or default_hostname()).strip() or 'bluedragon'
  _write_config(enabled=True, hostname=hostname)

  args = ['up', '--hostname', hostname, '--reset']
  if authkey:
    # Synchronous: the key authenticates us outright.
    code, _out, err = _cli(*args, '--authkey', authkey, timeout=90)
    if code != 0:
      return {'success': False, 'error': err or 'tailscale up failed'}
    return {'success': True, 'status': status()}

  # Interactive: `up` blocks until the user visits the URL, so run it detached
  # and let status() report the AuthURL that tailscaled publishes.
  try:
    log = open(DAEMON_LOG, 'ab')
    subprocess.Popen([str(TAILSCALE), '--socket', str(SOCKET), *args],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True)
  except OSError as e:
    return {'success': False, 'error': str(e)}

  # Give tailscaled a moment to publish the login URL.
  for _ in range(60):
    st = status()
    if st.get('auth_url') or st.get('backend_state') == 'Running':
      return {'success': True, 'status': st}
    time.sleep(0.25)
  return {'success': True, 'status': status()}


def down() -> dict:
  _write_config(enabled=False)
  if not is_installed():
    return {'success': True}
  code, _out, err = _cli('down', timeout=30)
  stop_daemon()
  if code != 0:
    return {'success': False, 'error': err or 'tailscale down failed'}
  return {'success': True}


# ---------------------------------------------------------------- status

def status() -> dict:
  """Never raises, and never returns the auth key."""
  cfg = _read_config()
  out: dict = {
    'installed': is_installed(),
    'daemon_running': daemon_running(),
    'enabled': bool(cfg.get('enabled')),
    'hostname': default_hostname(),
    'version': cfg.get('version'),
    'tun': _tun_available(),
    'backend_state': None,
    'auth_url': None,
    'ips': [],
    'tailnet': None,
    'peers': 0,
    'install': install_progress(),
  }
  if not out['installed'] or not out['daemon_running']:
    return out

  code, raw, _err = _cli('status', '--json', timeout=20)
  if code != 0 or not raw:
    return out
  try:
    js = json.loads(raw)
  except json.JSONDecodeError:
    return out

  out['backend_state'] = js.get('BackendState')
  out['auth_url'] = js.get('AuthURL') or None
  self_node = js.get('Self') or {}
  out['ips'] = self_node.get('TailscaleIPs') or []
  out['hostname'] = self_node.get('HostName') or out['hostname']
  out['peers'] = len(js.get('Peer') or {})
  magic = js.get('CurrentTailnet') or {}
  out['tailnet'] = magic.get('Name') or magic.get('MagicDNSSuffix')
  return out


def autostart() -> None:
  """Bring the tailnet back up on portal start if the user enabled it.

  Best-effort and fully swallowed: a tailnet problem must never stop the portal
  from serving.
  """
  try:
    cfg = _read_config()
    if not cfg.get('enabled') or not is_installed():
      return
    if daemon_running():
      return
    ok, msg = start_daemon()
    logger.info(f'tailscale autostart: {msg}')
  except Exception as e:
    logger.error(f'tailscale autostart failed: {e}')
