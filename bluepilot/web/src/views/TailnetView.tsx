import { useCallback, useEffect, useRef, useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Icon, LoadingSpinner, Button, QRCode } from '@/components/common'
import { tailscaleAPI } from '@/services/api'
import { useToastStore } from '@/stores/useToastStore'
import type { DeviceStatus, TailscaleStatus } from '@/types'
import './TailnetView.css'

interface TailnetViewProps {
  deviceStatus?: DeviceStatus
}

// Poll fast while something is in flight (installing, or waiting on the login
// link to be visited), slowly once the state is settled.
const POLL_BUSY_MS = 1500
const POLL_IDLE_MS = 10000

const STATE_LABELS: Record<string, string> = {
  Running: 'Connected',
  NeedsLogin: 'Waiting for sign-in',
  Starting: 'Starting',
  Stopped: 'Stopped',
  NoState: 'Not configured',
}

export const TailnetView = ({ deviceStatus }: TailnetViewProps) => {
  const [status, setStatus] = useState<TailscaleStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [authkey, setAuthkey] = useState('')
  const [hostname, setHostname] = useState('')
  const addToast = useToastStore((s) => s.addToast)
  const timer = useRef<number | null>(null)
  // Seed the name field from the device once. Without this the poller keeps
  // writing the server value back and overwrites whatever the user is typing.
  const seededHostname = useRef(false)

  const load = useCallback(async () => {
    try {
      const data = await tailscaleAPI.getStatus()
      setStatus(data)
      if (!seededHostname.current && data.hostname) {
        seededHostname.current = true
        setHostname(data.hostname)
      }
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Failed to read tailnet status', 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast])

  // Reschedule after every load so the interval tracks the current state.
  useEffect(() => {
    load()
    const inFlight = status?.install?.running || status?.backend_state === 'NeedsLogin'
    const delay = inFlight ? POLL_BUSY_MS : POLL_IDLE_MS
    timer.current = window.setTimeout(load, delay)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.install?.running, status?.backend_state, status?.installed, status?.daemon_running])

  const act = async (fn: () => Promise<{ success: boolean; error?: string }>, ok: string) => {
    setBusy(true)
    try {
      const res = await fn()
      if (res.success) {
        addToast(ok, 'success')
      } else {
        addToast(res.error || 'Action failed', 'error')
      }
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Action failed', 'error')
    } finally {
      setBusy(false)
      load()
    }
  }

  if (loading) {
    return (
      <>
        <Header deviceStatus={deviceStatus} subtitle="Connect this device to your tailnet" />
        <div className="tailnet-view tailnet-centered">
          <LoadingSpinner message="Reading tailnet status..." />
        </div>
      </>
    )
  }

  const s = status
  const connected = s?.backend_state === 'Running'
  const installing = s?.install?.running

  // Same port the portal is being served on, but at the tailnet address, so the
  // QR keeps working whether this page came from :8088 or a custom port.
  const tailnetIp = s?.ips?.[0]
  const portalUrl = tailnetIp
    ? `${window.location.protocol}//${tailnetIp}${window.location.port ? `:${window.location.port}` : ''}`
    : null

  return (
    <>
      <Header deviceStatus={deviceStatus} subtitle="Connect this device to your tailnet" />
      <div className="tailnet-view">

        <section className="tailnet-card">
          <div className="tailnet-card-head">
            <div>
              <h2>Tailnet</h2>
              <p className="tailnet-sub">
                Puts this device on your Tailscale network so you can reach the portal and SSH
                from anywhere, without port forwarding.
              </p>
            </div>
            <span className={`tailnet-badge ${connected ? 'on' : 'off'}`}>
              {s?.backend_state ? (STATE_LABELS[s.backend_state] ?? s.backend_state) : 'Not installed'}
            </span>
          </div>

          {connected && (
            <>
              <dl className="tailnet-facts">
                <div><dt>Address</dt><dd>{s?.ips?.[0] ?? '—'}</dd></div>
                <div><dt>Name</dt><dd>{s?.hostname ?? '—'}</dd></div>
                {s?.tailnet && <div><dt>Tailnet</dt><dd>{s.tailnet}</dd></div>}
                <div><dt>Peers</dt><dd>{s?.peers ?? 0}</dd></div>
              </dl>

              {portalUrl && (
                <div className="tailnet-reach">
                  <div className="tailnet-qr-wrap tailnet-qr-small">
                    <QRCode value={portalUrl} size={150} title="Portal address on the tailnet" />
                  </div>
                  <div>
                    <h4>Reach this portal from anywhere</h4>
                    <p className="tailnet-sub">
                      Scan on any device that is on your tailnet to open this portal over the VPN.
                      SSH works at the same address.
                    </p>
                    <code className="tailnet-code">{portalUrl}</code>
                  </div>
                </div>
              )}
            </>
          )}
        </section>

        {/* Step 1: get the binaries onto /data */}
        {!s?.installed && (
          <section className="tailnet-card">
            <h3>Install Tailscale</h3>
            <p className="tailnet-sub">
              Downloads the official Tailscale build (~70 MB) to <code>/data/tailscale</code>, which
              survives openpilot updates. Needs an internet connection.
            </p>
            {installing ? (
              <div className="tailnet-progress">
                <div className="tailnet-progress-bar">
                  <span style={{ width: `${s?.install?.percent ?? 0}%` }} />
                </div>
                <span className="tailnet-progress-label">
                  {s?.install?.stage ?? 'working'} {s?.install?.percent ? `${s.install.percent}%` : ''}
                </span>
              </div>
            ) : (
              <Button variant="primary" disabled={busy}
                      onClick={() => act(tailscaleAPI.install, 'Download started')}>
                Install
              </Button>
            )}
            {s?.install?.error && <p className="tailnet-error">{s.install.error}</p>}
          </section>
        )}

        {/* Step 2: sign in */}
        {s?.installed && !connected && (
          <section className="tailnet-card">
            <h3>Connect</h3>

            {s?.auth_url ? (
              <div className="tailnet-auth">
                <p className="tailnet-sub">
                  Scan this with the phone that is signed in to your tailnet, approve the device,
                  and this page will switch to connected on its own.
                </p>
                <div className="tailnet-qr-wrap">
                  <QRCode value={s.auth_url} size={240} title="Tailscale sign-in link" />
                </div>
                <p className="tailnet-sub tailnet-hint">Or open the link directly:</p>
                <a className="tailnet-authlink" href={s.auth_url} target="_blank" rel="noreferrer">
                  {s.auth_url}
                </a>
              </div>
            ) : (
              <>
                <label className="tailnet-field">
                  <span>Device name</span>
                  <input value={hostname} onChange={(e) => setHostname(e.target.value)}
                         placeholder="bluedragon" spellCheck={false} />
                </label>

                <label className="tailnet-field">
                  <span>Auth key <em>(optional)</em></span>
                  <input value={authkey} onChange={(e) => setAuthkey(e.target.value)}
                         placeholder="tskey-auth-..." type="password" spellCheck={false}
                         autoComplete="off" />
                </label>
                <p className="tailnet-sub tailnet-hint">
                  Leave the key blank to get a sign-in link you can open on your phone. Paste a
                  pre-generated auth key instead if you would rather not sign in interactively.
                </p>

                <Button variant="primary" disabled={busy}
                        onClick={() => act(() => tailscaleAPI.up({ authkey, hostname }),
                                           authkey ? 'Joined tailnet' : 'Sign-in link requested')}>
                  {busy ? 'Working...' : 'Connect'}
                </Button>
              </>
            )}
          </section>
        )}

        {/* Step 3: manage */}
        {s?.installed && (
          <section className="tailnet-card">
            <h3>Manage</h3>
            <div className="tailnet-actions">
              {connected && (
                <Button variant="secondary" disabled={busy}
                        onClick={() => act(tailscaleAPI.down, 'Disconnected from tailnet')}>
                  Disconnect
                </Button>
              )}
              {!connected && s?.daemon_running && (
                <Button variant="secondary" disabled={busy}
                        onClick={() => act(tailscaleAPI.down, 'Stopped')}>
                  Cancel
                </Button>
              )}
            </div>
            <dl className="tailnet-facts tailnet-facts-muted">
              <div><dt>Version</dt><dd>{s?.version ?? '—'}</dd></div>
              <div><dt>Daemon</dt><dd>{s?.daemon_running ? 'Running' : 'Stopped'}</dd></div>
              <div>
                <dt>Mode</dt>
                <dd>
                  {s?.tun ? 'Kernel networking' : 'Userspace networking'}
                  <Icon name="info" size={14} className="tailnet-info-icon" />
                </dd>
              </div>
            </dl>
            {!s?.tun && (
              <p className="tailnet-sub tailnet-hint">
                This device has no TUN interface, so Tailscale runs in userspace mode. The portal
                and SSH are still reachable over the tailnet; the device just cannot act as a
                subnet router.
              </p>
            )}
          </section>
        )}
      </div>
    </>
  )
}
