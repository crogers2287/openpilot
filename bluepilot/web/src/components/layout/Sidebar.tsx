import { useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Icon } from '@/components/common'
import { useSidebarStore } from '@/stores/useSidebarStore'
import './Sidebar.css'

interface NavItem {
  to: string
  label: string
  icon: string
}

interface NavSection {
  title: string
  items: NavItem[]
}

// Grouped so the whole product is visible at a glance. Previously every
// destination other than Home was reachable only via cards on the Home view,
// which made the portal feel smaller than it is.
const SECTIONS: NavSection[] = [
  {
    title: 'Device',
    items: [
      { to: '/', label: 'Home', icon: 'home' },
      { to: '/settings', label: 'Settings', icon: 'settings' },
    ],
  },
  {
    title: 'Recordings',
    items: [{ to: '/routes', label: 'Routes', icon: 'videocam' }],
  },
  {
    title: 'Tools',
    items: [
      { to: '/parameters', label: 'Parameters', icon: 'tune' },
      { to: '/logs', label: 'System Logs', icon: 'description' },
      { to: '/troubleshoot', label: 'Troubleshoot', icon: 'healing' },
      { to: '/tailnet', label: 'Tailnet', icon: 'vpn_lock' },
    ],
  },
]

export const Sidebar = () => {
  const { isOpen, close } = useSidebarStore()
  const location = useLocation()

  // Navigating on mobile should dismiss the drawer.
  useEffect(() => {
    close()
  }, [location.pathname, close])

  // Escape closes the drawer; harmless when the rail is permanent.
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, close])

  return (
    <>
      {isOpen && <div className="sidebar-underlay" onClick={close} aria-hidden="true" />}

      <nav
        className={`sidebar ${isOpen ? 'open' : ''}`}
        aria-label="Primary navigation"
      >
        <div className="sidebar-header">
          <span className="sidebar-brand">
            <img src="/icons/bluedragon.svg" alt="" className="sidebar-brand-mark" />
            Blue Dragon
          </span>
          <button
            type="button"
            className="icon-btn sidebar-close"
            onClick={close}
            title="Close navigation"
            aria-label="Close navigation"
          >
            <Icon name="close" size={22} />
          </button>
        </div>

        {SECTIONS.map((section) => (
          <div className="sidebar-section" key={section.title}>
            <span className="sidebar-section-title">{section.title}</span>
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                // `end` so "/" only matches Home, not every route.
                end={item.to === '/'}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? 'active' : ''}`
                }
              >
                <Icon name={item.icon} size={22} />
                <span className="sidebar-link-label">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </>
  )
}
