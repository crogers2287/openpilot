import { useCallback, useEffect, useMemo, useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Icon, LoadingSpinner } from '@/components/common'
import { troubleshootAPI } from '@/services/api'
import { useToastStore } from '@/stores/useToastStore'
import type { DeviceStatus, TroubleshootReport, SettingsDiffItem } from '@/types'
import './TroubleshootView.css'

interface TroubleshootViewProps {
  deviceStatus?: DeviceStatus
}

// carState only exists onroad, so poll rather than fetch once -- the interesting
// case is watching a fault appear while the truck is running.
const VEHICLE_POLL_MS = 3000

const FAULT_LABELS: Record<string, string> = {
  steerFaultTemporary: 'Steering fault (temporary)',
  steerFaultPermanent: 'Steering fault (permanent)',
  accFaulted: 'ACC faulted',
  canTimeout: 'CAN timeout',
}

const formatValue = (v: string | number | boolean | null): string => {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  return String(v)
}

export const TroubleshootView = ({ deviceStatus }: TroubleshootViewProps) => {
  const [report, setReport] = useState<TroubleshootReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [changedOnly, setChangedOnly] = useState(true)
  const addToast = useToastStore((s) => s.addToast)

  const load = useCallback(async () => {
    try {
      const data = await troubleshootAPI.getReport()
      setReport(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load report')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Refresh only the cheap half on a timer.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const vehicle = await troubleshootAPI.getVehicleStatus()
        setReport((prev) => (prev ? { ...prev, vehicle } : prev))
      } catch {
        // Transient; the next tick will retry.
      }
    }, VEHICLE_POLL_MS)
    return () => clearInterval(id)
  }, [])

  const items = report?.settings?.items ?? []
  const visible = useMemo(
    () => (changedOnly ? items.filter((i) => i.changed) : items),
    [items, changedOnly]
  )

  const grouped = useMemo(() => {
    const out = new Map<string, SettingsDiffItem[]>()
    for (const item of visible) {
      const list = out.get(item.panelLabel) ?? []
      list.push(item)
      out.set(item.panelLabel, list)
    }
    return Array.from(out.entries())
  }, [visible])

  const copyReport = async () => {
    if (!report) return
    const lines: string[] = ['# BluePilot troubleshoot report', '']

    const v = report.vehicle
    lines.push('## Vehicle')
    if (!v?.available) {
      lines.push(`unavailable: ${v?.reason ?? 'unknown'}`)
    } else {
      lines.push(`healthy: ${v.healthy}`)
      Object.entries(v.faults ?? {}).forEach(([k, val]) => lines.push(`${k}: ${val}`))
      lines.push(`canErrorCounter: ${v.canErrorCounter}`)
      lines.push(`gear: ${v.gearShifter}  vEgo: ${v.vEgo?.toFixed(2)}`)
      if (v.cruise) {
        lines.push(
          `cruise: available=${v.cruise.available} enabled=${v.cruise.enabled} nonAdaptive=${v.cruise.nonAdaptive}`
        )
      }
    }

    lines.push('', `## Changed settings (${report.settings?.changedCount ?? 0})`)
    for (const item of items.filter((i) => i.changed)) {
      lines.push(`${item.key} = ${formatValue(item.current)}  (default ${formatValue(item.default)})`)
    }

    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      addToast('Report copied to clipboard', 'success')
    } catch {
      addToast('Could not copy to clipboard', 'error')
    }
  }

  const vehicle = report?.vehicle
  const activeFaults = Object.entries(vehicle?.faults ?? {}).filter(
    ([k, v]) => k !== 'canValid' && v === true
  )
  const canInvalid = vehicle?.available && vehicle.faults?.canValid === false

  return (
    <>
      <Header deviceStatus={deviceStatus} subtitle="Diagnostics" />
      <div className="troubleshoot-view">
        {loading && <LoadingSpinner />}
        {error && <div className="ts-error">{error}</div>}

        {!loading && report && (
          <>
            <section className="ts-card">
              <div className="ts-card-header">
                <h2>Vehicle status</h2>
                <button type="button" className="ts-btn" onClick={copyReport}>
                  <Icon name="content_copy" size={18} /> Copy report
                </button>
              </div>

              {!vehicle?.available ? (
                <p className="ts-muted">
                  No live vehicle data — {vehicle?.reason ?? 'unavailable'}.
                  These flags only exist while openpilot is running.
                </p>
              ) : (
                <>
                  <div className={`ts-banner ${vehicle.healthy ? 'ok' : 'bad'}`}>
                    <Icon name={vehicle.healthy ? 'check_circle' : 'error'} size={20} />
                    {vehicle.healthy ? 'No faults reported' : 'Faults active'}
                  </div>

                  <div className="ts-faults">
                    {activeFaults.length === 0 && !canInvalid && (
                      <span className="ts-muted">All fault flags clear.</span>
                    )}
                    {activeFaults.map(([k]) => (
                      <span className="ts-fault" key={k}>
                        {FAULT_LABELS[k] ?? k}
                      </span>
                    ))}
                    {canInvalid && <span className="ts-fault">CAN invalid</span>}
                  </div>

                  <dl className="ts-grid">
                    <div><dt>CAN errors</dt><dd>{vehicle.canErrorCounter}</dd></div>
                    <div><dt>Gear</dt><dd>{vehicle.gearShifter ?? '—'}</dd></div>
                    <div><dt>Speed</dt><dd>{vehicle.vEgo?.toFixed(1) ?? '—'} m/s</dd></div>
                    <div><dt>Cruise available</dt><dd>{String(vehicle.cruise?.available)}</dd></div>
                    <div><dt>Cruise engaged</dt><dd>{String(vehicle.cruise?.enabled)}</dd></div>
                    <div><dt>Non-adaptive</dt><dd>{String(vehicle.cruise?.nonAdaptive)}</dd></div>
                  </dl>
                </>
              )}
            </section>

            <section className="ts-card">
              <div className="ts-card-header">
                <h2>
                  Settings{' '}
                  <span className="ts-count">
                    {report.settings?.changedCount ?? 0} changed of {report.settings?.total ?? 0}
                  </span>
                </h2>
                <label className="ts-toggle">
                  <input
                    type="checkbox"
                    checked={changedOnly}
                    onChange={(e) => setChangedOnly(e.target.checked)}
                  />
                  Changed only
                </label>
              </div>

              {!report.settings?.available && (
                <p className="ts-muted">Settings unavailable — {report.settings?.reason}</p>
              )}

              {grouped.length === 0 && report.settings?.available && (
                <p className="ts-muted">
                  {changedOnly ? 'Everything is at its default.' : 'No settings found.'}
                </p>
              )}

              {grouped.map(([panelLabel, panelItems]) => (
                <div className="ts-panel-group" key={panelLabel}>
                  <h3>{panelLabel}</h3>
                  <table className="ts-table">
                    <thead>
                      <tr><th>Setting</th><th>Current</th><th>Default</th></tr>
                    </thead>
                    <tbody>
                      {panelItems.map((item) => (
                        <tr key={item.key} className={item.changed ? 'changed' : ''}>
                          <td>
                            <span className="ts-title">{item.title}</span>
                            <span className="ts-key">{item.key}</span>
                          </td>
                          <td>
                            {formatValue(item.current)}
                            {item.changed && <span className="ts-badge">Changed</span>}
                          </td>
                          <td className="ts-muted">{formatValue(item.default)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </section>
          </>
        )}
      </div>
    </>
  )
}
