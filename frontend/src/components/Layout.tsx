import { NavLink, Outlet } from 'react-router-dom'
import ConnectionIndicator from './ConnectionIndicator'

export const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/cameras', label: 'Cameras' },
  { to: '/incidents', label: 'Incidents' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/health', label: 'System Health' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:bg-white focus:p-2 focus:text-black"
      >
        Skip to content
      </a>
      <aside className="border-b border-slate-800 bg-slate-900 md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4 text-lg font-semibold">Black Smoke Monitor</div>
        <nav aria-label="Primary" className="flex flex-wrap gap-1 px-2 pb-3 md:flex-col">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) =>
                `rounded px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                  isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <span className="text-sm text-slate-400">Supplemental monitoring — not a certified fire alarm</span>
          <ConnectionIndicator />
        </header>
        <main id="main" className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
