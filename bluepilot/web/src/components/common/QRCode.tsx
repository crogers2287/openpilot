import { useMemo } from 'react'
import qrcode from 'qrcode-generator'

interface QRCodeProps {
  value: string
  /** Rendered size in px. The SVG scales, so this is purely presentational. */
  size?: number
  /** Quiet zone in modules. The spec requires 4; scanners get flaky below that. */
  margin?: number
  className?: string
  title?: string
}

/**
 * Renders a QR code as inline SVG.
 *
 * Error correction is 'M': the auth URL is short enough that the extra
 * redundancy costs nothing, and it keeps the code readable on a glare-y
 * screen in a truck.
 */
export const QRCode = ({ value, size = 220, margin = 4, className, title }: QRCodeProps) => {
  const { path, dimension } = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(value)
    qr.make()

    const count = qr.getModuleCount()
    const dim = count + margin * 2

    // One path of many little squares beats one <rect> per module: far fewer
    // DOM nodes, and it scales crisply.
    const parts: string[] = []
    for (let r = 0; r < count; r++) {
      for (let c = 0; c < count; c++) {
        if (qr.isDark(r, c)) {
          parts.push(`M${c + margin} ${r + margin}h1v1h-1z`)
        }
      }
    }
    return { path: parts.join(''), dimension: dim }
  }, [value, margin])

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={`0 0 ${dimension} ${dimension}`}
      shapeRendering="crispEdges"
      role="img"
      aria-label={title || 'QR code'}
    >
      {title && <title>{title}</title>}
      {/* Solid light background: the quiet zone must stay light for scanners,
          even when the surrounding UI is dark. */}
      <rect width={dimension} height={dimension} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  )
}
